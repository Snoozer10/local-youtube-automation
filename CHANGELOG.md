# Changelog

All notable changes to the `youtube-automation-pipeline` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
