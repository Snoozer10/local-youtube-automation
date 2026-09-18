# Product State: Autonomous YouTube Production Pipeline

## 1. Product Overview
An end-to-end, zero-cloud-SDK autonomous multimedia studio engineered to produce high-retention, broadcast-grade educational YouTube videos. Features an adaptive multi-niche engine (`GENERAL_EXPLAINER`, `AL_DAHEEH`, `SCIENCE_TECH`, `FINANCE`), automated neural TTS synthesis, Win32 Audacity DSP mastering, Faster-Whisper ASR alignment, 16:9 widescreen Google Flow visual generation, hardware-accelerated video compositing with procedural Ken Burns kinematics, and high-CTR thumbnail packaging with automated OCR text gates.

---

## 2. Core Functional Subsystems

| Pipeline Stage | Implementation Core | Output Artifacts | Quality Gates |
| :--- | :--- | :--- | :--- |
| **Phase 1: Transcreation** | `automate_all.py` (Gemini Pro) | `final_output.txt`, `Translation.docx` | $\ge 35\%$ Arabic ratio gate, command armor |
| **Phase 2: Dialect Refinement** | `refine_script.py` (Gemini Flash) | `refined_script.txt`, `tts_payload.json` | Meta-banter stripping, deterministic chunking |
| **Phase 3: Neural Voice Synthesis** | `src/youtube_automation/audio/tts_generator.py` | `voice_chapters/*.wav` | Multi-account HTTP 403 failover, $\ge 85\%$ coverage |
| **Phase 4: Audacity DSP Mastering** | `src/youtube_automation/audio/audacity_client.py` | `polished_chapters/*.wav` | Win32 Named Pipe IPC, NoiseGate, Compression, EBU R128 |
| **Phase 5: Lossless Audio Stitching** | `src/youtube_automation/audio/chapter_stitcher.py` | `full_episode_voice.wav` | Lossless WAV concatenation, 0.00s drift |
| **Phase 6: Speech Alignment & SSOT** | `src/youtube_automation/speech/transcriber.py` | `timeline.json`, SHA-256 sidecars | Faster-Whisper ASR, Silero VAD pause snapping |
| **Phase 7A: Roadmap & Prompt Planning** | `src/youtube_automation/orchestrator/roadmap_orchestrator.py` | `master_roadmap.jsonl`, `flow_prompts.json` | 6-part universal grammar, strict zero-text invariant |
| **Phase 7B: Visual Generation** | `src/youtube_automation/visuals/flow_generator.py` | `generated_images/*.png`, `studio_viewer.html` | Google Flow CDP loopback, Rolling SHA-256 ledger, backfill sweep |
| **Phase 8: Hardware Video Compositing** | `src/youtube_automation/video/compiler.py` | `youtube_ready_video.mp4`, 1080p/720p proxies | Intel QSV / libx264, Ken Burns smoothstep, 0.00s A/V drift |
| **Phase 9: High-CTR Thumbnail Packaging** | `generate_thumbnail.py` | `thumbnails/*.png`, `thumbnail_critique.json` | Title synergy, curiosity gap scoring, two-tier OCR gate |

---

## 3. Current Production Run: *What Do Animals Think Of Humans* (`vIqTRyX-cq0`)
- **Status**: 100% COMPLETE & VERIFIED.
- **Audio**: 602.267s master voiceover (44.1kHz mono 16-bit PCM).
- **Timeline**: 139 scenes, 18,057 video frames, 30.00 fps CFR.
- **Visuals**: 139 / 139 PNG frames (100% unique hashes, 0 text leaks).
- **Video**: 161.4 MB master (1080p, 602.27s), 86.1 MB 1080p proxy, 43.7 MB 720p proxy (0.00s drift).
- **Thumbnails**: 2 winning high-CTR variants (`title_1_thumbnail.png`, `title_3_thumbnail.png`).
