# 2 — RUNTIME DEBUG AND PATCH REPORT

## Defect Matrix

| ID | Location | Exception / Symptom | Trigger Condition | Root Cause | Resolution |
|---|---|---|---|---|---|
| DM-1 | `refine_script.py:880` (`main` → `connect_over_cdp`) | Playwright `TimeoutError: Timeout 5000ms exceeded` at ws-handshake stage | Chrome cold start: `ensure_chrome_debug_session`'s HTTP probe (`/json/version`) returns OK before the browser-level DevTools websocket finishes binding; main's separate connect then races it | Two independent readiness checks with no retry coupling; 5 s hard timeout too tight for cold boot | **Patched:** 3-attempt retry loop (2 s/4 s backoff) + timeout raised 5000→15000 ms. Resume from checkpoint P13 verified — zero reprocessing |
| DM-2 | `refine_script.py:1068` (`verify_script_with_rubric`) | `[AUDIT] 'audit_rubric.md' not found. Skipping rubric verification.` | Rubric relocated to `docs/` during root-declutter; loader still used bare filename | Dangling-path gap in the reorg sweep (only `.py` loaders were swept, this lookup lived behind a graceful-degrade branch) | **Patched:** `docs/audit_rubric.md` primary + legacy-root fallback. Audit gate re-run via one-shot driver |
| DM-3 | Gemini output format (remediation driver) | `<p id="N">` wrapper absent from model reply (round 1 & 2) | Instruction-following drift on multi-block structured output | Model prefers plain prose for long Arabic rewrites | **Hot-fixed in driver:** dual parser — tagged regex first, ordered blank-line block mapping fallback (with chatty-intro-line guard); round 1 splice succeeded via fallback |
| DM-4 | Remediation R1 side-effect | Rubric #2 regression: technical terms colloquialized (`Calculator→آلة حاسبة`, `Hydrogen→هيدروجين`, `Octave→أوكتاف`, `Ether→أثير`) | Over-broad "make it Amiya" instruction let the model translate domain vocabulary | Prompt lacked term-preservation lock | **Fixed:** deterministic harakat-tolerant term restoration (3 spans) + R2 prompt gained explicit NON-NEGOTIABLE term-lock rules |
| DM-5 | Sandbox supervision layer | Background `Start-Process` children reaped (`ChildProcess.kill`); foreground run invisible to polling | Execution harness forbids detached processes | Tooling constraint, not script defect | **Adapted:** supervised windows of ~100 s via `cmd /c python -u … >> log`, unbuffered `-u` + file redirect for progressive telemetry; checkpoint made window-kills free |

## High-Level Solution Strategy

1. **Readiness decoupling (DM-1):** rather than synchronizing the two probes, treat CDP connect as idempotent-with-retry — cheaper and robust to any future boot-order drift.
2. **Graceful-degrade audit trail (DM-2):** the rubric skip *looked* like success (`return True`). Patch keeps the fallback path but now logs loudly only when both paths miss; supervisor caught it because the run log line was scanned, not trusted.
3. **Output-contract hardening (DM-3/4):** every LLM structured-output consumer in the pipeline should assume format drift and ship a deterministic fallback parser; every content directive that worked (term locks) is now phrased as a NON-NEGOTIABLE block, mirroring the existing `[RATIO LOCK]/[TAG LOCK]` pattern.

## Security & Concurrency Audit

| Check | Result |
|---|---|
| Paid SDK imports | ✅ none — only `playwright.sync_api`; all AI over CDP `127.0.0.1:9222` |
| Subprocess discipline | ✅ Chrome launched via list-args, `creationflags=CREATE_NEW_CONSOLE`, no shell interpolation |
| Socket hygiene on 9222 | ✅ `ensure_chrome_debug_session(force_restart=True)` kills only the PID bound to the port (netstat-scoped), never image-wide; stale listener terminated cleanly before each relaunch (log: `Terminated CDP process (PID: 18576)`) |
| Checkpoint atomicity | ✅ `save_checkpoint` = tmp + `fsync` + `os.replace`; no `WinError 32` sharing violations across 16 saves + 7 process restarts |
| Deliverable writes | ✅ all regenerated through atomic save paths; crash between save and audit cannot orphan state (recovery branch regenerates before delete) |
| Console UTF-8 | ✅ Arabic logs clean under redirected pipes (`sys.stdout.reconfigure(encoding='utf-8')`) |
