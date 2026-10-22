# Claude Interim Delegation

- **Task ID:** CLAUDE-INTERIM-H10.
- **Status:** concluded 2026-10-07T02:15Z (started 2026-10-06T08:37:43Z); **reopened 2026-10-07T02:44Z** for user-approved follow-ups (c) and (d). The outcome is in `CLAUDE_INTERIM_RESULT.md`.
- **Delegate:** Claude Code (Opus 5.5 lead plus subagents), driven by the user.

The user approved this brief before execution. It follows the shape of `ANTIGRAVITY_H10_PLAN_CRITIC_DELEGATION.md` and is stricter in several ways. The live record is in `docs/sessions/CLAUDE_INTERIM_RESULT.md`.

## Why this exists

- Codex's weekly quota ran out. It resets at 2026-10-09T21:13Z.
- Antigravity completed `analyze` and `write`. It halted at TTS (`ANTIGRAVITY_H10_PLAN_CRITIC_RESULT.md`).
- The user asked Claude to use the gap productively and without damage. Codex must be able to resume with full, hash-verifiable knowledge of what happened.

## Goal and end condition

**What Claude delivers:**
1. A fail-closed fix for the TTS redirect loop, with regression tests (an authorized deviation).
2. An independent second-opinion review of Codex's unreviewed work in progress.
3. An independent review of Antigravity's Phase 2 deliverables.
4. An optional read-only AI Studio probe.
5. A Stage 3 runbook for Codex.
6. A complete, hash-bound handoff.

**Out of scope.** No live Gemini, TTS or Flow sends. Live pipeline stages are blocked by two things:
- the spent TTS budget;
- the `<final_script>` tag defect in the Phase 2 script.

**Deadline.** Claude stops writing by 2026-10-09T12:00Z.

## User authorizations (verbatim, 2026-10-06)

| Question put to the user | User's answer |
|---|---|
| "tts_generator.py is marked "immutable" in Codex's protected baseline. May Claude edit it to make the TTS loop fail closed: stop instead of looping, never type into the wrong page, and close the unguarded Ctrl+Enter submit? The edit would be recorded as an authorized deviation, with regression tests and a byte-exact restore script." | **"Yes, fix it (Recommended)"** |
| "Project CLAUDE.md forbids modifying docs/, but Codex's handoff protocol (AGENTS.md:97) keeps delegation briefs and results in docs/sessions/. Which waiver do you give?" | **"Same as Antigravity (Recommended)"**. This permits the two new `CLAUDE_INTERIM_*` docs, narrow HANDOFF edits and edits to CONTINUITY's Now/Next bullets only. |
| "Should Claude do the optional read-only browser probe with you present? … No typing, no clicks, 0 TTS and 0 Gemini sends." | **"Yes, when I'm present (Recommended)"** |
| (2026-10-06T13:10Z) "No browser is on port 9222 … How should we do the read-only AI Studio probe?" | **"I start Chrome (Recommended)"** |
| (2026-10-07T00:39Z, unprompted follow-up from the user) | **"okay, I prefer you run it so you have direct access to the browser to monitor what's happening live and what clicks that work and don't work."** This authorizes Claude to run Codex's launcher `.runtime/start_owned_profile.py` once. It is a narrow exception to "no launching browsers" below. Probe clicks remain unauthorized until the user explicitly approves a click test. |
| (2026-10-07T01:15Z) Claude recommended a no-send "dress rehearsal" click test (real `reapply_speech_settings` on an empty prompt, with tripwires and a network block). | **"Click test: YES — the dress rehearsal as designed in the resume cursor (real reapply_speech_settings, empty prompt, tripwires + network block; no typing, no Run)."** |
| (2026-10-07T01:39Z) Claude offered two optional follow-ups: (a) a one-click "Create new dialog" probe (no typing, no Run); (b) a model-identity fail-closed check in `tts_generator.py`. | **"for the two optional follow-ups, after the reviewer answers, go with the best recommend option and with the best approach."** This delegates both decisions to Claude, after the reviewer returns. Limits that still apply: no typing into prompts, no Run, no sends; any `tts_generator.py` edit goes through a cc-executor with tests and a byte audit. |
| (2026-10-07T02:40Z, after closeout) Claude offered (c) a voice-selection probe (choose Achird; no typing, no Run) and (d) an UNAPPLIED proposal diff + tests for the new AI Studio TTS flow in `proposals/`. | **"yes, go with your recommendation "Both"."** Scope: (c) one probe script using Playwright `locator.click()` only, same tripwires/network block, no typing or keyboard, close only its own tab; (d) a proposal only. Live `src/` and `tests/` stay untouched; verification happens in a scratch copy outside the repo. |

## Workspace and baseline

**Workspace**
- Path: `C:/Users/Snoozer/Downloads/Antigravity/Youtube Automation 2/buckup/Version 4 before deepseek implementation plan/image_generation`.
- Branch `codex/adaptive-multi-channel-visual-engine`, HEAD `41d02eba1fa17467ac8fdbfcbb6d445e5fd9f64b`.
- Work happens in place. No branch or worktree switch.

**Claude's runtime folder:** `.runtime/claude_interim_20261006T083743Z/`, created exclusively. It holds:

| File | Purpose |
|---|---|
| `baseline_manifest.json` | Captured before any Claude write. Covers 74 expanded dirty files, all 270 Codex protected inputs (267 match, 3 drift is expected), gitignored evidence trees (19 run files, 9 Antigravity runtime files, 55 Codex handoff files), `.runtime/adaptive.sqlite3` and `.runtime/owned_browsers.json`. |
| `claude_verify.py` | Read-only; never exits early. Classifies every difference as CLAUDE_ALLOWED, OPERATIONAL or UNEXPECTED. Exit 0 means zero UNEXPECTED. |
| `restore_preimages.py` | Dry-run by default; `--apply` restores exact bytes and verifies SHA-256. |
| `pre_images/` | Exact bytes of every file Claude may modify. |
| `drift_vs_codex_baseline.md` | Explains why `verify_baseline.py` exits 2. Its 13 entries are the `.claude/agents` archive. All drift is benign. |

## Allowed writes

- This file and `docs/sessions/CLAUDE_INTERIM_RESULT.md`. Both are new and exclusively created.
- `docs/sessions/HANDOFF.md`: narrow edits that keep its six-section, ~400-token shape.
- `docs/short-term-plan/CONTINUITY.md`: Now/Next bullets only. The file is LF-only, so the edit must preserve LF bytes.
- `src/youtube_automation/audio/tts_generator.py`: the authorized fail-closed deviation only. The file has mixed line endings, so every untouched line must stay byte-identical. Compare against the pre-image; `git diff` hides line-ending changes.
- A new `tests/unit/test_tts_workspace_redirect.py`.
- Anything under `.runtime/claude_interim_20261006T083743Z/`.

## Forbidden

**Git and tooling**
- Git: stage, commit, push, merge, reset, revert, stash, checkout or restore.
- Worktrees, including subagent isolation.
- Formatters in write mode.
- serena edit or memory tools (`.serena/memories/` is tracked).

**Codex's and Antigravity's files**
- Any of Codex's work-in-progress files.
- Antigravity's run directory, `.runtime/antigravity_phase2_*` and `ANTIGRAVITY_*_RESULT.md`.
- The send guard and its journal.
- `youtube_runs/`, `AGENTS.md`, `GEMINI.md`, `tasks/`, `channels/`.
- `runtime_state.json`, `.env`, browser profiles.

**Live services**
- Gemini, TTS and Flow sends.
- Profile rotation.
- Killing or launching browsers.

**Ownership.** Acceptance and approval gates, quota accounting, task checkboxes, LEARNINGS/TEMPLATE updates, architecture and commits all remain Codex-owned.

## Roles

**Lead (Claude main session)**
- Coordinator and reviewer.
- Sole browser operator, and only with the user present.
- Writes the RESULT and HANDOFF.

**Workers**

| Agent | Model | Role |
|---|---|---|
| cc-executor | Sonnet/Opus | Owns exact files |
| cc-tester | Sonnet | Testing |
| cc-reviewer | Opus | Read-only; has no Edit/Write tools; returns findings that the lead persists under `reviews/` |

No two workers write the same path. Workers never touch the browser, Audacity or send budgets.

## Stop conditions

- An unexpected protected-hash change, meaning `claude_verify.py` reports UNEXPECTED above 0.
- The same failure twice with no new hypothesis.
- Browser ownership cannot be proved.
- Any gate fails.

In every case, stop, preserve evidence and log it in RESULT. No blind third retry.

## Fresh Codex return checklist (extends the Antigravity checklist)

1. Read `HANDOFF.md`, `CONTINUITY.md`, this brief and `CLAUDE_INTERIM_RESULT.md`, plus the still-unreviewed `ANTIGRAVITY_H10_PLAN_CRITIC_RESULT.md`.
2. Recheck quota. Do not infer a new cap.
3. Run `PYTHONDONTWRITEBYTECODE=1 ./venv/Scripts/python.exe -I .runtime/claude_interim_20261006T083743Z/claude_verify.py`. Read `drift_vs_codex_baseline.md`. Confirm your work in progress and Antigravity's evidence are byte-identical.
4. Review the `tts_generator.py` deviation against `pre_images/`. To reject it: `restore_preimages.py --path src/youtube_automation/audio/tts_generator.py --apply`. Then run `pytest tests/unit`.
5. Triage every finding in `reviews/`: accept or reject. The `<final_script>` tag defect blocks Stage 3.
6. Follow the Stage 3 runbook in RESULT. Fold the lessons into LEARNINGS/TEMPLATE. Then decide how to group commits.
