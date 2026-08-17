# Prompt for Opencode Agent: Run & Monitor `flow_image_generator.py`

## Objective
Execute `flow_image_generator.py` under supervision, monitor all phases in real-time, and produce a structured Markdown log (`flow_generation_run_<timestamp>.md`) capturing every significant event, decision point, error, and outcome.

---

## Prerequisites (Verify Before Start)

- [ ] Chrome/Opera running with CDP on `http://localhost:9222` (profile matching `ACTIVE_PROFILE_INDEX` in `.env`)
- [ ] `.env` configured with required keys:
  - `ACTIVE_PROFILE_INDEX`, `BROWSER_TYPE`
  - `IMAGE_PLANNER_MODEL` (default: `Flash-Lite`)
  - `FLOW_IMAGE_MODEL` (default: `Nano Banana 2`)
  - `FLOW_IMAGE_COUNT` (default: `1x`)
  - `FLOW_ASPECT_RATIO` (default: `16:9`)
  - `FLOW_CHUNK_SIZE` (default: `15`)
  - `IMAGE_RESET_LOOP_LIMIT` (default: `20`)
  - `SWITCH_ACCOUNTS_ENABLED` (default: `false`)
  - `FLOW_DISABLE_AGENT` (default: `true`)
- [ ] `youtube_runs/` contains at least one subfolder with `image_timestamps.txt` or `timestamped_transcript.txt`
- [ ] `playwright` installed (`pip install playwright && playwright install chromium`)

---

## Execution Instructions for Agent

### 1. Initialize Run Log
Create a Markdown file named:
```
flow_generation_run_YYYYMMDD_HHMMSS.md
```
Use ISO timestamp format. This file will be appended continuously during the run.

### 2. Pre-Flight Checks (Log Each)
```markdown
## Pre-Flight Checks
- **Timestamp**: 2026-08-17T14:30:00Z
- **CDP Port 9222**: ✅ Reachable / ❌ Failed (run `netstat -ano | findstr :9222`)
- **Chrome Profile**: Profile index N active
- **Batch Queue**: X folders found in `youtube_runs/`
- **Target Folder**: `youtube_runs/<topic_folder>/`
- **Script Exists**: `image_timestamps.txt` ✅ / `timestamped_transcript.txt` ✅
- **Prompts File**: `flow_prompts.json` exists? Y/N
- **Master Roadmap**: `master_roadmap.txt` exists? Y/N (checkpoint resume)
- **Workspace URL Checkpoint**: `flow_workspace_url_profile_N.txt` exists? Y/N
```

### 3. Launch Script with Monitoring
Run:
```bash
python flow_image_generator.py
```
**Capture stdout/stderr in real-time** (tee to log file + console).

### 4. Phase Monitoring Checklist

#### Phase 1A: Master Roadmap Generation
Watch for:
- [ ] "Analyzing full script to generate Master Continuity Roadmap..."
- [ ] `select_gemini_model()` → Target model: `Flash-Lite` (or `.env` value)
- [ ] Roadmap prompt sent (length ~2000+ chars)
- [ ] `wait_for_gemini_response()` → min_length=200, timeout=180s
- [ ] **Success**: "Master Roadmap successfully generated and saved to checkpoint"
- [ ] **Failure modes**: "Analyzing" stuck, <150 chars, timeout → triggers retry

Log every Gemini interaction:
```markdown
### Phase 1A - Master Roadmap
- **Start**: 14:30:15
- **Model Selected**: Flash-Lite ✅
- **Prompt Length**: 2,847 chars
- **Response Time**: 42s
- **Response Length**: 3,201 chars
- **Checkpoint Saved**: master_roadmap.txt ✅
- **Status**: SUCCESS
```

#### Phase 1B: JSON Chunking
Watch for:
- [ ] "Checking chunks for missing indices..."
- [ ] Chunk size from `FLOW_CHUNK_SIZE` (default 15)
- [ ] Missing indices detected vs existing in `flow_prompts.json`
- [ ] System prompt injected with Master Roadmap
- [ ] "JSON System Ready. Awaiting chunks." confirmation
- [ ] Each chunk: payload sent → response parsed → appended to `flow_prompts.json`
- [ ] `save_sorted_prompts_file()` cleans/sorts after each chunk

Log per chunk:
```markdown
### Phase 1B - Chunk Processing
- **Total Chunks**: 4 | **Missing Chunks**: 2
- **Chunk 1** (Indices 1-15): Sent 14:31:00 → Response 14:31:35 (1,200 chars) ✅
- **Chunk 2** (Indices 16-30): SKIPPED (already complete) ✅
- **Chunk 3** (Indices 31-45): Sent 14:32:10 → Response 14:32:55 (980 chars) ✅
- **Chunk 4** (Indices 46-52): Sent 14:33:20 → Response 14:33:48 (650 chars) ✅
- **Final Sort**: 52 items in flow_prompts.json ✅
```

#### Phase 2: Image Rendering (Google Flow)
Watch for:
- [ ] `setup_flow_ui()` → Loads `https://labs.google/fx/tools/flow`
- [ ] Splash screen bypass: "Create with Google Flow"
- [ ] "+ New project" click → URL contains `/project/`
- [ ] Agent OFF (if `FLOW_DISABLE_AGENT=true`)
- [ ] Model selection: `FLOW_IMAGE_MODEL` (Nano Banana 2)
- [ ] Settings: Aspect Ratio `16:9`, Count `1x`
- [ ] Workspace URL saved to `flow_workspace_url_profile_N.txt`

**Per Frame Rendering Loop:**
For each `prompt_item` in `storyboard_prompts`:
- [ ] Frame index, timestamp, sequence_type, frame_idx, total_frames
- [ ] Skip if `generated_images/<timestamp>.png` exists (>100 bytes)
- [ ] **Continuity chaining**: If `PROGRESSIVE_BUILD_SET`/`HISTORICAL_PARODY`/etc. AND `frame_idx > 1`:
  - `attach_previous_image_to_prompt(flow_page)` → "Add to prompt" DOM click
  - Payload includes `[ATTACHED BASELINE IMAGE - FRAME N]` + delta action
- [ ] `enforce_arabic_in_prompt()` sanitizes payload
- [ ] Submit to Flow → Wait for generation
- [ ] Screenshot capture via Playwright (native)
- [ ] Save to `generated_images/<timestamp>[_N].png`
- [ ] Duplicate check: MD5 hash → move to `generated_images_duplicates/` if match
- [ ] Reset loop: Every `IMAGE_RESET_LOOP_LIMIT` (20) generations → reload Flow UI

Log per frame:
```markdown
### Phase 2 - Frame Rendering
- **Total Frames**: 52
- **Frame 1** [00_42.png]: STANDALONE | 14:35:10 → 14:35:45 (35s) ✅ 2.1MB
- **Frame 2** [00_42_2.png]: PROGRESSIVE_BUILD_SET (2/3) | Attached Frame 1 → 14:36:20 (35s) ✅ 1.9MB
- **Frame 3** [00_42_3.png]: PROGRESSIVE_BUILD_SET (3/3) | Attached Frame 2 → 14:37:05 (45s) ✅ 2.0MB
- **Frame 4** [01_15.png]: HISTORICAL_PARODY | 14:37:50 → 14:38:20 (30s) ✅ 2.3MB
...
- **Reset Triggered**: After Frame 20 → Flow UI reload ✅
- **Duplicates Detected**: 2 → moved to generated_images_duplicates/
```

### 5. Error/Intervention Logging
Log ANY of these immediately:
- CDP connection lost → `kill_cdp_chrome(9222)` + restart browser
- Gemini "Analyzing" stuck >60s → manual intervention note
- Flow "Add to prompt" not found → selector cascade failure
- Screenshot capture failed → fallback strategy
- Duplicate hash collision → file naming conflict
- Profile switch triggered (`SWITCH_ACCOUNTS_ENABLED=true`)
- Script crash with traceback → full stack trace in log

### 6. Completion Summary
At end of run (all folders processed or manual stop), append:
```markdown
## Run Summary
- **End Timestamp**: 2026-08-17T15:45:30Z
- **Duration**: 1h 15m 30s
- **Folders Processed**: 3 / 3
- **Total Frames Generated**: 147
- **Total Frames Skipped (cached)**: 23
- **Duplicates Moved**: 5
- **Resets Performed**: 7
- **Errors Encountered**: 2 (logged above)
- **Final Status**: ✅ COMPLETE / ⚠️ PARTIAL / ❌ FAILED

## Artifacts Produced
| Folder | Master Roadmap | flow_prompts.json | Images Generated | Duplicates |
|--------|---------------|-------------------|------------------|------------|
| topic_1 | ✅ | ✅ (52 items) | 48 | 2 |
| topic_2 | ✅ | ✅ (38 items) | 35 | 1 |
| topic_3 | ✅ | ✅ (57 items) | 54 | 2 |
```

---

## Agent Behavioral Rules

1. **DO NOT** modify `flow_image_generator.py` — only observe and log
2. **DO NOT** interact with browser manually — let script drive Playwright
3. **DO NOT** kill the script unless explicitly instructed
4. **DO** capture full stdout/stderr with timestamps
5. **DO** poll log file every 10-15 seconds during active generation
6. **DO** note any deviation from expected flow (selector changes, UI updates, timeouts)
7. **DO** verify checkpoint files are written atomically (no partial writes)

---

## Quick Reference: Key Files to Watch

| File | Purpose | Checkpoint? |
|------|---------|-------------|
| `master_roadmap.txt` | Phase 1A output | ✅ Resume if >150 chars |
| `flow_prompts.json` | Phase 1B accumulated JSON | ✅ Append-only, sorted on save |
| `flow_workspace_url_profile_N.txt` | Flow project URL per profile | ✅ Resume workspace |
| `generated_images/*.png` | Final frames | ✅ Skip if exists >100B |
| `generated_images_duplicates/` | MD5 collision quarantine | ✅ Auto-managed |
| `image_timestamps.txt` / `timestamped_transcript.txt` | Source sentences + timestamps | Input only |

---

## Escalation Triggers (Stop and Alert)

- [ ] Script exits with non-zero code
- [ ] >3 consecutive frame generation failures
- [ ] CDP port 9222 unresponsive for >2 minutes
- [ ] Gemini response stuck on "Analyzing" for >3 minutes
- [ ] Flow workspace URL invalid / account switched unexpectedly
- [ ] Disk space < 1GB in `youtube_runs/`

---

## Usage
Pass this entire file as the prompt to the opencode agent:
```
opencode run --prompt "$(cat RUN_FLOW_IMAGE_GENERATOR_PROMPT.md)"
```
Or copy-paste into the agent chat interface.