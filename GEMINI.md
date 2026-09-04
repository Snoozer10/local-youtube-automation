---
project_name: "youtube-automation-pipeline"
version: "4.1.0"
tech_stack:
  - "python"
  - "playwright"
  - "faster-whisper"
  - "ffmpeg"
  - "audacity"
  - "pydantic"
rules:
  - "qsv-lookahead-zero"
  - "nv12-hardware-format"
  - "cdp-loopback-binding"
  - "timeline-canonical-truth"
  - "zero-cloud-sdks"
  - "atomic-disk-writes"
exclude_paths:
  - "youtube_runs"
  - "venv"
  - "legacy_and_utilities"
  - "assets"
last_indexed: "2026-09-03"
generator: "gemini-context-engineer/v4.0.0"
---

# Project Context: youtube-automation-pipeline

## 🎯 Project Overview
Automated video pipeline emulating the Egyptian/Khaleeji Arabic "Al-Daheeh" educational persona. Transcreates YouTube transcripts, synthesizes neural voiceovers, applies Audacity DSP mastering, aligns speech with Faster-Whisper, orchestrates Gemini storyboard prompts via CDP, harvests visuals via Google Flow, and renders HD video via FFmpeg hardware acceleration on Windows.

## 🏗️ Architecture & Component Mapping
```text
[Phase 1: Transcreation] ──► [Phase 2: Script Polish] ──► [Phase 3: TTS Synthesis]
                                                                  │
[Phase 6: Whisper ASR]   ◄── [Phase 5: Audio Stitch]  ◄── [Phase 4: Audacity DSP]
       │
       ▼
[Phase 7: Spellcheck]    ──► [Phase 8: Timeline Engine] ─► [Phase 9: Roadmap & Prompts]
                                                                  │
[Phase 12: FFmpeg Render] ◄── [Phase 11: Timestamp Fix] ◄── [Phase 10: Visual Harvesting]
       │
       ▼
[Phase 13: Thumbnail Gen]
```

| Component | File Path | Responsibility |
| :--- | :--- | :--- |
| Supervisor | [run_agency.py](run_agency.py) | Batch orchestrator for pipeline.json |
| Translation | [automate_all.py](automate_all.py) | Transcreation to 30/70 Arabic |
| Polish & Tashkeel | [refine_script.py](refine_script.py) | Tashkeel vocalization & cleanup |
| TTS Voice | [generate_voice.py](generate_voice.py) | Neural TTS via browser CDP |
| DSP Audio | [automate_audacity.py](automate_audacity.py) | Audacity Named Pipes DSP |
| Audio Stitch | [stitch_chapters.py](stitch_chapters.py) | Lossless WAV concatenation |
| ASR Alignment | [faster_whisper_transcribe_audio.py](faster_whisper_transcribe_audio.py) | Whisper ASR with VAD splitting |
| Spellcheck | [correct_transcript_spelling.py](correct_transcript_spelling.py) | Fuzzy spellcheck against script |
| Timeline SSOT | [timeline_engine.py](timeline_engine.py) | SSOT manager for 	imeline.json |
| Visual Roadmap | [roadmap_orchestrator.py](roadmap_orchestrator.py) | Fixed 25-row storyboard roadmap |
| Prompt Planner | [prompt_planner.py](prompt_planner.py) | Visual prompt planner with buffer |
| JSON Sanitizer | [json_sanitizer.py](json_sanitizer.py) | Multi-tier repair for LLM JSON |
| Prompt Validator | [validator.py](validator.py) | Pydantic schema validator |
| Text Gate | [text_gate.py](text_gate.py) | OCR text collision gate |
| Asset Harvesting | [flow_image_generator.py](flow_image_generator.py) | Visual generation via Flow CDP |
| Timestamp Repair | [fix_timestamps.py](fix_timestamps.py) | Aligns timestamps with audio |
| Compositing | [compile_video.py](compile_video.py) | FFmpeg compositing & Ken Burns |
| Thumbnail | [generate_thumbnail.py](generate_thumbnail.py) | Dual thumbnail generation |
| Video Config | [video_config.txt](video_config.txt) | Encoder, loudnorm & zoom config |
| ASR Config | [transcribe_config.txt](transcribe_config.txt) | Whisper model & VAD config |
| Persona Config | [daheeh_config.json](daheeh_config.json) | Persona lexicon & dialect config |
### Domain Lexicon & Ubiquitous Language
| Term | Canonical Meaning | Forbidden Synonyms / Overloaded Usage |
| :--- | :--- | :--- |
| `Timeline` | Authoritative single source of truth (`timeline.json`) managed by `timeline_engine.py` | "Word list", "Subtitle timing" |
| `VisualPrompt` | Validated 8-part diffusion prompt schema strictly conforming to ADR 0004 | "Image description", "Prompt string" |
| `Ken Burns` | Dynamic smoothstep pan-and-zoom transformation applied in FFmpeg filtergraph | "Zoom effect", "Slide animation" |
| `CDP Session` | Chrome DevTools Protocol WebSocket connection bound strictly to 127.0.0.1:9222 | "Browser tab", "Selenium session" |
| `Transcreation` | Fusha/Amiya educational Arabic rewrite emulating Al-Daheeh persona | "Direct translation", "Machine translation" |

### Architectural Health & Deep Modules
| Module / Subtree | Interface Count | Implementation LOC | Leverage | Classification |
| :--- | :--- | :--- | :--- | :--- |
| [fix_timestamps.py](fix_timestamps.py) | 1 | 93 | 93.0 | Deep Module |
| [json_sanitizer.py](json_sanitizer.py) | 2 | 137 | 68.5 | Deep Module |
| [correct_transcript_spelling.py](correct_transcript_spelling.py) | 6 | 207 | 34.5 | Deep Module |
| [flow_image_generator.py](flow_image_generator.py) | 90 | 2803 | 31.14 | Deep Module |
| [run_agency.py](run_agency.py) | 14 | 333 | 23.79 | Deep Module |

### Child Context Index
| Subtree / Scope | Context Path | Ownership & Purpose |
| :--- | :--- | :--- |
| `.agents/skills/gemini-context-engineer/` | [.agents/skills/gemini-context-engineer/GEMINI.md](.agents/skills/gemini-context-engineer/GEMINI.md) | Agent skill for context engineering and GEMINI.md lifecycle |

## 🛑 Mandatory Engineering Constraints

### FerroxLabs Cognitive Non-Negotiables
- **Anti-Sycophancy**: Disagree with false user premises; never offer performative agreement.
- **Surgical Changes Only**: Modify strictly what is requested; avoid unrequested style churn.
- **Plausibility Is Not Correctness**: Untested code is assumed broken; verify with compiler, linter, or tests.

### Technical & Environmental Invariants
- **Intel QSV & Hardware Compositing**:
  - `QSV_LOOKAHEAD=0`: Never enable lookahead with software-decoded frames (causes memory exhaustion).
  - `format=nv12`: Filtergraphs targeting `h264_qsv` must append `format=nv12` (yuv420p crashes with `Invalid FrameType:0`).
  - Zero-drift frame math: Enforce CFR (`fps_mode cfr`), clip 0 at frame 0, `frame_count = round(duration * fps)`.
  - FFmpeg 32KB CLI limit: Filtergraphs >1,000 chars written to `temp_clips/filter_chunk_*.txt` via `-filter_complex_script`.
- **Playwright CDP & Browser Automation**:
  - Host binding: Always bind `127.0.0.1:9222` (never `localhost`).
  - Process teardown: Kill by port PID via `utils.kill_cdp_chrome` (never global `taskkill /IM chrome.exe`).
  - Prompt injection ladder: `insert_text` -> Clipboard Ctrl+V -> `execCommand` with >=95% `inner_text()` readback check.
  - Turn completion handshake: Stop button absence + 3x stability checks at 500ms.
  - Roadmap paging: Fixed 25-row pages (`ROADMAP_WINDOW_SIZE=25`), anchor = exact last row of page K-1.
- **Data, Subprocess & Environment Safety**:
  - Canonical timeline: `timeline_engine.py` is single source of truth for `timeline.json`.
  - Zero Cloud SDK Policy: Zero cloud SDKs (`google-generativeai`, `openai`); all cloud AI runs via CDP loopback.
  - Subprocess safety: Always pass command arguments as a `list` with `shell=False`.
  - UTF-8 console streams: Force Windows streams via `sys.stdout.reconfigure(encoding="utf-8")`.
  - Atomic disk writes: State files (`pipeline.json`, checkpoints) written via `NamedTemporaryFile` + `os.replace` + `fsync`.

## 🛠️ Common Workflows & CLI Commands
- Run unit test suite: `python -m pytest tests/unit -v`
- Run full test suite: `python -m pytest tests/ -v`
- Code formatting & linting: `ruff check . --fix`
- Static type checking: `mypy .`
- Run supervisor batch: `python run_agency.py`
- Run individual phases: `python automate_all.py` / `python compile_video.py`
- Run context verification: `python .agents/skills/gemini-context-engineer/scripts/validate_gemini_md.py GEMINI.md --strict --reality`
- Verify workstream proofs: `python .agents/skills/gemini-context-engineer/scripts/verify_proofs.py --file GEMINI.md --workstream <ID>`

### OpenCode Multi-Agent Orchestration & Quality Gates
- **Coordinator (Tier 1)**: Claude 3.7 Sonnet / Gemini Pro — spec design, refactor strategy.
- **Executor (Tier 2)**: Gemini Flash / DeepSeek V3 — fast TDD, linting, regression tests.
- **Quality Gates**: Unit tests green (`python -m pytest tests/unit`), clean lint (`ruff check`), zero-warning validation (`validate_gemini_md.py --strict --reality`).

## 🔄 Active Workstreams & Verification Status
| ID | Workstream Slice | Status | Blocked By | Proof Command |
| :--- | :--- | :--- | :--- | :--- |
| #1 | Audio Mastering & Lossless Stitching | Done | - | python -m pytest tests/unit/test_audacity_pipe_protocol.py |
| #2 | ASR Alignment & Timeline Sync | Done | #1 | python -m pytest tests/unit/test_timeline.py |
| #3 | Paged Storyboard & Prompt Planning | Done | #2 | python -m pytest tests/unit/test_roadmap_orchestrator.py |
| #4 | Flow Asset Harvesting & Text Gate | Done | #3 | python -m pytest tests/unit/test_text_gate.py |
| #5 | Hardware Video Compositing & Ken Burns | Done | #4 | python -m pytest tests/unit/test_encoder.py |
| #6 | Post-Encode Validation & Compositing Sync | Done | #5 | python -m pytest tests/unit/test_post_encode_validation.py |

### Known Failure Modes & Project Learnings
- [LEARNING-001]: NEVER enable `look_ahead` on Intel QSV (`h264_qsv`) with sw-decoded frames (causes memory exhaustion & corruption); ALWAYS enforce `QSV_LOOKAHEAD=0`.
- [LEARNING-002]: NEVER feed `yuv420p` directly to `h264_qsv` (driver requires `nv12`); ALWAYS append `format=nv12` to the filtergraph before encoding.
- [LEARNING-003]: NEVER assume Gemini SPA DOM mounts immediately post-reset; ALWAYS use up to 8s polling deadline and resilient soft-failure fallback.
- [LEARNING-004]: NEVER use cloud AI SDKs (`google-generativeai`, `openai`); ALWAYS drive web sessions via local Playwright CDP loopback (`127.0.0.1:9222`).
- [LEARNING-005]: NEVER run bare `pytest`; ALWAYS execute via `python -m pytest` from repository root so `tests/conftest.py` properly configures `sys.path`.
