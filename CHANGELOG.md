# Changelog

All notable changes to the `youtube-automation-pipeline` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [4.4.0] - 2026-09-18

### Added
- **Dynamic Multi-Niche Architecture (`niche_engine.py`)**: Completely decoupled pipeline visual generation from single hardcoded personas, introducing an extensible registry of niches (`GENERAL_EXPLAINER`, `SCIENCE_TECH`, `FINANCE_ECONOMICS`, `HISTORY_GEOPOLITICS`, `PHILOSOPHY_ESSAY`, `CULTURE_COMEDY`) and modular channel profiles with configurable host modes (`NONE`, `CUSTOM_AVATAR`, `DOCUMENTARY_OBSERVER`).
- **Inverted Pyramid Universal Prompt Grammar**: Restructured diffusion prompt tokens into 4 prioritized attentional zones, positioning subject scale and dynamic action within the first 35 tokens to eliminate cross-attention semantic attenuation.
- **AudioTransientDetector & Procedural Kinematics**: Implemented short-time RMS onset flux detection with +33.3ms optical lag compensation (aligning cross-modal perception), discrete scale punches ($Y=360\text{px}$ eye-line elevation), and zero-safe clamped Ken Burns drift on holds $\ge 3.5\text{s}$.
- **Two-Substrate Studio Visual Engine**: Consolidated visual backgrounds into `#2A2420` dark mahogany workbench (host studio) and `#F8F8FA` neutral drafting limbo desk (diagrammatic plates) following the 60-30-10 chromatic attention law, eliminating 15-cut retinal luminance whiplash.
- **Interactive Side-by-Side Studio Viewer (`studio_viewer.html`)**: Interactive comparison tool featuring dynamic relative path resolution, kinetic action badges (`⚡ Scale Punch`, `🎥 Linear Push`, `👁️ Eye-Line Lock`), and chunk filtering.
- **High-CTR Thumbnail Optimization Matrix**: Deployed 5 curiosity gap archetypes (Novelty, Result, Story, Transformation, Moment), 1-second mobile scan rule, and automated two-tier OCR text collision self-healing with strengthened negative re-synthesis.
- **Multi-Bitrate Proxy Ladder**: Automated generation of `youtube_ready_video_1080p.mp4` (high-bitrate web proxy) and `youtube_ready_video_720p.mp4` (mobile proxy) during video compilation.
- **Script Ratio Language Gate**: Added $\ge 35\%$ Arabic character density assertion and regex meta-chatter stripping in `automate_all.py` to reject conversational review responses from LLM chats.

### Changed
- **Universal 16:9 Long-Form Composition**: Replaced 24mm wide-angle optical model with an orthographic flat 2D projection plane and explicit coordinate boundaries (X: 180 to 1740, Y: 90 to 980), banishing wide-angle barrel distortion and text leaks.
- **Google Flow Candidate Selection**: Hardened visual scraping to query tiles across page and sort ascending by $(y, x)$, selecting top-of-feed prepended cards and eliminating historical stale card duplicates.
- **Resilient Gap-Skipping**: Updated batch generation to treat transient queue latency as non-fatal skips, accompanied by a single-pass deterministic post-batch backfill sweep.
- **Audacity Cold-Boot Resilience**: Expanded Win32 Named Pipe connection timeout to an 80s polling window with a 6.0s grace period for Windows cold-boot stability.
- **TTS Network Transport**: Injected `--disable-quic` and deterministic DNS IP pinning to prevent UDP packet drops during multi-chapter AI Studio speech synthesis.

### Fixed
- **Timeline SSOT Read-Only Invariant**: Fixed `fix_timestamps.py` to preserve canonical `timeline.json` immutability, updating prompt schemas without sidecar desynchronization.
- **Table Delimiter Parsing in Gemini SPA**: Updated Markdown table parser in `roadmap_orchestrator.py` to support both tab (`\t`) and pipe (`|`) delimiters from rendered HTML `<table>` elements.
- **Angular CDK Asset Drawer Handshake**: Implemented bidirectional wheel scrolling (`-600`, `+600`) and single-click auto-attach detection in `summon_character_chip`.
- **FFmpeg Thread Thrash Guard**: Capped parallel video encoding workers to 1 on 4-core systems to prevent CPU thread context-switch thrash.
- **Type Hint Latent NameError Guard (`ken_burns.py`)**: Imported `Any` from `typing` in `derive_multishot_crop` to prevent latent runtime `NameError` under non-evaluated type-hinting environments.
- **Test Suite Code Quality & Invariant Parity (`tests/unit/`)**: Resolved 43 Ruff errors across unit tests (import order, unused imports, ambiguous variable `l` -> `line`, and explicit `zip(..., strict=...)` guards).
- **Package Manifest Version Synchronization**: Synchronized package version to `4.4.0` across `pyproject.toml`, `GEMINI.md`, and `CHANGELOG.md`.

### Verified
- **Autonomous 10-Phase Production Milestone (197 / 200, 98.5% Pass)**: Executed full autonomous production run on `vIqTRyX-cq0` (*What Do Animals Think Of Humans*):
  - Master voiceover: 602.267s (44.1kHz mono 16-bit PCM, $\Delta = 0.000\text{s}$ chapter stitch).
  - Canonical timeline: 139 scenes, 18,057 video frames, 30.00 fps CFR.
  - Flow visuals: 139/139 PNG frames on disk, 139 unique SHA-256 hashes (zero collisions, zero text leaks).
  - Broadcast video: 161.4 MB master (1080p, 602.267s, **exact 0.00s A/V drift**).
  - High-CTR thumbnails: 2 winning variants verified via automated OCR collision gates.

## [4.3.0] - 2026-09-12

### Added
- **Google Flow SPA Hydration Recovery**: Added `wait_for_flow_input_box` with 15s deadline pumping CDP WebSocket transport via `page.wait_for_timeout(300)` instead of `time.sleep()`.
- **Card-Spawn Handshake**: Introduced pre-submission card count tracking and a 20s handshake window to distinguish queue latency from true generation stalls, eliminating false double-submission re-triggers.
- **Angular CDK Overlay Portaling Interaction**: Refactored Google Flow model and output settings to portal into root `div.cdk-overlay-container`, clearing blocking `cdk-overlay-backdrop` overlays.
- **Quota & Rate-Limit Error Fast-Failover**: Added card error regex matching (`reached your usage limit`, `you have not been charged`), instantly triggering account rotation instead of 120s silent timeouts.
- **Two-Tier Watchdog & Paired Diagnostic Dumper**: Scoped generation activity watching to `active_card` with a 120s stall ceiling, 360s hard ceiling, and atomic dual `.png` + `.html` DOM diagnostic artifact dumps.
- **Formulative Pedagogy Drill 03.03**: Implemented `exercises/03-browser-cdp/03.03-flow-hydration-recovery/` with 9 deterministic pytest tests verifying SPA hydration delays, transient modal dismissal, quota detection, and card spawn handshakes.

### Changed
- **Anti-Occlusion Browser Flags**: Added `--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling` and `--disable-background-media-suspend` to Chrome launch flags to prevent Windows DWM from throttling background CDP tasks.
- **Safe Mouse Coordinates**: Updated `wake_up_page()` target coordinates to safe `(100, 15)` to avoid accidental toolbar button clicks.

### Verified
- **Full Production Milestone (22.24 Minutes)**: Completed 100% end-to-end production for *Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!* (57 mastered voice chapters, 293 storyboard frames generated via Google Flow with self-healing recovery at Frame 264, 15/15 video chunks compiled into 1440p master video `youtube_ready_video.mp4` with 0.01s audio-visual drift).

## [4.2.0] - 2026-09-07

### Added
- **PEP 517/518 Modular Package Architecture**: Reorganized monolithic scripts into authoritative modular domain packages under `src/youtube_automation/` (`core`, `audio`, `speech`, `timeline`, `nlp`, `prompts`, `browser`, `visuals`, `video`, `orchestrator`).
- **Transparent Root Facade Proxies (`_FacadeProxy`)**: Implemented backward-compatible dynamic proxy shims at repository root (`compile_video.py`, `flow_image_generator.py`, `generate_voice.py`, `automate_audacity.py`, `stitch_chapters.py`, etc.) ensuring zero CLI regressions and dynamic bidirectional monkeypatch synchronization.
- **Formulative Pedagogy Drills Scaffold**: Added the initial 3-tier pedagogy scaffold with 6 hardware and daemon diagnostic pre-flight drills in `exercises/`:
  - `01-audio-dsp`: `01.01-tts-chapter-slicing` and `01.02-audacity-named-pipe-ipc`
  - `03-browser-cdp`: `03.01-cdp-connection-and-lifecycle` and `03.02-turn-completion-detector`
  - `05-hardware-video-compositing`: `05.01-qsv-hardware-encoder-probe` and `05.02-ken-burns-smoothstep-math`
- **Scaffold Linter Tooling**: Created `tools/lint_exercises.py` to enforce strict pedagogy structure, directory conventions, and link integrity.
- **Automated Windows Setup Wizards**: Added `setup.ps1` and `setup.bat` for automated environment verification, FFmpeg/Audacity prerequisite checks, and virtual environment provisioning.
- **Deterministic Release Notes Slicer**: Added `tools/extract_release_notes.py` for automated extraction of Keep a Changelog sections.

### Changed
- **Test Suite Modernization**: Migrated test suites from legacy `.tests/` to standardized `tests/unit/` conforming to `pytest.ini`.
- **CI/CD Quality Gates**: Updated `.github/workflows/ci.yml` and `run.bat` to include `test-drills` and `lint-exercises` verification commands.

### Security
- **Hardened Git Boundaries**: Blocked secret leaks, browser profiles, and runtime artifacts via updated `.gitignore`.

## [4.1.0] - 2026-09-04

### Added
- **Canonical Timeline SSOT**: Unified all sync sources into `timeline.json` managed exclusively by `timeline_engine.py` with immutable `words[]` and VAD pause-snapped `spans[]` (PR #14, `84f4084`, ADR 0001).
- **Sidecar Checksum Verification**: Added fail-closed SHA-256 sidecar validation for all generated timeline and shim artifacts (`2451319`).
- **3-Span Windowed Prompt Planner**: Context-aware prompt generation with style-preserving continuity across scene boundaries (PR #16, `05ff9b7`, ADR 0003).
- **Speech-Paced Ken Burns Modulation**: Dynamically scales Ken Burns camera motion velocity based on `words_per_second` speech density (`89526e0`).
- **Strict Negative Prompt & Thumbnail OCR Gate**: Injected strict negative prompt preventing embedded text in thumbnails, backed by OCR text collision checking with one-shot retry and failed asset purging (`dc22c52`).
- **Script Hash Checkpoint Invalidation**: Automatic invalidation of downstream pipeline checkpoints when script content changes via SHA-256 tracking (`56c5674`).

### Changed
- **8-Part Diffusion Prompt Schema**: Upgraded prompt schema to strict 8-part compositional structure enforced by Pydantic validators (`a143a13`).
- **Dynamic Duration Scaling**: Refactored Ken Burns pan/zoom to use integer frame budget guarantees (`d={frames}`, `trim=end_frame={frames}`) ensuring zero-drift CFR alignment (`c78b0e2`, `79eb323`).
- **Strict CDP Port Binding**: Hardened browser tab cleanup routines to bind strictly to `http://127.0.0.1:{cdp_port}`, eliminating DNS rebinding and ambiguous localhost resolution (`56c5674`).

### Fixed
- **Timeline Invalidation Bug**: Fixed stale checkpoint reuse by invalidating compile caches when timeline hash changes (PR #17, `3698a89`).
- **Zero-Division in Ken Burns Calculation**: Added guard against division-by-zero when calculating speech pace on silent audio spans (`89526e0`).
- **Post-Encode Audio-Visual Desync**: Implemented post-encode validation gate verifying output video frame counts against timeline audio duration within 1 frame tolerance (`c78b0e2`).

## [4.0.0] - 2026-09-03

### Added
- Complete automated end-to-end video pipeline emulating Al-Daheeh educational persona (`run_agency.py`).
- Neural Arabic transcreation and Tashkeel vocalization engine (`automate_all.py`, `refine_script.py`).
- Playwright CDP loopback voice synthesis via Edge TTS (`generate_voice.py`).
- Lossless Audacity DSP mastering bridge via Named Pipes protocol (`automate_audacity.py`, ADR 0005).
- Faster-Whisper ASR alignment with Voice Activity Detection (VAD) splitting (`faster_whisper_transcribe_audio.py`).
- Fuzzy Levenshtein spellchecker aligning ASR transcript with original script (`correct_transcript_spelling.py`).
- Paged visual storyboard orchestrator with fixed 25-row Gemini paging (`roadmap_orchestrator.py`).
- Multi-tier JSON sanitizer and schema validator for LLM prompt recovery (`json_sanitizer.py`, `validator.py`).
- Multi-layer text collision gate checking Flow visual assets (`text_gate.py`, ADR 0004).
- Intel QSV hardware-accelerated video compositing engine with dynamic Ken Burns pan/zoom (`compile_video.py`, ADR 0002).
- Dual YouTube thumbnail generator (`generate_thumbnail.py`).

### Changed
- Refactored five cyclomatic complexity hotspots across pipeline orchestration modules.
- Hardened FFmpeg CLI filtergraph generation using `-filter_complex_script` chunks for commands exceeding 1,000 chars.
- Enforced zero-drift CFR math (`fps_mode cfr`, `frame_count = round(duration * fps)`).

### Fixed
- Comprehensive hardening batch addressing ERR-01 through ERR-18 (CDP timeouts, named pipe deadlocks, UTF-8 Windows console crashes).
- Resolved Gemini submission trigger deadlocks and SPA DOM mounting wait states.
- Fixed Whisper timestamp schema validation tolerances in `validator.py`.
- Fixed hardware encoder crashes caused by software-decoded frames by enforcing `format=nv12` and `QSV_LOOKAHEAD=0`.

### Security
- Mandated Zero Cloud SDK Policy (`google-generativeai`, `openai`); all cloud AI interactions routed via local CDP loopback.
- Enforced local loopback host binding (`127.0.0.1:9222`) across all Playwright sessions.
