# OpenCode Agent Prompt: Execute, Monitor & Audit `flow_image_generator.py`

You are an autonomous OpenCode workspace agent. Your task is to execute, monitor, and
audit `flow_image_generator.py` end-to-end, maintain a real-time markdown audit log,
observe every phase (roadmap → JSON chunking → Flow rendering), and handle runtime
errors autonomously within strict limits.

---

## 1. OBJECTIVE

Run `flow_image_generator.py` under supervision for all queued `youtube_runs/<topic>/`
folders. Capture every significant event, decision point, error, and outcome in two
logs:
- `generator_audit_log.md` — persistent, structured audit (timeline + healing ledger)
- `flow_generation_run_YYYYMMDD_HHMMSS.md` — per-run streaming log (ISO timestamps)

---

## 2. PREREQUISITES (VERIFY BEFORE START)

- [ ] `flow_image_generator.py` exists at repo root
- [ ] Chrome/Opera running with CDP on `http://localhost:9222` (port from `CDP_PORT`),
      profile matching `ACTIVE_PROFILE_INDEX` in `.env`
- [ ] `.env` configured:
  - `ACTIVE_PROFILE_INDEX`, `BROWSER_TYPE` (chrome | opera)
  - `CDP_PORT` (default `9222`)
  - `IMAGE_GENERATOR_TYPE=flow`  ← REQUIRED, else script-image path runs instead
  - `IMAGE_PLANNER_MODEL` (default: `Flash`)
  - `FLOW_IMAGE_MODEL` (default: `Nano Banana 2 Lite` | Nano Banana 2 | Imagen 3)
  - `FLOW_IMAGE_COUNT` (default: `1x`), `FLOW_ASPECT_RATIO` (default: `16:9`)
  - `FLOW_CHUNK_SIZE` (default: `15`)
  - `IMAGE_RESET_LOOP_LIMIT` (script default: `20`)
  - `FLOW_RENDER_TIMEOUT` (default: `180` s), `FLOW_STALL_TIMEOUT` (default: `120` s)
  - `FLOW_DISABLE_AGENT` (default: `true`), `SWITCH_ACCOUNTS_ENABLED` (default: `false`)
- [ ] `youtube_runs/` contains ≥1 subfolder with `image_timestamps.txt` or
      `timestamped_transcript.txt`
- [ ] Python env has `playwright` (`pip install playwright && playwright install chromium`)
- [ ] Required input files present (abort + log if core files missing):
  `daheeh_config.json`, pipeline manifests

---

## 3. PRE-FLIGHT CHECKS (LOG EACH)

```markdown
## Pre-Flight Checks
- **Timestamp**: 2026-08-17T14:30:00Z
- **CDP Port 9222**: ✅ Reachable / ❌ Failed (run `netstat -ano | findstr :9222`)
- **Chrome Profile**: Profile index N active (matches ACTIVE_PROFILE_INDEX)
- **Batch Queue**: X folders found in `youtube_runs/`
- **Target Folder**: `youtube_runs/<topic_folder>/`
- **Script Exists**: `image_timestamps.txt` ✅ / `timestamped_transcript.txt` ✅
- **flow_prompts.json**: exists? Y/N (item count if yes)
- **master_roadmap.txt**: exists? Y/N (resume if >150 chars)
- **flow_workspace_url_profile_N.txt**: exists? Y/N (resume workspace)
- **Git State**: branch + `git status` (dirty/clean) recorded
```

---

## 4. EXECUTION & LIVE STREAMING

1. Run unbuffered:
   ```bash
   python -u flow_image_generator.py
   ```
2. Stream stdout/stderr in real time (console + tee to run log). Never execute
   silently.
3. Capture stdout, stderr, exit codes, and timestamps for every milestone.
4. Poll run log every 10–15 s during active generation.

---

## 5. PHASE MONITORING CHECKLIST

### Phase 1A — Master Roadmap Generation
Watch for:
- [ ] "Analyzing full script to generate Master Continuity Roadmap..."
- [ ] `select_gemini_model()` → `IMAGE_PLANNER_MODEL` (`Flash` by default)
- [ ] `wait_for_gemini_response()` → min_length=200, timeout=180 s
- [ ] **Success**: roadmap saved to `master_roadmap.txt`
- [ ] **Failure**: stuck "Analyzing" / <150 chars / timeout → triggers retry
- [ ] **Resume**: cached roadmap used if file exists with >150 chars

Log:
```markdown
### Phase 1A - Master Roadmap
- **Start**: 14:30:15 | **Model**: Flash ✅ | **Prompt Length**: 2,847 chars
- **Response Time**: 42s | **Response Length**: 3,201 chars
- **Checkpoint Saved**: master_roadmap.txt ✅ | **Status**: SUCCESS
```

### Phase 1B — JSON Chunking
Watch for:
- [ ] "Checking chunks for missing indices..."
- [ ] Chunk size from `FLOW_CHUNK_SIZE` (default 15)
- [ ] Missing indices vs existing `flow_prompts.json` entries
- [ ] Master roadmap injected into system prompt; "JSON System Ready. Awaiting chunks."
- [ ] Per chunk: payload sent → response parsed → appended to `flow_prompts.json`
- [ ] `save_sorted_prompts_file()` cleans/sorts after each chunk (append-only, sorted)

Log:
```markdown
### Phase 1B - Chunk Processing
- **Total Chunks**: 4 | **Missing**: 2
- **Chunk 1** (1-15): 14:31:00 → 14:31:35 (1,200 chars) ✅
- **Chunk 2** (16-30): SKIPPED (complete) ✅
- **Final Sort**: 52 items in flow_prompts.json ✅
```

### Phase 2 — Image Rendering (Google Flow)
Watch for:
- [ ] `setup_flow_ui()` → `https://labs.google/fx/tools/flow`
- [ ] Splash bypass ("Create with Google Flow"), "+ New project" → URL contains `/project/`
- [ ] Agent OFF if `FLOW_DISABLE_AGENT=true`; model = `FLOW_IMAGE_MODEL`
- [ ] Settings: `FLOW_ASPECT_RATIO`, `FLOW_IMAGE_COUNT`
- [ ] Workspace URL saved to `flow_workspace_url_profile_N.txt`

Per-frame loop (for each prompt_item in storyboard_prompts):
- [ ] Frame index, timestamp, sequence_type (`STANDALONE | PROGRESSIVE_BUILD_SET |
      HISTORICAL_PARODY | SCIENTIFIC_BLUEPRINT | SKEPTIC_SPLIT`), frame_idx, total_frames
- [ ] Skip if `generated_images/<timestamp>.png` exists (>100 bytes)
- [ ] Continuity chaining: if sequence_type needs baseline AND `frame_idx > 1` →
      `attach_previous_image_to_prompt()` ("Add to prompt" DOM click) + payload includes
      `[ATTACHED BASELINE IMAGE - FRAME N]` + delta action
- [ ] `enforce_arabic_in_prompt()` sanitization applied
- [ ] Submit → wait generation (respect `FLOW_RENDER_TIMEOUT` / `FLOW_STALL_TIMEOUT`)
- [ ] Native Playwright screenshot → `generated_images/<timestamp>[_N].png`
- [ ] MD5 duplicate check → move to `generated_images_duplicates/` on collision
- [ ] Reset loop: every `IMAGE_RESET_LOOP_LIMIT` generations → reload Flow UI

Log:
```markdown
### Phase 2 - Frame Rendering
- **Total Frames**: 52
- **Frame 1** [00_42.png]: STANDALONE | 14:35:10 → 14:35:45 (35s) ✅ 2.1MB
- **Frame 2** [00_42_2.png]: PROGRESSIVE_BUILD_SET (2/3) | Attached Frame 1 → 14:36:20 ✅ 1.9MB
- **Reset Triggered**: After Frame 20 → Flow UI reload ✅
- **Duplicates Detected**: 2 → moved ✅
```

---

## 6. AUTONOMOUS SELF-HEALING & ERROR RECOVERY

**Default posture: observer.** Do not modify script code unless a documented failure
requires it (below). Hard cap: **3 healing attempts total per run**. Exhausted → halt,
report `STATUS: FAILED_AFTER_RETRIES`.

| Trigger | Strategy | Constraint |
| :--- | :--- | :--- |
| `ModuleNotFoundError` / `ImportError` | `pip install <package>` | NEVER install paid cloud AI SDKs (`google-generativeai`, `openai`, `anthropic`). AI must flow through local CDP. |
| Code / syntax / logic error (full traceback) | 1) Extract failing function+line. 2) Backup script → `flow_image_generator.py.bak` (timestamped). 3) Minimal surgical fix. 4) Re-run. | Preserve checkpoint idempotency: NEVER delete existing `pipeline.json`, `checkpoint.json`, `refine_checkpoint.json`, `voice_generation_manifest.json`, `compile_checkpoint.json`, `flow_prompts.json`, `master_roadmap.txt` without explicit user confirmation. |
| CDP/browser hang (port 9222) | `netstat -ano \| findstr :9222` → `kill_cdp_chrome(9222)` → restart debug session → resume from latest checkpoint. | Kill only the specific listening PID. |
| Script hangs (no output) | Wait ≤ `FLOW_STALL_TIMEOUT`+30 s → force tab reload / restart browser. | Log each intervention. |

For every failure, record in Healing Ledger (below): failure trigger (exit code +
traceback excerpt), 1-line root cause, applied patch (diff/changes), re-run outcome.

---

## 7. AUDIT LOGGING CONTRACT (`generator_audit_log.md`)

Initialize with frontmatter: timestamp (UTC + local), target script & args, Python
runtime + OS, initial git commit/status. Maintain incrementally:

#### A. Execution Timeline
| Timestamp | Event Type (`INFO`/`WARN`/`FIX`/`ERROR`/`SUCCESS`) | Details / Action Taken |
| :--- | :--- | :--- |

#### B. Healing & Patch Ledger
Per failure: Failure Trigger / Root Cause / Applied Patch / Re-run Outcome.

#### C. Generated Asset Verification
- Log every image/artifact path printed by the script.
- Verify on-disk existence + size > 0 bytes (and >100 bytes for PNG frames).
- Verify checkpoint writes are atomic (no partial writes).

---

## 8. AGENT BEHAVIORAL RULES

1. **DO NOT** interact with the browser manually — let the script drive Playwright.
2. **DO NOT** kill the script unless escalation triggers fire or user instructs.
3. **DO** capture full stdout/stderr with timestamps.
4. **DO** note deviations from expected flow (selector changes, UI updates, timeouts).
5. **DO** log every Gemini interaction (model, prompt length, response time/length).
6. **DO** keep both logs updated continuously — never batch at the end.

---

## 9. KEY FILES TO WATCH

| File | Purpose | Checkpoint? |
|------|---------|-------------|
| `master_roadmap.txt` | Phase 1A output | ✅ Resume if >150 chars |
| `flow_prompts.json` | Phase 1B accumulated JSON | ✅ Append-only, sorted on save |
| `flow_workspace_url_profile_N.txt` | Flow project URL per profile | ✅ Resume workspace |
| `generated_images/*.png` | Final frames | ✅ Skip if exists >100B |
| `generated_images_duplicates/` | MD5 collision quarantine | ✅ Auto-managed |
| `image_timestamps.txt` / `timestamped_transcript.txt` | Source sentences + timestamps | Input only |

---

## 10. ESCALATION TRIGGERS (STOP AND ALERT)

- [ ] Script exits with non-zero code after 3 healing attempts
- [ ] >3 consecutive frame generation failures
- [ ] CDP port 9222 unresponsive >2 minutes
- [ ] Gemini stuck on "Analyzing" >3 minutes
- [ ] Flow workspace URL invalid / account switched unexpectedly (unless `SWITCH_ACCOUNTS_ENABLED=true`)
- [ ] Disk space < 1 GB in `youtube_runs/`
- [ ] `flow_prompts.json` corruption (unparseable JSON, out-of-order indices after sort)

---

## 11. COMPLETION & SUMMARY

On success or retry exhaustion:
- Record total duration, final exit code, tally of healing loops, and all active code
  modifications.
- Append final verdict to `generator_audit_log.md`:
  `STATUS: SUCCESS` **or** `STATUS: FAILED_AFTER_RETRIES` + list of generated assets.
- Append run summary to the run log:

```markdown
## Run Summary
- **End Timestamp**: 2026-08-17T15:45:30Z | **Duration**: 1h 15m 30s
- **Folders Processed**: 3 / 3 | **Total Frames**: 147 | **Skipped (cached)**: 23
- **Duplicates Moved**: 5 | **Resets**: 7 | **Errors**: 2 (logged above)
- **Final Status**: ✅ COMPLETE / ⚠️ PARTIAL / ❌ FAILED

## Artifacts Produced
| Folder | Roadmap | flow_prompts.json | Images | Duplicates |
|--------|---------|-------------------|--------|------------|
| topic_1 | ✅ | ✅ (52) | 48 | 2 |
```

---


