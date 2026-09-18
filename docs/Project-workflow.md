# 🛠️ YouTube Video Automation Pipeline — Developer Technical Workflow

> **Developer-Facing Architecture Reference.** For the user-facing quick start and setup guide, see [README.md](../README.md).

---

## 🏗️ Architecture & Stack Matrix

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             MASTER SUPERVISOR (run_agency.py)                    │
│   • Batch State Machine (pipeline.json)  • Multi-Profile CDP Rotation (utils.py) │
│   • Process & Socket Sanitation          • Telegram Bot Alerts                   │
└────────┬─────────────────────────────────┬────────────────────────────────┬──────┘
         │                                 │                                │
         ▼                                 ▼                                ▼
┌───────────────────┐             ┌───────────────────┐            ┌───────────────────┐
│ LINGUISTIC ENGINE │             │  AUDIO DSP MATRIX │            │  VISUALS & VIDEO  │
├───────────────────┤             ├───────────────────┤            ├───────────────────┤
│ • automate_all.py │             │ • generate_voice  │            │ • flow_image_gen  │
│   (30/70 Hybrid)  │             │   (AI Studio TTS) │            │   (Google Flow)   │
│ • refine_script   │             │ • stitch_chapters │            │ • generate_thumb  │
│   (1-3-1 Cadence) │             │ • automate_audacity│           │   (CTR Matrix)    │
│ • daheeh_config   │             │   (Named Pipes)   │            │ • compile_video   │
│   (Tashkeel DB)   │             │ • faster_whisper  │            │   (QSV / NVENC)   │
└───────────────────┘             └───────────────────┘            └───────────────────┘
```

| Layer                       | Implementation                         | Developer Technical Notes                                                                                                                          |
| :-------------------------- | :------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Runtime Environment**     | Python 3.10+ (Windows 10/11 x64)       | Relies on `ctypes.windll` (native Win32 clipboard), Named Pipes IPC, and Win32 process creation flags (`CREATE_NEW_CONSOLE`).                      |
| **Browser CDP Engine**      | Playwright Sync API                    | Connects over Chrome DevTools Protocol (`127.0.0.1:9222`) to control authenticated browser profiles. **No API keys or billed tokens**.             |
| **Linguistic Transcreator** | Gemini 2.5 Pro / Flash                 | 30/70 Fusha/Amiya hybrid code-switching, 1-3-1 sentence cadence, anti-translatese filters, and automated diacritic injection.                      |
| **Voice Synthesis**         | AI Studio Speech Playground            | Drives `gemini-2.5-pro-preview-tts` (Voice: _Achird_, Temp: _1.1_ via `.env:TTS_TEMPERATURE`). Uses Bezier mouse emulation and MD5 hash caching to detect stale audio. |
| **Audio Mastering**         | Audacity 3.x Scripting Pipe            | Non-blocking Win32 named pipes (`\\.\pipe\ToSrvPipe` & `\\.\pipe\FromSrvPipe`) for deterministic multiband DSP mastering.                          |
| **ASR & Synchronization**   | Faster-Whisper + SequenceMatcher       | Word-level alignment with VAD filtering; spelling alignment against refined scripts via `difflib.SequenceMatcher`.                                 |
| **Visual Diffusion Engine** | Google Flow (Nano Banana 2 / Imagen 3) | Master Visual Roadmap generation, JSON keyframe matrices, and DOM-level continuity chaining via "Add to prompt" card injection.                    |
| **Video Compositor**        | FFmpeg 5+ (Direct Subprocess)          | Hardware-accelerated (Intel QSV `h264_qsv` / NVIDIA `h264_nvenc` / CPU `libx264` fallback) Ken Burns engine at 1440p/1080p with EBU R128 loudnorm. |
| **Observability & Alerts**  | Telegram Bot API                       | Asynchronous webhook notifications for pipeline completions, step progress, fatal crashes, and account failovers.                                  |

---

## 🔁 Complete 10-Phase Pipeline Lifecycle

Every phase writes stateful progress to `youtube_runs/<Cleaned_Title>/`:

```
youtube_runs/<Cleaned_Title>/
├── raw_transcript.txt                   # Raw YouTube caption dump
├── breaked_paragraphs.txt               # Structured narrative paragraphs
├── final_output.txt                     # Phase 1 transcreated conversational Arabic
├── refined_script.txt                   # Phase 2 polished script with Tashkeel
├── refined_script.docx                  # Formatted Word Document
├── tts_payload.json                     # Atomic paragraph payload for voice synthesis
├── master_roadmap.jsonl                 # Paged 25-row scene graph roadmap
├── flow_prompts.json                    # Google Flow keyframe metadata
├── voice_generation_manifest.json       # Chapter synthesis manifest & status
├── audio_manifest.json                  # Re-timed DSP chapter durations
├── full_episode_voice.wav               # Stitched master voice track
├── timeline.json                        # Canonical Single Source of Truth (SSOT)
├── timeline.json.sha256                 # Fail-closed cryptographic checksum
├── timestamped_transcript.txt           # Sentence-level timestamp timeline
├── timestamped_transcript.srt           # Full video subtitle timeline
├── image_timestamps.txt                 # Exact sync anchors for images
├── image_timestamps.txt.sha256          # Image timestamp checksum sidecar
├── audacity_voice/
│   └── full_episode_voice.wav           # DSP-mastered voice track
├── voice_chapters/
│   ├── Chapter_1.wav                    # Sectional audio synthesis
│   └── Chapter_2.wav
├── polished_chapters/
│   ├── Chapter_1.wav                    # Sectional DSP-mastered audio
│   └── Chapter_2.wav
├── generated_images/
│   ├── 00_00.png                        # Frame-accurate scene assets
│   ├── 00_05.png
│   └── 00_12_2.png                      # Multi-frame continuity duplicates
├── thumbnails/
│   ├── title_1_thumbnail.png            # High-CTR winning thumbnail
│   └── title_3_thumbnail.png
├── studio_viewer.html                   # Interactive side-by-side comparison studio
├── compile_checkpoint.json              # Render state tracking
├── youtube_ready_video.mp4              # Final Master Video
├── youtube_ready_video_1080p.mp4        # 1080p high-bitrate proxy stream
└── youtube_ready_video_720p.mp4         # 720p mobile-optimized proxy stream
```

---

## 📑 Architectural Decision Records (ADRs)

### ADR-001: Zero-API CDP Browser Automation

- **Status:** Accepted
- **Context:** Official LLM and Speech API endpoints impose strict rate limits, high credit costs, and over-sensitive content filters on colloquial dialects.
- **Decision:** Automate authenticated sessions on `gemini.google.com`, `aistudio.google.com`, and `labs.google/fx/tools/flow` using Playwright over Chrome DevTools Protocol (`localhost:9222`).
- **Consequences:**
  - ✅ Zero API costs; access to web-exclusive models (`Nano Banana 2`, `Achird Speech`).
  - ⚠️ Fragile to frontend DOM changes.
  - **Mitigation:** Centralized selector abstractions in `gemini_utils.py` and `utils.py` with multi-selector cascading fallbacks and text-stability polling.

---

### ADR-002: Deterministic DSP via Audacity Named Pipes

- **Status:** Accepted
- **Context:** GUI hotkey automation (PyAutoGUI) for audio mastering failed when OS windows lost focus or modal dialogues appeared.
- **Decision:** Replace GUI simulation with Audacity's native IPC Named Pipes (`mod-script-pipe`), executing explicit batch macro commands (`SelectAll:`, `NoiseGate:`, `Compressor:`, `Normalize:`, `Export2:`).
- **Consequences:**
  - ✅ Headless, 100% reliable background execution without GUI focus dependencies.
  - ✅ Auto-syncs `YouTube_Voice_Optimizer.txt.txt` directly to Audacity's AppData macro directory on boot.

---

### ADR-003: Conversational Explainer Dialect & Dynamic Prosody Architecture

- **Status:** Accepted
- **Context:** Literal English-to-Arabic translations produce robotic, unengaging "translatese" that causes viewer retention drop-off.
- **Decision:** Enforce an adaptive two-stage linguistic pipeline:
  1. `automate_all.py` (Phase 1): Transcreates into natural conversational Arabic with 30% academic precision and 70% engaging colloquial phrasing, governed by an automated $\ge 35\%$ Arabic ratio gate.
  2. `refine_script.py` (Phase 2): Applies 1-3-1 Gary Provost sentence cadence, comedic timing, skeptical interjections, and phonetic Tashkeel diacritics.
  3. `generate_voice.py` (Phase 3): Injects neural TTS prosody tags (`[tone: street_logic]`, `[tone: expert_drop]`, `[pause: comedic_halt]`).

---

### ADR-004: Multi-Frame Continuity Chaining in Google Flow

- **Status:** Accepted
- **Context:** Generating isolated image prompts produces inconsistent character designs, erratic lighting, and disjointed backgrounds across continuous scenes.
- **Decision:**
  1. Gemini constructs a `master_roadmap.jsonl` and `flow_prompts.json` with explicit sequence semantics.
  2. For subsequent frames in a sequence, `flow_image_generator.py` locates the previous generated image card in the workspace DOM, clicks **"Add to prompt"**, and injects delta-motion directives with baseline references.
  3. Images are extracted via native Playwright viewport screenshots (bypassing CORS/tainted canvas locks) with Base64 fetch fallback.

---

### ADR-005: Hardware-Accelerated Zero-Drift Video Compositing

- **Status:** Accepted
- **Context:** Dynamic framerates and multi-pass stitching cause millisecond-level audio/video desynchronization over long documentary timelines.
- **Decision:**
  1. `compile_video.py` pre-calculates exact integer frame counts for every clip (`total_frames = audio_duration * fps`), forcing clip 0 to frame 0.
   2. Renders batches of clips (chunk size: `CHUNK_SIZE`, default 20) to temporary MP4s via `-filter_complex_script` to prevent 32 KB Windows CLI argument overflow.
   3. Probe-detects hardware encoders with automatic cascading fallback:
      $$\text{NVIDIA (\texttt{h264\_nvenc})} \longrightarrow \text{Intel QuickSync (\texttt{h264\_qsv}}, \leq 1080\texttt{p}\texttt{)} \longrightarrow \text{CPU (\texttt{libx264})}$$
   4. Always forces `QSV_LOOKAHEAD=0` and pixel format normalization (`format=nv12` for QSV, `format=yuv420p` for CPU/NVENC).

---

### ADR-006: Lexical Sequence Spelling Alignment

- **Status:** Accepted
- **Context:** Speech-to-text models (Whisper) often phonetically misspell Egyptian colloquial slang or specialized scientific terminology.
- **Decision:** `correct_transcript_spelling.py` runs `difflib.SequenceMatcher` (with `autojunk=False`) over the raw ASR tokens against the ground-truth `refined_script.txt`, replacing misspelled words while preserving millisecond-accurate timestamps across `.txt` and `.srt` files.

---

### ADR-007: Dynamic Multi-Niche Architecture & Channel Profile Decoupling

- **Status:** Accepted
- **Context:** Hardcoding persona elements directly into prompt generators prevented the studio from creating content for varied channels, niches, and formats.
- **Decision:** Implement `src/youtube_automation/prompts/niche_engine.py` declaring extensible `NICHE_PRESETS` (`GENERAL_EXPLAINER`, `SCIENCE_TECH`, `FINANCE_ECONOMICS`, `HISTORY_GEOPOLITICS`, `PHILOSOPHY_ESSAY`, `CULTURE_COMEDY`) and modular `ChannelProfile` configurations supporting customizable host modes (`NONE`, `CUSTOM_AVATAR`, `DOCUMENTARY_OBSERVER`).
- **Consequences:**
  - ✅ Universal reuse across diverse YouTube educational niches.
  - ✅ Complete elimination of hardcoded character and cafe tropes.

---

### ADR-008: Long-Form 16:9 Widescreen Universal 6-Part Prompt Grammar & Two-Substrate Model

- **Status:** Accepted
- **Context:** Unconstrained diffusion prompts caused 15-cut retinal luminance whiplash, warped Latin text leaks, and perspective distortion.
- **Decision:**
  1. Adopt the Universal 6-Part Grammar (Master Style Anchor, Orthographic 2D Camera Model, 16:9 Foveal Safe Envelope, Substrate Ground, Semantic Data Entity, Codec-Safe Accents).
  2. Implement Two-Substrate Studio Grounds: `#2A2420` dark mahogany workbench for host studio shots and `#F8F8FA` neutral drafting limbo desk for technical plates.
  3. Enforce 60-30-10 chromatic attention law and strict zero-text invariant with non-linguistic data telemetry (ratio bars, waveforms, node linkages).

---

### ADR-009: Audio-Transient-Gated Procedural Kinematics & Upper-Third Eye-Line Pinning

- **Status:** Accepted
- **Context:** Random pan/zoom movements produce ocular fatigue and desynchronization with voice emphasis.
- **Decision:**
  1. Deploy `AudioTransientDetector` using short-time RMS energy flux and adaptive surge gating ($\ge 4.5\text{ dB}$).
  2. Enforce +33.3ms (1-frame) optical lag compensation aligning visual camera actions with human cross-modal perception (auditory ~140ms vs visual ~180ms).
  3. Pin discrete scale punches (zoom 1.25) to upper-third eye-line elevation ($Y=360\text{px}$) with zero-safe clamped drift on long holds ($\ge 3.5\text{s}$).

---

### ADR-010: Top-of-Feed Sorting, Angular CDK Auto-Attach & Resilient Gap-Skipping

- **Status:** Accepted
- **Context:** Google Flow UI prepends new generation cards to the top of the feed (lowest $y$), unmounts virtualized asset cards in the Angular CDK drawer, and occasionally experiences transient queue latency.
- **Decision:**
  1. Always sort candidate images ascending by $(y, x)$ to select newly generated top-row cards.
  2. Inject bidirectional wheel scrolls (`-600`, `+600`) to mount virtualized drawer items and detect single-click auto-attachment.
  3. Implement resilient gap-skipping with a single-pass deterministic post-batch backfill sweep, eliminating false account failovers on non-fatal queue timeouts.

## 🔌 Inter-Process Communication (IPC) Protocol

### Audacity Named Pipe Architecture

```
┌─────────────────────────┐                 ┌─────────────────────────┐
│   automate_audacity.py  │                 │      Audacity.exe       │
│                         │                 │   (mod-script-pipe=1)   │
│  \\.\pipe\ToSrvPipe     ├────────────────►│  Reads command stream   │
│                         │   Command IPC   │                         │
│  \\.\pipe\FromSrvPipe   │◄────────────────┤  Returns "BatchCommand   │
│                         │   Response IPC  │  finished: OK"          │
└─────────────────────────┘                 └─────────────────────────┘
```

Audacity named pipe commands must be formatted as `<Command>:<Parameter>="<Value>"` followed by a newline:

- `Import2:Filename="C:\\path\\to\\audio.wav"`
- `SelectAll:`
- `NoiseGate:attack=10...`
- `Export2:Filename="C:\\path\\to\\export.wav" NumChannels=1`

---

## 🛡️ Fault Tolerance, Recovery & Checkpoints

| Component         | Failure Trigger                                   | Automated Recovery Mechanism                                                                              |
| :---------------- | :------------------------------------------------ | :-------------------------------------------------------------------------------------------------------- |
| **Gemini Chat**   | Repeated paragraph failures                       | Cumulative `FAILURE_BUDGET` (`max(max_retries*5, 20)`) aborts rotation cleanly; profile retries reset on rotation. Academic re-framing fallback is *planned, not implemented*. |
| **AI Studio TTS** | Session token expiry / 500 error / stalled render | Exponential backoff $(5\text{s} \times 2^n)$; reloads session and reapplies settings.                     |
| **Account Quota** | 3 consecutive chapter/frame failures              | `rotate_profile_index()` cycles `ACTIVE_PROFILE_INDEX`, kills CDP socket, and relaunches browser profile. |
| **Google Flow**   | "Something went wrong loading media"              | Auto-clicks card retry button; if stalled >120s, forces workspace URL reload.                             |
| **Audacity**      | Pipe connection broken / crash                    | Surgically terminates `Audacity.exe`, wipes `SessionData`/`AutoSave`, and relaunches instance. Exports bounded by a 900 s deadline; timed-out chapters are skipped *without* being marked polished, so resume retries them. |
| **FFmpeg**        | Hardware encoder driver crash (QSV/NVENC)         | Catches non-zero exit codes and re-renders affected chunks via CPU `libx264`. A stderr pump-thread keeps the per-chunk timeout enforceable even when an encoder hangs silently. |

All state files (`pipeline.json`, refine/voice/audacity checkpoints, voice manifest, asset memos) are written atomically — temp file + `fsync` + `os.replace` — so a crash mid-write can never leave truncated state behind.

---

## 🧪 Testing & Validation

```bash
# Run the audit test suite (unit tests; no GUI/Audacity/FFmpeg required)
python -m pytest tests/unit -v

# Run the full test suite
python -m pytest tests/ -v

# Test timeline synchronization math
python -m pytest tests/unit/test_timeline.py -v

# Run linting and type checking (formatting is enforced by pre-commit's ruff-format)
ruff check .
mypy .
```

> Note: the legacy `tests/unit` suite currently carries ~11 stale expectations
> (occurrence-suffixed dict keys, `raw_sec` field, real-hardware encoder probes)
> that predate recent production evolution — see `.docs/TEST_EXECUTION_REPORT.md`.

---

## 📚 Related Documentation Files

- **User Quick Start & Config:** [README.md](../README.md)
- **Agent Instructions:** [AGENTS.md](../AGENTS.md) · [CLAUDE.md](../CLAUDE.md)
- **Code of Conduct:** [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- **Security & Credential Policy:** [SECURITY.md](../SECURITY.md)
- **Contribution Guidelines:** [CONTRIBUTING.md](../CONTRIBUTING.md)
- **Dialect Configuration:** `daheeh_config.json` (repo root)
- **Quality Audit Rubric:** [audit_rubric.md](audit_rubric.md) (this directory)
- **Audit Deliverables:** `.docs/` (AUDIT_REPORT, TEST_EXECUTION_REPORT, ARCHITECTURE_HEALTH_CHECK)
