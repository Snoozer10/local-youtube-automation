<!-- AGENT-SYNC: GEMINI.md -->
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Project-specific workflow and DOX live in AGENTS.md; current guidance is in GEMINI.md; current session state is in docs/sessions/HANDOFF.md. Read these and the applicable task brief before work. Nested `AGENTS.md` files (e.g. `src/youtube_automation/production/AGENTS.md`, `tests/AGENTS.md`, `channels/AGENTS.md`) hold binding local contracts for their subtree.

For the user-authorized 2026-10-09 production delegation, the current test interpreter, pinned pytest redirect plugin, environment, scoped mypy command, and the specific exceptions to this file are defined in `docs/sessions/CLAUDE_FULL_COMPLETION_DELEGATION_20261009.md`; do not use stale test-count examples below to infer current branch status.

> Scope: `image_generation/` — `youtube-transcript-api` → Gemini CDP → AI Studio TTS → Audacity Named Pipes → Faster-Whisper → Google Flow → FFmpeg QSV/NVENC. Windows-only (`ctypes.windll`, `\\.\pipe\ToSrvPipe`, `CREATE_NEW_CONSOLE`). Python 3.10+, project `youtube-automation-pipeline`, setuptools, pip + `venv\` (no uv/poetry/Makefile). No cloud SDKs — all AI via Playwright CDP `127.0.0.1:9222`.

- Before tackling a task or investigating a problem, follow [Research before execution](AGENTS.md#research-before-execution): targeted web research, version checks, alternatives and an evidence receipt; explicit offline restrictions take precedence.

## Forbidden

- Never add cloud SDKs `google-generativeai`/`openai`/`anthropic`.
- Never `taskkill /IM chrome.exe` or terminate a process solely because it owns the CDP port. Terminate only the exact PID registered as pipeline-owned after revalidating process creation time, profile directory, listener, and lease.
- Never `input_value()` on contenteditable; follow Flow selector rules.
- Never destructive-overwrite checkpoints; schema changes need backward-compatible migration.
- `QSV_LOOKAHEAD=0` mandatory.
- Never commit `.env`, `runtime_state.json`, `*_checkpoint.json`, `pipeline.json`, video/WAVs.
- Do not modify: `youtube_runs/`, `venv/`, `legacy_and_utilities/`, `.agents/`, `.gemini/`, `.opencode/`, `.specify/`, `.superpowers/`, `graphify-out/`, `docs/`, `.env`, `*.json` checkpoints, `*.log`, browser profiles. Exception: when the user explicitly invokes `docs/sessions/CLAUDE_FULL_COMPLETION_DELEGATION_20261009.md`, follow only its named durable-doc edits and its existing staged-production outputs under `youtube_runs/`; preserve protected archives/checkpoints, use supported journaled publication, and leave Git/GitHub mutations to Codex.

## Setup — Windows PowerShell, order matters

```powershell
python -m venv venv; .\venv\Scripts\Activate.ps1   # repo uses venv\, not .venv
pip install -r requirements.txt
pip install -r requirements-dev.txt   # NOTE: has literal ``` fence lines (rows 1, 44) that break pip — flag, don't fix
python -m playwright install --with-deps
# Externals: FFmpeg/FFprobe on PATH (winget install Gyan.FFmpeg), Audacity 3.x → Preferences→Modules mod-script-pipe=Enabled, Chrome/Opera --remote-debugging-port=9222 --user-data-dir=C:\ChromeDebugProfile
copy .env.example .env   # fill TELEGRAM_*, CDP_PORT, model routing; ACTIVE_PROFILE_INDEX in runtime_state.json
```

- Runtime deps in `venv\`; `ruff/black/mypy/pytest` in global python. `pydantic>=2.0` required in both.

## Verify

```powershell
python -m pytest tests/unit -v                         # Historical generic example; active branch gate/plugin is in the current session brief
python -m pytest tests/unit/test_timeline.py -v        # single file; add ::test_name for a single test
python -m pytest exercises/ -v -m drill                # hardware & daemon pre-flight drills (run.bat test-drills)
python tools/lint_exercises.py                         # validate exercise pedagogy scaffold
ruff check .                                           # Do not auto-fix unreviewed working-tree changes
ruff format --check .                                  # pre-commit uses ruff-format
black --check --line-length 100 .
mypy src/youtube_automation/production --follow-imports=silent  # Scoped adaptive-production check; see current session brief
pre-commit run --all-files
```

- `pytest.ini` is the effective pytest config (it overrides `[tool.pytest.ini_options]` in pyproject): `pythonpath = src . tests`, `--import-mode=importlib`, `--strict-markers`, markers `unit`/`integration`/`drill`. Run from repo root. Integration tests need real `ffmpeg lavfi`.
- Prefer single-file runs while iterating; full suites for the final pass.

## Layout

- **Root facade shims → `src/youtube_automation/`.** Root entrypoints (`run_agency.py`, `automate_all.py`, `refine_script.py`, `generate_voice.py`, `automate_audacity.py`, `stitch_chapters.py`, `faster_whisper_transcribe_audio.py`, `correct_transcript_spelling.py`, `flow_image_generator.py`, `fix_timestamps.py`, `compile_video.py`, `generate_thumbnail.py`, …) delegate via `_FacadeProxy`, preserving legacy CLI syntax and monkeypatch transparency. Domain packages: `core, audio, speech, timeline, nlp, prompts, browser, visuals, video, orchestrator, production`.
- **Two pipelines coexist:**
  - **Legacy batch** — `run_agency.py` scans `youtube_runs/<Title>/` for `final_output.txt` and drives `pipeline.json` phases `translate, refine, voice, audacity, stitch, transcribe, images, fixtimes, video, thumbnail`.
  - **Adaptive multi-channel (opt-in, active development)** — `adaptive_production.py` → `src/youtube_automation/production/cli.py`. Explicit-run stages: `analyze → write | source-audio → plan → generate → report → preview → approve → render`, plus `status`. Example: `venv\Scripts\python.exe adaptive_production.py plan --run-dir "youtube_runs/<run>"` (`analyze` also takes `--channel-profile channels/<name>.json`). State and stage recipes live in a per-run SQLite ledger; channel profiles in `channels/*.json`. Contracts: `src/youtube_automation/production/AGENTS.md`; usage: `tasks/adaptive-visual-usage.md`; current revision: `tasks/professor-visual-playbook.md`.
- `exercises/` = pedagogy scaffold + `@pytest.mark.drill` pre-flight drills. `tools/` = `lint_exercises.py`, `extract_release_notes.py`. Tests in `tests/{unit,integration,mocks}` with `tests/conftest.py`.
- **Planning layer DAG (legacy):** `flow_image_generator.py` → `pipeline_manifest.py` → `json_sanitizer.py` → `validator.py` → `gemini_controller.py` → `roadmap_orchestrator.py` → `prompt_planner.py`. Strictly acyclic — never import upward. `validator.py` owns pure utils `flatten_visual_prompt_to_diffusion_text`/`enforce_arabic_in_prompt`/`purge_subtitle_phrases`.

## Pipeline execution & idempotency (legacy)

- **Supervisor:** skips completed `pipeline.json` flags, `clean_browser_tabs()` between phases, Telegram on crash/timeout. `compile_video.py` chunk 300s / final 3600s; `video`+`thumbnail` done → skip folder.
- **Toggles (`.env`):** `ENABLE_REFINE_SCRIPT`, `FLIP_AUDACITY_ORDER`, `IMAGE_GENERATOR_TYPE=flow|script`, `WHISPER_ENGINE=faster_whisper|hard_whisper`.
- **Images state machine:** `pipeline_manifest.json` gates resume. `script_hash=SHA256(transcript+template+presets)` mismatch invalidates caches. Chunk `{PENDING, VERIFIED, REPAIRED, FAILED}` — `FAILED` dumps `debug/malformed_chunk_N.json` then `ChunkPlanningError`. `master_roadmap.jsonl` is source of truth (migrates `master_roadmap.txt`); paging `ROADMAP_WINDOW_SIZE=25`, planning `FLOW_CHUNK_SIZE=15`.

## Config sources of truth (executable > prose)

- **`.env` + `.env.example`:** model routing `SCRIPT_BREAKER_MODEL` `SCRIPT_TRANSLATOR_MODEL` `VOICE_GENERATOR_MODEL` `IMAGE_PLANNER_MODEL` `REFINE_MODEL` `THUMBNAIL_MODEL`; TTS `TTS_MODEL` `TTS_VOICE_NAME` `TTS_TEMPERATURE` `TTS_PROACTIVE_RELOAD_INTERVAL`; Flow `FLOW_IMAGE_MODEL` `FLOW_IMAGE_COUNT` `FLOW_ASPECT_RATIO` `FLOW_DISABLE_AGENT` `FLOW_CHUNK_SIZE` `GEMINI_SESSION_RESET_THRESHOLD`; `CDP_PORT=9222` `BROWSER_TYPE` `FAILOVER_RETRY_LIMIT`. `ACTIVE_PROFILE_INDEX` lives in `runtime_state.json` via `utils.rotate_profile_index()`.
- **`video_config.txt`:** `2560x1440@30` `yuv420p` `high@5.1`, `CHUNK_SIZE=20`, `QSV_LOOKAHEAD=0`, Ken Burns `1.0-1.08 smoothstep upscale 1.12`, VBV `35000k/70000k`, `FFMPEG_THREADS=4`, audio `320k/48k I-14 TP-1 LRA11`. CPU fallback `libx264 veryfast crf17 tune animation`.
- **`transcribe_config.txt`:** `WHISPER_MODEL_SIZE=small` `WHISPER_LANGUAGE=ar` VAD on, image 2.2s/3.5s/4.8s 5-12 words, subs 4/2 words gap 0.35s, `IMAGE_PAUSE_SPLIT 0.40s`; `image_timestamps.txt` is the sync anchor.
- **`daheeh_config.json` + `docs/audit_rubric.md`:** 30/70 Fusha/Amiya, 1-3-1 Provost cadence, Tashkeel `كِدَه, بِيُقول, هُوبَّا, قِسط`, 10-point audit. `refine_script.py` strips `<thinking>`/`<slang_ledger>`.

## Gotchas — would miss without help

- **QSV:** `QSV_LOOKAHEAD=0` — `>0` starves the pool on sw-decoded inputs. `format=nv12` for QSV else `yuv420p`; fallback `h264_qsv → h264_nvenc → libx264` via `ffmpeg -encoders`.
- **FFmpeg filter graphs:** long graphs go to `temp_clips/filter_chunk_*.txt` and load via `-/filter_complex <file>` (both legacy `video/compiler.py` and adaptive `production/render.py`); the deprecated `-filter_complex_script` is absent in CI's FFmpeg. Zero-drift `frame_count=round(duration*30)`, clip 0 at frame 0, CFR `fps_mode cfr`. WinGet FFmpeg via `%LOCALAPPDATA%\Microsoft\WinGet\Links`.
- **CDP:** `127.0.0.1:9222`, not `localhost` (IPv6 fails). Kill only the PID on the port via `kill_cdp_chrome(port)` (`netstat -ano` + `taskkill /F /T /PID`). `launch_browser_with_profile` wipes `SingletonLock` and verifies `http://127.0.0.1:{port}/json/version`.
- **Gemini injection/completion:** `gemini_controller.inject_prompt_via_cdp` ladder (`insert_text`→clipboard Ctrl+V→`execCommand`→`fill()` only <500 chars) + ≥95% `inner_text()` gate before submit. Completion = `wait_for_gemini_turn_completion`: stop-absent + 3× stability@500ms HARD, action-bar SOFT. Ephemeral chat per roadmap page + per chunk (+jitter 1.5-3s). Pages fixed 25 lines — never tail-merge. Validator WEAK `TS[i]≤TS[i+1]`; equal TS ⇒ strict `index`+`frame_index`.
- **Gemini polling:** never `time.sleep`. `gemini_utils.wait_for_gemini_response`: stop absent + 5× stable reads + last `model-response` `len>=1`; fast-fail on error card. Strip `Gemini said`/`قال Gemini`, handle `Analyzing/Thinking/Visualizing`.
- **Audacity:** `\\.\pipe\ToSrvPipe`/`FromSrvPipe`, every cmd ends `\n`, read until empty line. Always `SelectAll:` before DSP. Sync `YouTube_Voice_Optimizer.txt` → `%APPDATA%\audacity\macros\`; wipe `SessionData`/`AutoSave` before open.
- **Flow selectors (validated 2026-08-20):** cascade only. `wait_for_flow_app_ready` 3s post-hydration. Submit `button:has(i.google-symbols:text-is('arrow_forward'))` (+ Enter fallback). `Describe your character` = `textarea[placeholder*='Describe your character']` or contenteditable `innerText`; `+ New Character` only on empty gallery. Body popup = LAST `contenteditable` floating card. Never fill workspace bar `What do you want to create?`. Mount verified via `/character/<id>` + `Done`. Assets memoized `flow_assets_profile_*.json` + `flow_workspace_url_profile_*.txt`; `SUMMON_ASSET` via `Search assets`→`Add to Prompt`.
- **Images:** tiered `base64 data: → page.request.get() → blob fetch in-page → de-hovered screenshot`. Never `<canvas>` primary (CORS-tainted); use `img_locator.screenshot(type="png")` after `mouse.move(100,15)`. Validate `>20KB`, PIL verify, `>100px`, PNG `89 50 4E 47`/JPEG `FF D8`.
- **Voice:** Bezier mouse, MD5 dedup across `Chapter_N.wav` (delete+reload if `N==N-1`), proactive reload every `TTS_PROACTIVE_RELOAD_INTERVAL`.
- **Subprocess & UTF-8:** list args + `shell=False`; all JSON/text `encoding="utf-8"` `ensure_ascii=False`; `sys.stdout.reconfigure(encoding='utf-8')` + `chcp 65001`.
- **Config writes:** atomic `NamedTemporaryFile`+`os.replace`+`fsync`.

## Subagent task matrix

| Task | Root Facade Entrypoint | Domain Package Module | Checklist |
| --- | --- | --- | --- |
| Linguistic Transcreation | `automate_all.py` | `automate_all.py` | 30/70 ratio + academic fallback on safety block |
| Script Doctor Polish | `refine_script.py` | `refine_script.py` | `daheeh_config.json` Tashkeel; strip `<thinking>`/`<slang_ledger>` |
| Voice Synthesis | `generate_voice.py` | `src/youtube_automation/audio/tts_generator.py` | Bezier mouse; MD5 dedup; `voice_generation_manifest.json` |
| DSP Mastering | `automate_audacity.py` | `src/youtube_automation/audio/audacity_client.py` | Named Pipes alive; `SelectAll:` before effects |
| Audio Stitching | `stitch_chapters.py` | `src/youtube_automation/audio/chapter_stitcher.py` | Lossless Wave frames, zero drop |
| ASR & Cadence Pacing | `faster_whisper_transcribe_audio.py` | `src/youtube_automation/speech/transcriber.py` | 3-6 words/chunk; VAD `0.40s`; `transcribe_config.txt` |
| Lexical Spellcheck | `correct_transcript_spelling.py` | `src/youtube_automation/speech/spelling_corrector.py` | `difflib.SequenceMatcher` vs `refined_script.txt`, timestamps untouched |
| Timeline SSOT | `timeline_engine.py` | `src/youtube_automation/timeline/engine.py` | Single source of truth for `timeline.json` |
| Timestamp Fix | `fix_timestamps.py` | `src/youtube_automation/timeline/fix_timestamps.py` | Monotonic audio-aligned timestamp reconciliation |
| Roadmap Paging | `roadmap_orchestrator.py` | `roadmap_orchestrator.py` | Fixed 25-row pages; anchor = last row K-1; atomic jsonl rewrite/page |
| JSON Planning | `prompt_planner.py` | `src/youtube_automation/nlp/json_sanitizer.py` | Slice ±1 buffer; ephemeral session; self-heal ≤2 same-session |
| Visual Generation | `flow_image_generator.py` | `src/youtube_automation/visuals/flow_generator.py` | `@asset` chip injection; native screenshot; continuity |
| Text Collision Gate | `text_gate.py` | `src/youtube_automation/visuals/text_gate.py` | Multi-layer OCR text filter before saving images |
| Video Compositing | `compile_video.py` | `src/youtube_automation/video/compiler.py` | Zero-drift frames; `-/filter_complex`; QSV→NVENC→CPU |
| Ken Burns Motion | `compile_video.py` | `src/youtube_automation/video/ken_burns.py` | Speech-paced dynamic smoothstep zoom & pan math |
| Thumbnail | `generate_thumbnail.py` | `generate_thumbnail.py` | Self-critique scoring, 2 variants |
| Adaptive Production | `adaptive_production.py` | `src/youtube_automation/production/` | Follow `production/AGENTS.md`; explicit `--run-dir`; preview approval before render |

## Domain lexicon

| Term | Canonical Meaning | Forbidden Synonyms |
| :--- | :--- | :--- |
| `Timeline` | Authoritative `timeline.json` managed by `timeline_engine.py` | "Word list", "Subtitle timing" |
| `VisualPrompt` | Validated 8-part diffusion prompt schema (ADR 0004) | "Image description", "Prompt string" |
| `Ken Burns` | Smoothstep pan-and-zoom applied in the FFmpeg filtergraph | "Zoom effect", "Slide animation" |
| `CDP Session` | Chrome DevTools Protocol connection bound to 127.0.0.1:9222 | "Browser tab", "Selenium session" |
| `Transcreation` | Fusha/Amiya educational Arabic rewrite emulating Al-Daheeh persona | "Direct translation", "Machine translation" |
| `Facade Shim` | Root module shim (`_FacadeProxy`) delegating to `src/` and syncing monkeypatches | "Wrapper hack", "Mock import" |
| `Pre-flight Drill` | `@pytest.mark.drill` test verifying live hardware (QSV) or daemons (Audacity, CDP) | "Smoke test", "Dummy test" |
| `Pedagogy Scaffold` | Three-tier `explainer`/`problem`/`solution` structure under `exercises/` | "Sample code", "Sandbox" |

Full glossary: `CONTEXT.md`; decisions: `docs/adr/`.

## Style & workflow

- `black --line-length 100`, `ruff` `E,W,F,I,B,C4,UP`, `mypy --strict --ignore-missing-imports` (all in `pyproject.toml`). Fix with `ruff check --fix` + `ruff format`.
- **OpenCode:** `opencode.json` → `default_agent: AGENTS-PROJECT`; `AGENTS.md` via `instructions`.
- **Git:** `youtube_runs/`, `legacy_and_utilities/`, `.agents/`, `.opencode/`, `graphify-out/` gitignored. Never auto-commit video/WAVs.
- **Issues:** GitHub Issues in Snoozer10/local-youtube-automation (`docs/agents/issue-tracker.md`); labels in `docs/agents/triage-labels.md`.
- **References:** `README.md` (quickstart, pipeline flow), `docs/audit_rubric.md` (broadcast quality gate).

## Project Learnings

When the user corrects your approach, append a concrete one-line rule here ("Always use X for Y"). Tighten an existing line instead of duplicating; remove lines whose issue is gone.

- (empty)
