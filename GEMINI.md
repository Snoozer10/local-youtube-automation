---
project_name: "youtube-automation-pipeline"
version: "4.3.0"
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
  - ".agents"
  - "debug_snapshots"
  - "docs/implementation_plans"
  - "docs/security_analysis"
last_indexed: "2026-09-09"
generator: "gemini-context-engineer/v4.0.0"
---

# Project Context: youtube-automation-pipeline

## 🎯 Project Overview
Automated video pipeline emulating the Egyptian/Khaleeji Arabic "Al-Daheeh" educational persona. Transcreates transcripts, synthesizes neural voiceovers, applies Audacity DSP, aligns speech via Faster-Whisper, orchestrates Gemini prompts via CDP, harvests visuals via Google Flow, and renders 1440p video via FFmpeg. Features PEP 517/518 packages in `src/youtube_automation/`, backward-compatible `_FacadeProxy` root shims, and pre-flight diagnostic drills in `exercises/`.

## 🏗️ Architecture & Component Mapping

```text
[Phase 1-2 Transcreation & Polish] ──► [Phase 3-5 TTS & Audacity DSP]
                  │                                   │
[Phase 8 Timeline SSOT & Fix]      ◄── [Phase 6-7 Whisper ASR & Spellcheck]
                  │
[Phase 9-10 Storyboard & Flow Visuals] ──► [Phase 11-13 Video & Thumbnail]
```

| Domain / Subsystem | Package Location | Facade / Entrypoint | Key Responsibility |
| :--- | :--- | :--- | :--- |
| Audio Synthesis & DSP | [audio/](src/youtube_automation/audio/) | [generate_voice](generate_voice.py), [audacity](automate_audacity.py), [stitch](stitch_chapters.py) | AI Studio TTS, Win32 Named Pipes DSP, lossless WAV stitch |
| Speech & Lexical Sync | [speech/](src/youtube_automation/speech/) | [transcribe](faster_whisper_transcribe_audio.py), [spellcheck](correct_transcript_spelling.py) | Faster-Whisper ASR, Silero VAD pause snap, monotonic spellcheck |
| Timeline SSOT | [timeline/](src/youtube_automation/timeline/) | [timeline_engine](timeline_engine.py), [fix_timestamps](fix_timestamps.py) | Canonical timeline.json, SHA-256 sidecars, timestamp repair |
| Visual Generation | [visuals/](src/youtube_automation/visuals/) | [flow_generator](flow_image_generator.py), [text_gate](text_gate.py) | Google Flow UI automation, continuity studio, OCR text gate |
| Hardware Video Render | [video/](src/youtube_automation/video/) | [compile_video](compile_video.py) | FFmpeg compositor, QSV (lookahead=0, nv12), Ken Burns, ASS |
| Browser CDP Engine | [browser/](src/youtube_automation/browser/) | [cdp_client](src/youtube_automation/browser/cdp_client.py), [gemini_utils](gemini_utils.py) | Port 9222 loopback binding, tab hygiene, Gemini web controls |
| Core Primitives | [core/](src/youtube_automation/core/) | [utils](utils.py) | Atomic disk writes, process lifecycle, profile rotation |
| Prompt & NLP Engines | [nlp/](src/youtube_automation/nlp/), [prompts/](src/youtube_automation/prompts/) | [json_sanitizer](json_sanitizer.py), [validator](validator.py) | Multi-tier LLM JSON repair, 8-part prompt validation |
| Pipeline Orchestrator | [orchestrator/](src/youtube_automation/orchestrator/) | [run_agency](run_agency.py), [roadmap](roadmap_orchestrator.py) | Batch scheduling, 25-row paged visual storyboard |
| Pedagogy & Diagnostics | [exercises/](exercises/) | [lint_exercises](tools/lint_exercises.py), [run.bat](run.bat) | 3-tier pedagogy drills (01-audio, 03-browser, 05-video) |

### Domain Lexicon & Ubiquitous Language
| Term | Canonical Meaning | Forbidden Synonyms / Overloaded Usage |
| :--- | :--- | :--- |
| `Timeline` | SSOT (`timeline.json`) via `timeline_engine.py` | "Word list", "Subtitles" |
| `VisualPrompt` | 8-part diffusion schema conforming to ADR 0004 | "Image prompt", "Description" |
| `Ken Burns` | Dynamic smoothstep pan-and-zoom in FFmpeg | "Zoom effect", "Slide" |
| `CDP Session` | Chrome DevTools Protocol bound to 127.0.0.1:9222 | "Browser tab", "Selenium" |
| `Transcreation` | 30/70 Egyptian/Khaleeji educational rewrite | "Machine translation" |
| `Facade Shim` | Root proxy (`_FacadeProxy`) syncing monkeypatches | "Wrapper hack", "Mock" |
| `Pre-flight Drill` | Diagnostic test (`@pytest.mark.drill`) for hardware | "Smoke test", "Dummy" |
| `Pedagogy Scaffold` | 3-tier structure (explainer/problem/solution) | "Sample code", "Sandbox" |

### Architectural Health & Deep Modules
| Module / Subtree | Interface Count | Implementation LOC | Leverage | Classification |
| :--- | :--- | :--- | :--- | :--- |
| [src/youtube_automation/timeline/fix_timestamps.py](src/youtube_automation/timeline/fix_timestamps.py) | 1 | 93 | 93.0 | Deep Module |
| [src/youtube_automation/nlp/json_sanitizer.py](src/youtube_automation/nlp/json_sanitizer.py) | 2 | 137 | 68.5 | Deep Module |
| [src/youtube_automation/speech/spelling_corrector.py](src/youtube_automation/speech/spelling_corrector.py) | 6 | 282 | 47.0 | Deep Module |
| [src/youtube_automation/video/ken_burns.py](src/youtube_automation/video/ken_burns.py) | 4 | 181 | 45.25 | Deep Module |
| [src/youtube_automation/visuals/text_gate.py](src/youtube_automation/visuals/text_gate.py) | 6 | 236 | 39.33 | Deep Module |

### Child Context Index
| Subtree / Scope | Context Path | Ownership & Purpose |
| :--- | :--- | :--- |
| `src/youtube_automation/` | [AGENTS.md](AGENTS.md) | Modular domain packages conforming to PEP 517/518 |
| `exercises/` | [AGENTS.md](AGENTS.md) | Pedagogy scaffold and pre-flight diagnostic drills |
| `.agents/skills/gemini-context-engineer/` | [.agents/skills/gemini-context-engineer/GEMINI.md](.agents/skills/gemini-context-engineer/GEMINI.md) | Context engineer skill specification |

## 🛑 Mandatory Engineering Constraints

### FerroxLabs Cognitive Non-Negotiables
- **Anti-Sycophancy**: Disagree with false user premises; never offer performative agreement.
- **Surgical Changes Only**: Modify strictly what is requested; avoid unrequested style churn.
- **Plausibility Is Not Correctness**: Untested code is assumed broken; verify with compiler, linter, or tests.

### Technical & Environmental Invariants
- **Intel QSV Compositing**: `QSV_LOOKAHEAD=0` (no lookahead with sw frames); `format=nv12` filter required for `h264_qsv` (yuv420p crashes); CFR frame math (`round(dur * fps)`); CLI >1000 chars written to `-filter_complex_script`.
- **Playwright CDP**: Bind strictly `127.0.0.1:9222`; kill port PID via `utils.kill_cdp_chrome`; prompt injection via `keyboard.insert_text` (fires React SyntheticEvents); turn handshake (stop button gone + 3x 500ms stable); 25-row roadmap pages (`ROADMAP_WINDOW_SIZE=25`). Angular CDK overlay menus portal to `div.cdk-overlay-container` (NOT children of trigger button); always dismiss `cdk-overlay-backdrop` before pointer interaction. Card-spawn handshake: record card count before submit, wait ≤20s for count increase before entering generation watchdog.
- **Flow Generation Watchdog**: Scoped to `active_card` (last card only); 120s stall ceiling → reload + re-inject; 360s hard ceiling → dump diagnostics + rotate account; error regex MUST include `reached your usage limit|you have not been charged`; always dump paired `.png` + `.html` on any stall.
- **Data & Subprocess Safety**: Canonical `timeline.json` SSOT; zero cloud SDKs (local CDP loopback only); subprocess args as `list` with `shell=False`; UTF-8 streams (`sys.stdout.reconfigure`); atomic disk writes (`NamedTemporaryFile` + `os.replace` + `fsync`).

## 🛠️ Common Workflows & CLI Commands
- Run unit test suite: `python -m pytest tests/unit -v`
- Run full test suite: `python -m pytest tests/ -v`
- Run hardware/daemon pre-flight drills: `python -m pytest exercises/ -v -m drill`
- Validate exercise pedagogy scaffold: `python tools/lint_exercises.py`
- Run pre-flight drills via wrapper: `run.bat test-drills`
- Run exercise linter via wrapper: `run.bat lint-exercises`
- Code formatting & linting: `ruff check src/ exercises/ tools/ --fix`
- Static type checking: `mypy src/`
- Run supervisor batch: `python run_agency.py`
- Run individual phases: `python automate_all.py` / `python compile_video.py`

### OpenCode Multi-Agent Orchestration & Quality Gates
- **Coordinator (Tier 1)**: Claude 3.7 Sonnet / Gemini Pro — spec design, refactor strategy.
- **Executor (Tier 2)**: Gemini Flash / DeepSeek V3 — fast TDD, linting, regression tests.
- **Quality Gates**: Unit tests green (`python -m pytest tests/unit`), clean lint (`ruff check`), exercise lint clean, drills green.

## 🔄 Active Workstreams & Verification Status
| ID | Workstream Slice | Status | Blocked By | Proof Command |
| :--- | :--- | :--- | :--- | :--- |
| `#1` | Audio DSP & Lossless Stitching | Done | - | `python -m pytest tests/unit/test_audacity_pipe_protocol.py` |
| `#2` | ASR Alignment & Timeline Sync | Done | `#1` | `python -m pytest tests/unit/test_timeline.py` |
| `#3` | Paged Storyboard & Prompts | Done | `#2` | `python -m pytest tests/unit/test_roadmap_orchestrator.py` |
| `#4` | Flow Visuals & Text Gate | Done | `#3` | `python -m pytest tests/unit/test_text_gate.py` |
| `#5` | Video Compositing & Ken Burns | Done | `#4` | `python -m pytest tests/unit/test_encoder.py` |
| `#6` | Post-Encode Validation & Sync | Done | `#5` | `python -m pytest tests/unit/test_post_encode_validation.py` |
| `#7` | Pedagogy Scaffold & Drills | Done | `#6` | `python tools/lint_exercises.py && python -m pytest exercises/ -v -m drill` |
| `#8` | DOX Docs & Quality Gate Audit | Done | `#7` | `python tools/lint_exercises.py && python -m pytest tests/ -v` |
| `#9` | Repo Cleanup & Consolidation | Done | `#8` | `python tools/lint_exercises.py && python -m pytest tests/ -v` |
| `#10` | Flow Generator Hardening v2 | Done | `#9` | `python -m py_compile src/youtube_automation/visuals/flow_generator.py && python -m pytest exercises/03-browser-cdp/03.03-flow-hydration-recovery/solution/test_exercise.py -v` |
| `#11` | Full Production Run (293 frames) | Done | `#10` | 293 PNGs in `generated_images/` + `youtube_ready_video.mp4` (1334.50s, 0.01s A/V drift) |

### Known Failure Modes & Project Learnings
- [LEARNING-001]: NEVER enable `look_ahead` on Intel QSV (`h264_qsv`) with sw-decoded frames; ALWAYS enforce `QSV_LOOKAHEAD=0`.
- [LEARNING-002]: NEVER feed `yuv420p` to `h264_qsv` (driver requires `nv12`); ALWAYS append `format=nv12` to filtergraph.
- [LEARNING-003]: NEVER assume Gemini SPA DOM mounts immediately; ALWAYS poll with 8s deadline & soft-fail fallback.
- [LEARNING-004]: NEVER use cloud AI SDKs; ALWAYS automate via Playwright CDP loopback (`127.0.0.1:9222`).
- [LEARNING-005]: NEVER run bare `pytest`; ALWAYS run `python -m pytest` so `tests/conftest.py` configures `sys.path`.
- [LEARNING-006]: NEVER use plain re-export shims; ALWAYS use `_FacadeProxy` with bidirectional monkeypatching sync.
- [LEARNING-007]: NEVER omit trailing commas in FFmpeg argument lists; ALWAYS assert explicit token boundaries.
- [LEARNING-008]: NEVER use `time.sleep()` inside Playwright polling loops; ALWAYS use `page.wait_for_timeout(ms)` to keep the CDP WebSocket transport pumped.
- [LEARNING-009]: NEVER query Angular CDK menu items as children of the trigger button; ALWAYS query `div.cdk-overlay-container [role='menuitem'], div.cdk-overlay-container button` — CDK portals menus to the document root.
- [LEARNING-010]: NEVER use a generic error regex in the generation watchdog; ALWAYS include `reached your usage limit|you have not been charged` — Flow quota errors render as card text, not `[role='alert']`, causing 120s silent stalls if undetected.
- [LEARNING-011]: NEVER check for progressbar immediately after pressing Enter; ALWAYS use a Card-Spawn Handshake (record pre-submit card count, poll ≤20s for count increase) to distinguish queue latency from true stall — prevents false double-submission re-triggers.
- [LEARNING-012]: NEVER scope `.animate-pulse` / skeleton checks globally; ALWAYS scope to `active_card` (last card locator) to avoid false "still loading" signals from historical generation cards re-animating on scroll.
