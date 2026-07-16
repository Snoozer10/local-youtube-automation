# YouTube Video Automation Pipeline — Developer Workflow

> **Developer-facing technical reference.** For user-facing quick start, see [README.md](README.md).

---

## Stack Summary

| Layer | Technology | Notes |
|-------|------------|-------|
| Language | Python 3.10+ | Windows only (hardcoded paths, `ctypes`, `CREATE_NEW_CONSOLE`) |
| Browser Automation | Playwright → Chrome/Opera CDP | `--remote-debugging-port=9222`, persistent profiles |
| AI Interaction | Gemini Web UI + AI Studio Speech | **No API keys** — all via browser automation |
| TTS | AI Studio Speech Playground | `aistudio.google.com/generate-speech` |
| Video | FFmpeg subprocess **or** MoviePy 2.x | Dual compile paths (see ADR-004) |
| Audio Polish | Audacity | Dual paths: PyAutoGUI (hotkeys) + Named Pipes (mod-script-pipe) |
| Notifications | Telegram Bot | Token in `gemini_model.txt` (gitignored) |

---

## Pipeline Overview (run_agency.py)

| Step | Script | Function | Checkpoint |
|------|--------|----------|------------|
| 1 | `automate_all.py` | Fetch YT transcript → break paragraphs → translate to Khaleeji Arabic via Gemini | `checkpoint.json` |
| 1b | `refine_script.py` | Refine Arabic: fluency, dialect consistency, hook, outro via Gemini CDP | `refine_checkpoint.json` |
| 2 | `generate_voice.py` | Dual-tab TTS: Tab 1=AI Studio Speech, Tab 2=Gemini Chat orchestrator (Bezier mouse + clipboard) | `voice_checkpoint.json` |
| 3 | `stitch_chapters.py` | Merge `Chapter_*.wav` → `full_episode_voice.wav` | — |
| 4 | `automate_audacity.py` | PyAutoGUI: launch Audacity, Ctrl+A → Ctrl+Shift+O (macro), poll FS for output | — |
| 5 | `transcribe_audio.py` | Named pipes (`\\.\pipe\ToSrvPipe`): per-chapter macro `Macro_Achird Gemini Voice cut and enhance` | — |
| 6 | `correct_transcript_spelling.py` | SequenceMatcher alignment: fix Whisper/ASR spelling via `final_output.txt` reference | — |
| 7a | `script_image_generator.py` | Storyboard → Gemini Web UI direct image gen (Playwright hover+download) | `planning_checkpoint.json` |
| 7b | `flow_image_generator.py` | Storyboard → Google Flow (base64 extraction via JS fetch) | `flow_workspace_url.txt` |
| 7c | `generate_thumbnail.py` | Concept extraction → Nano Banana Pro prompts → Gemini self-critique → top 2 variants | — |
| 8 | `fix_timestamps.py` | Conditional: inject timestamps from transcript into `flow_prompts.json` (auto-skips if present) | — |
| 9a | `compile_video.py` | FFmpeg: Ken Burns camera animations per `flow_prompts.json` (zoom/pan/static) | `concat.txt` + `temp_clips/` |
| 9b | `compile_video_with_moviepy.py` | MoviePy 2.x: SRT-synced image timeline (`.with_start()`/`.with_duration()`) | — |

> **Run:** `python run_agency.py` (full pipeline)  
> **Legacy:** `run.bat` — steps 1–5 only, **no** audacity/stitch/spellcheck/fixtimes  
> **Single-step rerun:** Safe — all scripts have JSON checkpoint/resume

---

## Architectural Decision Records (ADRs)

### ADR-001: All AI via Browser Automation (No API Keys)

**Status:** Accepted  
**Date:** 2024  
**Context:** Need to use Gemini (translation, image gen, TTS orchestration) and AI Studio Speech without API access.  
**Decision:** Automate `gemini.google.com` and `aistudio.google.com` via Playwright CDP against manually-signed-in browser profiles.  
**Consequences:**
- ✅ No API keys to manage/rotate/leak
- ✅ Access to latest UI features automatically
- ⚠️ Fragile to Google UI changes (`RESPONSE_SELECTOR = "model-response div.markdown"`)
- ⚠️ Requires manual browser login per profile
- ⚠️ Rate-limited by browser session, not API quota
- ⚠️ Account rotation via `ACTIVE_PROFILE_INDEX` cycling Chrome profiles 1→3

**Mitigation:** Shared utilities in `gemini_utils.py` (`find_input_box`, `wait_for_gemini_response`, `start_clean_gemini_chat`, `select_gemini_model`) extracted from `automate_all.py` to centralize selector logic.

---

### ADR-002: Dual Audacity Automation Paths

**Status:** Accepted  
**Context:** Audacity provides two automation interfaces with different trade-offs.  
**Decision:** Support both simultaneously for different pipeline stages.

| Aspect | `automate_audacity.py` (PyAutoGUI) | `transcribe_audio.py` (Named Pipes) |
|--------|-----------------------------------|--------------------------------------|
| Mechanism | Keystroke simulation (Ctrl+A, Ctrl+Shift+O) | `mod-script-pipe` (`\\.\pipe\ToSrvPipe`) |
| Trigger | Hotkey-bound macro (must pre-assign Ctrl+Shift+O) | Direct pipe command to named macro |
| Granularity | Whole file (`full_episode_voice.wav`) | Per-chapter (`Chapter_*.wav`) |
| Reliability | Fragile (focus, timing, UI changes) | Robust (programmatic API) |
| Prereqs | Audacity running, macro on hotkey | `mod-script-pipe` enabled, macro registered by name |

**Consequences:** PyAutoGUI path used for full-episode optimization (step 4); named pipes used for per-chapter enhancement + transcription (step 5). Both required.

---

### ADR-003: Dual Image Generation Paths

**Status:** Accepted  
**Context:** Two Google image generation UIs with different reliability/speed profiles.  
**Decision:** Support both, selectable via `IMAGE_GENERATOR_TYPE` in `gemini_model.txt`.

| Aspect | `script_image_generator.py` (Gemini UI) | `flow_image_generator.py` (Google Flow) |
|--------|----------------------------------------|------------------------------------------|
| Input | `pre_planned_prompts.txt` (text storyboard) | `flow_prompts.json` (JSON storyboard) |
| Extraction | Playwright hover → download button click | JS `fetch(img.src)` → base64 decode |
| Speed | Faster (direct UI) | Slower (Flow round-trip) |
| Reliability | Fragile (UI selectors) | Robust (stable Flow API) |
| Resume | Checkpoint by index | Saves/resumes Flow workspace URL |
| Duplicates | — | Saves to `generated_images_duplicates/` |

**Consequences:** Default to `flow` for reliability; `script` for speed when UI stable. Both respect stateless skip (existing PNG >100 bytes = skip).

---

### ADR-004: Dual Video Compilation Paths

**Status:** Accepted  
**Context:** Different output styles need different tooling.  
**Decision:** Maintain both FFmpeg (camera animations) and MoviePy (SRT timeline).

| Aspect | `compile_video.py` (FFmpeg) | `compile_video_with_moviepy.py` (MoviePy 2.x) |
|--------|----------------------------|-----------------------------------------------|
| Animation | Ken Burns: zoom_in/out, pan_left/right/static | None (static images) |
| Timing | `flow_prompts.json` per-frame camera moves | SRT subtitles drive image duration |
| Overrides | `manual_animations.txt` per-frame override | — |
| Output | `temp_clips/` per-frame MP4 → concat | Direct timeline composition |
| API | FFmpeg subprocess | MoviePy 2.x (`.with_start()`, `.with_duration()`) |

**Consequences:** FFmpeg path for "cinematic" feel; MoviePy for simple subtitle-synced slideshows. Select in `run_agency.py` pipeline config.

---

### ADR-005: Checkpoint/Resume Everywhere

**Status:** Accepted  
**Decision:** Every long-running script writes progress to JSON checkpoint in `youtube_runs/<Title>/`. On restart, resume from last saved state. Checkpoints delete on full success.

| Script | Checkpoint File | Tracks |
|--------|----------------|--------|
| `automate_all.py` | `checkpoint.json` | Paragraph translation index |
| `refine_script.py` | `refine_checkpoint.json` | Refinement turn index |
| `generate_voice.py` | `voice_checkpoint.json` | TTS chapter index |
| `script_image_generator.py` | `planning_checkpoint.json` | Storyboard prompt index |
| `flow_image_generator.py` | `flow_workspace_url.txt` | Google Flow workspace URL |
| `run_agency.py` | `pipeline.json` | Batch state machine (refine→voice→audacity→stitch→transcribe→spellcheck→images→fixtimes→video) |

**Consequences:** Safe to Ctrl+C and rerun any step. Clean room = delete `youtube_runs/<Title>/`.

---

### ADR-006: Windows-Only Hardcoded Paths

**Status:** Accepted (constraint)  
**Context:** Automation targets specific Windows app locations.  
**Hardcoded Paths:**
- Chrome: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- Opera: `C:\Program Files (x86)\Opera\...`, `%LOCALAPPDATA%\Programs\Opera\...`
- Chrome Debug Profile: `C:\ChromeDebugProfile`
- Opera Debug Profile: `C:\OperaDebugProfile`
- Audacity: `C:\Program Files\Audacity\Audacity.exe`
- Named Pipes: `\\.\pipe\ToSrvPipe` / `FromSrvPipe` (Windows-only)

**Consequences:** Not portable to Linux/macOS. WSL untested. Docker would require GPU passthrough + browser + Audacity — not viable.

---

### ADR-007: Account Rotation via Profile Index

**Status:** Accepted  
**Config:** `gemini_model.txt` → `ACTIVE_PROFILE_INDEX` (1–3), `SWITCH_ACCOUNTS_ENABLED`, `FAILOVER_RETRY_LIMIT`  
**Mechanism:** `utils.py` → `rotate_profile_index()` increments index, `map_profile_index()` maps to Chrome profile directory. On rate limit or error, `run_agency.py` triggers rotation.  
**Consequences:** Requires 3 pre-logged-in Chrome profiles. No programmatic login (2FA, captcha).

---

### ADR-008: Arabic Text Handling (UTF-8 Everywhere)

**Status:** Accepted  
**Decision:** All scripts handling Arabic: `sys.stdout.reconfigure(encoding='utf-8')` at top. JSON writes use `ensure_ascii=False`.  
**Consequences:** Required for correct Khaleeji Arabic output in transcripts, prompts, and JSON configs.

---

## Configuration Files (Project Root)

| File | Key Parameters | Notes |
|------|----------------|-------|
| `gemini_model.txt` | `VOICE_GENERATOR_MODEL`, `IMAGE_PLANNER_MODEL`, `FLOW_IMAGE_MODEL`, `IMAGE_RESET_LOOP_LIMIT`, `SWITCH_ACCOUNTS_ENABLED`, `ACTIVE_PROFILE_INDEX`, `FAILOVER_RETRY_LIMIT`, `BROWSER_TYPE`, `SCRIPT_BREAKER_MODEL`, `SCRIPT_TRANSLATOR_MODEL`, `FLOW_IMAGE_COUNT`, `IMAGE_GENERATOR_TYPE`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `REFINE_MODEL`, `THUMBNAIL_MODEL` | **Gitignored** — contains Telegram credentials |
| `video_config.txt` | `ENABLE_ANIMATIONS=true/false`, `ENABLE_SUBTITLES=true/false` | Toggles for video compile |
| `voice_option_notes.txt` | TTS model, temperature, voice, whisper model | Reference only |
| `prompt.txt` | Phase 1: paragraph breaking instructions | |
| `prompt_phase3.txt` | Phase 3: Khaleeji White Dialect translation style | |
| `refine_prompt.txt` | Refinement: fluency, dialect, hook, outro (two-turn) | |
| `TTS_PROMPT.txt` | Voice generation prosody architecture | |
| `visual_style.txt` | Visual style rules (local override per run folder) | |
| `visuals_plan.txt` | Storyboard blueprint (local override per run folder) | |

---

## Output Structure (`youtube_runs/<Video Title>/`)

```
youtube_runs/<Title>/
├── raw_transcript.txt              # Raw YouTube transcript
├── breaked_paragraphs.txt          # Gemini-parsed paragraphs
├── final_output.txt                # Translated paragraphs (Khaleeji Arabic)
├── refined_script.txt              # Refined Arabic script
├── refined_script.docx             # Word doc copy
├── timestamped_transcript.txt      # Whisper lines [MM:SS]
├── timestamped_transcript.srt      # SRT subtitles
├── image_timestamps.txt            # Alias of timestamped_transcript.txt
├── full_episode_voice.wav          # Stitched TTS audio
├── audacity_voice/
│   └── full_episode_voice.wav      # PyAutoGUI Audacity output
├── Chapter_*.wav                   # Per-chapter TTS
├── pre_planned_prompts.txt         # Storyboard (Gemini path)
├── flow_prompts.json               # JSON storyboard (Flow path)
├── generated_images/               # PNG images per timestamp
│   └── *.png
├── generated_images_duplicates/    # Extra copies from multi-gen
├── thumbnails/
│   └── variant_*.png               # Thumbnail variants
├── temp_clips/                     # Per-timestamp FFmpeg clips
├── concat.txt                      # FFmpeg concat list
├── youtube_ready_video.mp4         # Final output
├── flow_workspace_url.txt          # Google Flow resume URL
├── pipeline.json                   # run_agency.py batch state
└── *.json                          # Checkpoint files (auto-resume)
```

---

## Legacy / Reference Directories

| Path | Purpose |
|------|---------|
| `legacy_and_utilities/` | 11 inactive scripts (`get_transcript.py`, `script_image_generator_v2.py`, `script_pre_planner.py`, etc.) — historical reference only |
| `Implementation plans/` | `.md` docs for planned features — future reference |
| `.opencode/agent/AGENTS.md` | Duplicate of this file for OpenCode subagent — **keep in sync** |

---

## Development Commands

| Command | Purpose |
|---------|---------|
| `python run_agency.py` | Full pipeline (recommended) |
| `.\run.bat` | Legacy 5-step only (no audacity/stitch/spellcheck/fixtimes) |
| `python <script>.py` | Single-step rerun (checkpoints auto-resume) |
| Delete `youtube_runs/<Title>/` | Clean room reset |

---

## Debugging

- **Browser Inspection:** Attach to `localhost:9222` via Chrome DevTools — inspect CDP browser state during Gemini interactions
- **Logging:** All scripts use emoji-prefixed stdout markers: `✅` success, `⏭️` skip, `❌` error, `🔄` retry
- **Common breakage:** `RESPONSE_SELECTOR` breaks on Google UI updates — check `gemini_utils.py`

---

## Security

- **`gemini_model.txt` contains Telegram bot token** — **DO NOT COMMIT**. Listed in `.gitignore`.
- No API keys stored — all AI via browser automation.
- Account rotation cycles `ACTIVE_PROFILE_INDEX` across 3 Chrome profiles.
- Native clipboard via `ctypes.windll.user32/kernel32` (Windows-only, `generate_voice.py`).

---

## Common Pitfalls & Fixes

| # | Symptom | Cause | Fix |
|---|---------|-------|-----|
| 1 | "Input box not found" | Chrome not signed into Gemini **and** AI Studio | Sign into both before run |
| 2 | `RESPONSE_SELECTOR` timeout | Google UI changed markdown container | Update selector in `gemini_utils.py` |
| 3 | Audacity macro not found | `mod-script-pipe` disabled or macro name mismatch | Tools → Modules → enable; verify macro name `Macro_Achird Gemini Voice cut and enhance` |
| 4 | `generate_voice.py` hangs 300s | 250MB context limit on `wait_for_selector` | Restart browser profile; check `FAILOVER_RETRY_LIMIT` |
| 5 | Arabic JSON garbled | Missing `ensure_ascii=False` | Already handled in all scripts |
| 6 | `run.bat` used | Legacy script, missing steps 6–9 | Always use `python run_agency.py` |
| 7 | Profile index out of range | `ACTIVE_PROFILE_INDEX` > 3 | Reset to 1 in `gemini_model.txt` |
| 8 | FFmpeg concat fails | `temp_clips/` empty or naming mismatch | Check `flow_prompts.json` frame entries |
| 9 | MoviePy import error | MoviePy 1.x vs 2.x API mismatch | Requires MoviePy 2.x (`.with_start()`, `.with_duration()`) |
| 10 | Flow workspace URL stale | Google Flow session expired | Delete `flow_workspace_url.txt` to force new session |
| 11 | Thumbnail generation fails | Nano Banana Pro prompt format changed | Check `generate_thumbnail.py` prompt template |
| 12 | PyAutoGUI clicks wrong window | Audacity not focused / multiple instances | Ensure single Audacity instance; check `automate_audacity.py` focus logic |
| 13 | Named pipe connection refused | Audacity not running or `mod-script-pipe` disabled | Start Audacity manually first; verify pipe in Tools → Modules |

---

## Cross-References

- **User Quick Start:** [README.md](README.md)
- **Implementation Plans:** `Implementation plans/`
- **Legacy Scripts:** `legacy_and_utilities/`
- **OpenCode Agent Config:** `.opencode/agent/AGENTS.md` (mirror of this file)