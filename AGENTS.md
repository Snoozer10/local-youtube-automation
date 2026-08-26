# AGENTS — YouTube Al-Daheeh Automation Pipeline

## CRITICAL RULES - MUST FOLLOW

### RESPONSES

- Keep responses concise and to the point - unless the user asks otherwise

### PLANNING MODE

- Always ask clarifying questions
- Never assume design, tech stack or features
- Use deep-dive sub-agents to assist with research
- Use deep-dive sub-agents to review the different aspects of your plan before presenting to the user

### CHANGE / EDIT MODE

- Never implement features yourself when possible - use sub-agents!
- Identify changes from the plan that can be implemented in parallel, and use sub-agents to implement the features efficiently
- When using sub-agents to implement features, act as a coordinator only
- Use the best model for the task - premium models for complex tasks (like coding) and mid-tier models for simpler tasks, like documentation
- After completing features (large or small), always run commands like lint and type check to check code quality

## YouTube Al-Daheeh Automation Pipeline

> Scope: `image_generation/` workspace (`youtube-transcript-api` → Gemini CDP → AI Studio TTS → Audacity Named Pipes → Faster-Whisper → Google Flow → FFmpeg QSV/NVENC). Windows-only (`ctypes.windll`, `\\.\pipe\ToSrvPipe`, `CREATE_NEW_CONSOLE`). Python 3.10+ (see `pyproject.toml:11`). No cloud SDKs — never add `google-generativeai`/`openai`/`anthropic`; all AI via Playwright CDP `127.0.0.1:9222`.

### Stack & repo boundaries

- **Single-package monorepo.** No multi-package workspace. Real entrypoints: `run_agency.py` (supervisor) or single-phase scripts: `automate_all.py` → `refine_script.py` → `generate_voice.py` → `stitch_chapters.py`/`automate_audacity.py` → `faster_whisper_transcribe_audio.py` → `correct_transcript_spelling.py` → `flow_image_generator.py` (or `script_image_generator.py`) → `fix_timestamps.py` → `compile_video.py` → `generate_thumbnail.py`. See `README.md:207` + `Project-workflow.md:5`.
- **State belongs to `youtube_runs/<Title>/` (gitignored).** Never commit `.env`, `gemini_model.txt`, `runtime_state.json`, or `*_checkpoint.json`/`pipeline.json`. Batch mode: `run_agency.py` scans `youtube_runs/` for `final_output.txt` folders and drives `pipeline.json` state machine (`translate, refine, voice, audacity, stitch, transcribe, images, fixtimes, video, thumbnail` in `run_agency.py:66`).
- **Gemini planning layer (2026-08 refactor):** `flow_image_generator.py` main() delegates planning/state to `pipeline_manifest.py` → `json_sanitizer.py` → `validator.py` → `gemini_controller.py` → `roadmap_orchestrator.py` → `prompt_planner.py`. DAG strictly acyclic — never import upward. `validator.py` owns the relocated pure text utils (`flatten_visual_prompt_to_diffusion_text`, `enforce_arabic_in_prompt`, `purge_subtitle_phrases`); fig keeps aliases. Flow rendering code is untouched by this layer.

### Setup (Windows PowerShell, order matters)

```powershell
python -m venv venv; .\venv\Scripts\Activate.ps1   # actual dir is venv\ — README's .venv is aspirational
pip install -r requirements.txt       # NOTE: file currently wrapped in markdown ``` fences + trailing prose — sanitize to plain reqs first or pip chokes
pip install -r requirements-dev.txt   # ruff, black, mypy, pytest-cov, bandit, types-*  (pyproject.toml:34 dev)
python -m playwright install --with-deps
# Externals: FFmpeg/FFprobe on PATH (winget install Gyan.FFmpeg), Audacity 3.x → Preferences→Modules set mod-script-pipe=Enabled, Chrome/Opera with --remote-debugging-port=9222 --user-data-dir=C:\ChromeDebugProfile
copy .env.example .env   # fill TELEGRAM_*, CDP_PORT, model routing; ACTIVE_PROFILE_INDEX migrated to runtime_state.json (utils.py:269)
```

- **Env split reality:** runtime deps live in `venv\`; pytest/ruff/black/mypy are installed in the GLOBAL python only. `pydantic>=2.0` required at runtime since the 2026-08 refactor (installed both places).

### Verify (run before concluding any refactor)

```powershell
python -m pytest tests/unit -v                         # CI scope — ci.yml:35; full = python -m pytest tests/ -v
python -m pytest tests/unit/test_timeline.py -v        # single-file example
python -m pytest tests/ --cov=. --cov-report=term-missing
ruff check . --fix
ruff format --check .          # pre-commit uses ruff-format, not black directly
black --check --line-length 100 .  # pyproject.toml:55 line-length 100, exclude youtube_runs/venv
mypy .                         # strict + ignore_missing_imports (pyproject.toml:93)
pre-commit run --all-files     # ruff, ruff-format, mypy --strict, trailing-whitespace, check-json/yaml/toml
```

- Always invoke tests as `python -m pytest ...` from repo root — bare `pytest` fails because `tests/conftest.py` imports need cwd on `sys.path`.
- Green baseline (2026-08-26): unit 170 passed / integration 17 passed. Integration suite shells out to real ffmpeg lavfi — skips/fails without it.
- `pyproject.toml` top-level `[tool.ruff] select/ignore` emits a deprecation warning under ruff ≥0.16 (pre-existing, harmless).

### Pipeline execution & idempotency

- **Supervisor:** `run_agency.py` batch state machine skips completed `pipeline.json` flags, calls `clean_browser_tabs()` between phases, sends Telegram on crash/timeout. `compile_video.py` `Chunk 300s / Final 3600s` timeouts; `video`+`thumbnail` done → skip folder entirely (`run_agency.py:154`).
- **Never destructive-overwrite** `pipeline.json`/`checkpoint.json`/`refine_checkpoint.json`/`voice_generation_manifest.json`/`compile_checkpoint.json`/`audacity_checkpoint.json`/`planning_checkpoint.json` without user confirmation. Schema changes require backward-compatible migration (see `CLAUDE.md:242`).
- **Phase toggles (`.env`):** `ENABLE_REFINE_SCRIPT=true` (skip phase 2 if false), `FLIP_AUDACITY_ORDER=false` (default polish→stitch), `IMAGE_GENERATOR_TYPE=flow|script`, `WHISPER_ENGINE=faster_whisper|hard_whisper` (`run_agency.py:164`).
- **Images phase state machine (2026-08 refactor):** `youtube_runs/<Title>/pipeline_manifest.json` gates resume. `script_hash = SHA256(transcript + prompt-template + presets)`; mismatch ⇒ auto-invalidates roadmap+planning caches. Chunk statuses `{PENDING, VERIFIED, REPAIRED, FAILED}` — FAILED dumps raw model output to `debug/malformed_chunk_N.json`, then halts via `ChunkPlanningError`. `master_roadmap.jsonl` is the source of truth (`master_roadmap.txt` legacy auto-migrates; corrupt ⇒ regenerate). Paging: `ROADMAP_WINDOW_SIZE=25`; planning: `FLOW_CHUNK_SIZE=15`.

### Config sources of truth (executable > prose)

- **`.env` + `.env.example` (78 lines):** model routing `SCRIPT_BREAKER_MODEL=Flash` / `SCRIPT_TRANSLATOR_MODEL=Pro` / `VOICE_GENERATOR_MODEL=Flash` / `IMAGE_PLANNER_MODEL=Flash` / `REFINE_MODEL=Flash` / `THUMBNAIL_MODEL=Pro`; TTS `TTS_MODEL=gemini-2.5-pro-preview-tts`, `TTS_VOICE_NAME=Achird`, `TTS_TEMPERATURE=1.1`, `TTS_PROACTIVE_RELOAD_INTERVAL=40`; Flow `FLOW_IMAGE_MODEL=Nano Banana 2 Lite`, `FLOW_IMAGE_COUNT=1x`, `FLOW_ASPECT_RATIO=16:9`, `FLOW_DISABLE_AGENT=true`, `FLOW_CHUNK_SIZE=15`; CDP `CDP_PORT=9222`, `BROWSER_TYPE=chrome`, `FAILOVER_RETRY_LIMIT=3`. `ACTIVE_PROFILE_INDEX` lives in `runtime_state.json` via `utils.rotate_profile_index()` (`utils.py:303`).
- **`video_config.txt`:** `OUTPUT 2560x1440@30` `yuv420p` `high@5.1`, `CHUNK_SIZE=20`, `QSV_LOOKAHEAD=0`, Ken Burns `ZOOM 1.0-1.08 smoothstep upscale 1.12`, VBV `35000k/70000k`, `FFMPEG_THREADS=4`, `AUDIO 320k/48k Loudnorm I-14 TP-1 LRA11`. CPU fallback `libx264 preset veryfast crf 17 tune animation`.
- **`transcribe_config.txt`:** `WHISPER_MODEL_SIZE=small`, `WHISPER_LANGUAGE=ar`, `VAD true`, chunking `IMAGE_MIN 2.2s TARGET 3.5s MAX 4.8s / 5-12 words`, pause split `0.40s` (`transcribe_config.txt:31`). `image_timestamps.txt` is the sync anchor produced by `faster_whisper_transcribe_audio.py`.
- **`daheeh_config.json:8` + `audit_rubric.md`:** 30% Fusha / 70% Amiya ratio, 1-3-1 Provost cadence, Tashkeel lexicon (`كِدَه, بِيُقول, هُوبَّا, قِسط`), 10-point broadcast audit. `refine_script.py` strips `<thinking>`/`<slang_ledger>` XML.

### Gotchas — would miss without help

- **QSV starvation:** `QSV_LOOKAHEAD=0` mandatory (`compile_video.py:46`, `video_config.txt:23`) — `>0` starves hardware frame pool on sw-decoded inputs. Always `format=nv12` for QSV else `yuv420p`; auto-fallback `h264_qsv → h264_nvenc → libx264` probed via `ffmpeg -encoders` (`compile_video.py:227`).
- **FFmpeg CLI 32KB limit:** filter graphs >1K chars written to `temp_clips/filter_chunk_*.txt` and invoked via `-filter_complex_script` (`compile_video.py:1000`). Zero-drift integer math `frame_count = round(duration*30)`, clip 0 forced to frame 0, CFR `fps_mode cfr` (`compile_video.py:726`). WinGet FFmpeg injected via `%LOCALAPPDATA%\Microsoft\WinGet\Links` (`compile_video.py:15`).
- **CDP socket:** connect to `127.0.0.1:9222` not `localhost` (IPv6 fails). Kill only PID on port via `kill_cdp_chrome(port)` (`netstat -ano` + `taskkill /F /T /PID >100`, poll 4s) — never blind `taskkill /IM chrome.exe` (`utils.py:123`). `launch_browser_with_profile` wipes `SingletonLock/SingletonSocket/lockfile` and verifies `http://127.0.0.1:{port}/json/version` (`utils.py:255`). `localhost` still lurks in `run_agency.clean_browser_tabs:57`, `generate_voice.py:1015`, `script_image_generator.py:667`, `automate_all.py:250/463`.
- **Gemini planning injection/completion (2026-08 refactor):** prompts go through `gemini_controller.inject_prompt_via_cdp` ladder (`keyboard.insert_text` → clipboard grant+Ctrl+V → `execCommand('insertText')` → `fill()` only <500 chars) with a mandatory ≥95% `inner_text()` readback gate BEFORE submit — never `input_value()` on contenteditable, never bare `fill()` on big payloads. Completion = tri-factor handshake (`wait_for_gemini_turn_completion`): stop-absent + 3× stability@500ms are HARD; action-bar is SOFT — never hard-gate cosmetic selectors. Ephemeral fresh chat per roadmap page AND per chunk (+1.5–3.0s jitter). Roadmap pages are FIXED-SIZE 25-line slices — never tail-merge (a 49-row page hits the ~50-60 row truncation ceiling). Validator enforces WEAK timestamp monotonicity: `TS[i]≤TS[i+1]`; equal TS ⇒ strict `index`+`frame_index` progression.
- **Gemini polling:** never `time.sleep` poll. `gemini_utils.wait_for_gemini_response` waits for stop button absent + 5 consecutive stable reads (~5-6s) + `len>=1` on last `model-response` node; fast-fails on error card (`gemini_utils.py:372`). Strip `Gemini said`/`قال Gemini` prefix, handle transient `Analyzing/Thinking/Visualizing` placeholders.
- **Audacity IPC:** `\\.\pipe\ToSrvPipe`/`FromSrvPipe`, every command ends `\n`, read until empty line (`\n` terminator). Always `SelectAll:` before DSP. Presets synced from `YouTube_Voice_Optimizer.txt` → `%APPDATA%\audacity\macros\`; wipe `SessionData`/`AutoSave` before pipe open to avoid recovery modals (`CLAUDE.md:105`).
- **Google Flow (hard-won selector facts, validated 2026-08-20):** cascade selectors — never single. `wait_for_flow_app_ready` 3s stability after `goto`/hydration. Submit = `button:has(i.google-symbols:text-is('arrow_forward'))` (zero svg buttons — `button:has(svg)` fails, need Enter fallback). `Describe your character` = `textarea[placeholder*='Describe your character']` or contenteditable whose `innerText` contains it; `+ New Character` card only empty-gallery (templates screen if non-empty). Body popup = LAST `div[contenteditable=true]` (floating card). Never fill workspace bar `What do you want to create?` (creates regular image, not character). Editor mount ≤3s verified via `/character/<id>` + `Done` button. Assets memoized per `flow_assets_profile_*.json` + workspace URL `flow_workspace_url_profile_*.txt`; `SUMMON_ASSET` adds `@Character` via search `Search assets` → card → `Add to Prompt`.
- **Images:** tiered extraction `base64 data: → page.request.get() (auth cookies) → blob: fetch in-page → de-hovered atomic screenshot` (`flow_image_generator.py:226`). Never `<canvas>` blob primary (tainted CORS); use `img_locator.screenshot(path, type="png")` after `page.mouse.move(100,15)` de-hover. Validate with `validate_image_file` (`>20KB`, PIL verify, `>100px`, PNG `\x89PNG`/JPEG `\xff\xd8` fallback).
- **Voice synthesis:** Bezier mouse physics, MD5 hash duplicate detection across `Chapter_N.wav` (delete+reload tab if identical to N-1), proactive reload every `TTS_PROACTIVE_RELOAD_INTERVAL=40` (`generate_voice.py` + `CLAUDE.md:284`).
- **Subprocesses & UTF-8:** list args + `shell=False` always. All JSON/text `encoding="utf-8"` `ensure_ascii=False`; every script `sys.stdout.reconfigure(encoding='utf-8')` + `chcp 65001` on Windows to avoid Arabic `???`.
- **Config writes:** `utils.update_config_value` atomic `NamedTemporaryFile`+`os.replace`+`fsync`; same pattern for `runtime_state.json` (`utils.py:282`).

### Subagent task matrix (mandatory verification)

| Task                     | Script                               | Checklist                                                                  |
| ------------------------ | ------------------------------------ | -------------------------------------------------------------------------- |
| Linguistic Transcreation | `automate_all.py`                    | 30/70 ratio + academic fallback on safety block                            |
| Script Doctor Polish     | `refine_script.py`                   | `daheeh_config.json` Tashkeel; strip `<thinking>`/`<slang_ledger>`         |
| Voice Synthesis          | `generate_voice.py`                  | Bezier mouse; MD5 dedup; Achievement: `voice_generation_manifest.json`     |
| DSP Mastering            | `automate_audacity.py`               | Named Pipes alive; `SelectAll:` before effects                             |
| Audio Stitching          | `stitch_chapters.py`                 | lossless Wave frames, zero drop                                            |
| ASR & Cadence Pacing     | `faster_whisper_transcribe_audio.py` | 3-6 words/chunk; VAD split `0.40-0.45s`; `transcribe_config.txt`           |
| Lexical Spellcheck       | `correct_transcript_spelling.py`     | `difflib.SequenceMatcher` vs `refined_script.txt`, timestamps untouched    |
| Roadmap Paging           | `roadmap_orchestrator.py`            | fixed 25-row pages; anchor = exact last row of K-1; atomic jsonl rewrite/page |
| JSON Planning            | `prompt_planner.py`                  | slice ±1 buffer rows; single-turn ephemeral session; self-heal ≤2 same-session |
| Visual Generation        | `flow_image_generator.py`            | `@asset` chip injection; native screenshot capture; multi-frame continuity |
| Thumbnail                | `generate_thumbnail.py`              | self-critique scoring, 2 variants                                          |
| Video Compositing        | `compile_video.py`                   | zero-drift frames; `filter_complex_script`; QSV→NVENC→CPU fallback         |

### Style & workflow

- **Formatter/linter/type:** `black --line-length 100` (exclude `youtube_runs,venv,.git,__pycache__` — `pyproject.toml:54`), `ruff` `E,W,F,I,B,C4,UP` (`pyproject.toml:72`), `mypy --strict --ignore-missing-imports` (`pyproject.toml:93`). Fix with `ruff check --fix` + `ruff format`.
- **OpenCode:** `opencode.json` → `default_agent: AGENTS-PROJECT`; lean-ctx shadow mode active; `AGENTS.md` consumed via `instructions`. Caveman mode default; drop articles/filler for agent comms, code/commits normal.
- **Git:** `youtube_runs/`, `Implementation plans/`, `Security Division Analysis/`, `.agents/`, `.opencode/`, `graphify-out/` gitignored. Commit only via user-initiated flow; never auto-commit compiled video or WAVs.

### References (deep invariants)

- `CLAUDE.md` — full 425-line architecture, DOM recovery matrix, Ken Burns math, Audacity protocol.
- `README.md` — user quickstart, master pipeline flow, output hierarchy.
- `Project-workflow.md` — ADRs, IPC diagram, fault-tolerance table.
- `audit_rubric.md` — 10-point broadcast quality gate.
