# 🛠️ YouTube Video Automation Pipeline — Developer Technical Workflow

> **Developer-Facing Architecture Reference.** For the user-facing quick start and setup guide, see [README.md](README.md).

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
| **Voice Synthesis**         | AI Studio Speech Playground            | Drives `gemini-2.5-pro-preview-tts` (Voice: _Achird_, Temp: _0.8_). Uses Bezier mouse emulation and MD5 hash caching to detect stale audio.        |
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
├── final_output.txt                     # Phase 1 30/70 transcreated Arabic
├── refined_script.txt                   # Phase 2 Al-Daheeh polished script
├── refined_script.docx                  # Formatted Word Document
├── master_roadmap.txt                   # Visual Scene Continuity Blueprint
├── flow_prompts.json                    # Google Flow keyframe metadata
├── voice_generation_manifest.json       # Chapter synthesis manifest & status
├── full_episode_voice.wav               # Stitched master voice track
├── timestamped_transcript.txt           # Sentence-level timestamp timeline
├── timestamped_transcript.srt           # Full video subtitle timeline
├── image_timestamps.txt                 # Exact sync anchors for images
├── subtitle_chunks.srt                  # 3-word staccato subtitle clips
├── audacity_voice/
│   └── full_episode_voice.wav           # DSP-mastered voice track
├── voice_chapters/
│   ├── Chapter_1.wav                    # Sectional audio synthesis
│   └── Chapter_2.wav
├── generated_images/
│   ├── 00_00.png                        # Frame-accurate scene assets
│   ├── 00_05.png
│   └── 00_12_2.png                      # Multi-frame continuity duplicates
├── thumbnails/
│   ├── title_1_thumbnail.png            # Winning 2D webcomic thumbnail
│   └── title_2_thumbnail.png
├── pipeline.json                        # Master supervisor state machine
└── 🎬 youtube_ready_video.mp4           # Final 1440p Master Video
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

### ADR-003: Al-Daheeh 30/70 Dialect & Prosody Architecture

- **Status:** Accepted
- **Context:** Literal English-to-Arabic translations produce robotic, unengaging "translatese" that causes viewer retention drop-off.
- **Decision:** Enforce a two-stage linguistic pipeline:
  1. `automate_all.py` (Phase 3): Transcreates into 30% Academic Fusha (jargon, universities, dates) and 70% Cairene Amiya (verbs, analogies).
  2. `refine_script.py` (Phase 2): Applies the 1-3-1 Gary Provost sentence cadence, "Abo Hmeed" skeptic interruptions, and phonetic Tashkeel from `daheeh_config.json`.
  3. `generate_voice.py`: Injects TTS prosody tags (`[tone: street_logic]`, `[tone: expert_drop]`, `[pause: comedic_halt]`).

---

### ADR-004: Multi-Frame Continuity Chaining in Google Flow

- **Status:** Accepted
- **Context:** Generating isolated image prompts produces inconsistent character designs, erratic lighting, and disjointed backgrounds across continuous scenes.
- **Decision:**
  1. Gemini constructs a `master_roadmap.txt` and `flow_prompts.json` with explicit `sequence_type` (`PROGRESSIVE_BUILD_SET`, `HISTORICAL_PARODY`, `CAMERA_ZOOM_SEQUENCE`).
  2. For subsequent frames in a sequence, `flow_image_generator.py` locates the previous generated image card in the workspace DOM, clicks **"Add to prompt"**, and injects delta-motion directives with baseline references.
  3. Images are extracted via native Playwright viewport screenshots (bypassing CORS/tainted canvas locks) with Base64 fetch fallback.

---

### ADR-005: Hardware-Accelerated Zero-Drift Video Compositing

- **Status:** Accepted
- **Context:** Dynamic framerates and multi-pass stitching cause millisecond-level audio/video desynchronization over long documentary timelines.
- **Decision:**
  1. `compile_video.py` pre-calculates exact integer frame counts for every clip (`total_frames = audio_duration * fps`), forcing clip 0 to frame 0.
  2. Renders batches of clips (chunk size: 25–40) to temporary MP4s via `-filter_complex_script` to prevent 32 KB Windows CLI argument overflow.
  3. Probe-detects hardware encoders with automatic cascading fallback:
     $$\text{Intel QuickSync (\texttt{h264\_qsv})} \longrightarrow \text{NVIDIA (\texttt{h264\_nvenc})} \longrightarrow \text{CPU (\texttt{libx264})}$$
  4. Always forces `QSV_LOOKAHEAD=0` and pixel format normalization (`format=nv12` for QSV, `format=yuv420p` for CPU/NVENC).

---

### ADR-006: Lexical Sequence Spelling Alignment

- **Status:** Accepted
- **Context:** Speech-to-text models (Whisper) often phonetically misspell Egyptian colloquial slang or specialized scientific terminology.
- **Decision:** `correct_transcript_spelling.py` runs `difflib.SequenceMatcher` over the raw ASR tokens against the ground-truth `refined_script.txt`, replacing misspelled words while preserving millisecond-accurate timestamps across `.txt` and `.srt` files.

---

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
| **Gemini Chat**   | Content policy refusal / safety block             | Triggers academic disclaimer re-framing prompt in fresh chat session.                                     |
| **AI Studio TTS** | Session token expiry / 500 error / stalled render | Exponential backoff $(5\text{s} \times 2^n)$; reloads session and reapplies settings.                     |
| **Account Quota** | 3 consecutive chapter/frame failures              | `rotate_profile_index()` cycles `ACTIVE_PROFILE_INDEX`, kills CDP socket, and relaunches browser profile. |
| **Google Flow**   | "Something went wrong loading media"              | Auto-clicks card retry button; if stalled >120s, forces workspace URL reload.                             |
| **Audacity**      | Pipe connection broken / crash                    | Surgically terminates `Audacity.exe`, wipes `SessionData`/`AutoSave`, and relaunches instance.            |
| **FFmpeg**        | Hardware encoder driver crash (QSV/NVENC)         | Catches non-zero exit code and transparently re-renders all chunks using CPU `libx264`.                   |

---

## 🧪 Testing & Validation

```bash
# Run full unit and integration test suite
python -m pytest tests/ -v

# Test timeline synchronization math
python -m pytest tests/unit/test_timeline.py -v

# Run linting and type checking
ruff check .
mypy .
black --check .
```

---

## 📚 Related Documentation Files

- **User Quick Start & Config:** [README.md](README.md)
- **Code of Conduct:** [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- **Security & Credential Policy:** [SECURITY.md](SECURITY.md)
- **Contribution Guidelines:** [CONTRIBUTING.md](CONTRIBUTING.md)
- **Dialect Configuration:** `daheeh_config.json`
- **Quality Audit Rubric:** `audit_rubric.md`

---

### 🎯 Next Steps You Can Request:

1. **Automated Test Suite Expansion**: Build comprehensive unit tests in `tests/unit/` for `test_timeline.py`, `test_daheeh_config.py`, or `test_audacity_pipe.py`.
2. **Setup Script / Installer**: Create an automated `setup_environment.ps1` script that configures Chrome debug shortcuts, checks FFmpeg/Audacity paths, and provisions virtual environments.
3. **Refactoring a Specific Script**: Target any script (such as `compile_video.py` or `flow_image_generator.py`) for further modularization, type annotations, or performance tuning.
