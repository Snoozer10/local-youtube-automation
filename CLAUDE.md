````markdown
# CLAUDE.md — YouTube Video Automation Pipeline (Al-Daheeh Engine)

Autonomous end-to-end media pipeline transcreating YouTube videos into broadcast-ready 1440p Arabic documentaries in the **Al-Daheeh (الدحيح)** dialect and 2D visual style. Operates entirely on browser automation (Playwright CDP), Win32 Named Pipes, Faster-Whisper ASR, and hardware-accelerated FFmpeg without external paid API keys.

---

## 🛠️ 1. Tech Stack & Runtime Environment

- **OS / Platform**: Windows 10 / 11 x64 only (relies on Win32 Named Pipes, `ctypes.windll.user32`, and detached process flags).
- **Language**: Python 3.10+
- **Browser Automation**: Playwright Sync API over Chrome DevTools Protocol (`127.0.0.1:9222`).
- **ASR & Audio Sync**: Faster-Whisper (CTranslate2 CUDA/CPU with VAD) + `difflib.SequenceMatcher` spelling correction.
- **Audio DSP**: Headless Audacity 3.x via Win32 Named Pipes (`\\.\pipe\ToSrvPipe`).
- **Visuals & Diffusion**: Google Flow (Nano Banana 2 / Imagen 3) with DOM continuity chaining.
- **Video Compositing**: FFmpeg 5+ subprocesses (Intel QSV `h264_qsv`, NVIDIA `h264_nvenc`, CPU `libx264` fallback).
- **Testing & Quality**: pytest, black (100-col), ruff, mypy.

---

## ⚡ 2. Core CLI Commands

### Full Pipeline & Batch Operations

```powershell
# Run the full autonomous supervisor across all folders in youtube_runs/
python run_agency.py

# Run parallel multi-browser sessions across isolated ports
python run_agency.py --port 9222 --folder youtube_runs/Video_Topic_A
python run_agency.py --port 9223 --folder youtube_runs/Video_Topic_B
```
````

### Individual Step Execution (Idempotent / State-Resuming)

```powershell
python automate_all.py                 # Step 1: Caption fetch & 30/70 transcreation
python refine_script.py                # Step 2: Cadence, humor, and Tashkeel polish
python generate_voice.py               # Step 3: AI Studio TTS synthesis (Achird)
python stitch_chapters.py              # Step 4: Lossless WAV chapter concatenation
python automate_audacity.py            # Step 5: Audacity Named-Pipe DSP mastering
python faster_whisper_transcribe_audio.py # Step 6: Faster-Whisper ASR & VAD alignment
python correct_transcript_spelling.py  # Step 7: SequenceMatcher spelling correction
python flow_image_generator.py         # Step 8: Google Flow visual generation
python fix_timestamps.py               # Step 9: Validate & inject prompt timestamps
python generate_thumbnail.py           # Step 10: 2D webcomic CTR thumbnail generator
python compile_video.py                # Step 11: Hardware-accelerated Ken Burns compositor
```

### Testing & Code Quality

```powershell
# Run all tests
python -m pytest tests/ -v

# Run single unit test
python -m pytest tests/unit/test_timeline.py -v

# Lint, format, and type check
black --line-length 100 .
ruff check . --fix
mypy .
```

---

## 🏗️ 3. Architecture & Pipeline Flow

```
youtube_urls.txt
  └─► automate_all.py (Phase 1: 30/70 Fusha/Amiya Transcreation)
        └─► refine_script.py (Phase 2: 1-3-1 Cadence, Humor, Tashkeel)
              └─► generate_voice.py (Phase 3: AI Studio Speech Synthesis)
                    └─► stitch_chapters.py & automate_audacity.py (Phase 4 & 5: Named Pipes DSP)
                          └─► faster_whisper_transcribe_audio.py (Phase 6: Word Timestamps)
                                └─► correct_transcript_spelling.py (Phase 7: Sequence Alignment)
                                      └─► flow_image_generator.py (Phase 8: Google Flow Visuals)
                                            └─► fix_timestamps.py (Phase 9: Timestamp Validation)
                                                  └─► generate_thumbnail.py (Phase 10: Thumbnails)
                                                        └─► compile_video.py (Phase 11: 1440p Render)
```

Every project directory under `youtube_runs/<Title>/` maintains stateful JSON checkpoints (`pipeline.json`, `checkpoint.json`, `refine_checkpoint.json`, `voice_generation_manifest.json`, `compile_checkpoint.json`). Interruptions safely resume from the last completed chunk or frame.

---

## ⚠️ 4. Critical Rules & Architectural Invariants

### 1. Zero-API Browser Automation (Playwright CDP)

- **Never introduce official paid API SDKs**. All LLM, Speech, and Image operations automate authenticated web sessions over `localhost:9222`.
- Use cascading selector lists and text-stability polling (`wait_for_gemini_response` in `gemini_utils.py`) rather than fixed `time.sleep` calls.

### 2. Al-Daheeh Linguistic & Stylistic Constraints

- **The 30/70 Rule**: 30% Academic Fusha (jargon, institutions, dates) : 70% Cairene Amiya (verbs, connectors, street analogies).
- **The 1-3-1 Cadence**: Strict variation of sentence lengths (Short punch $\rightarrow$ Explanatory flow $\rightarrow$ Slang punchline).
- **Phonetic Tashkeel**: Ambiguous slang words (`كِدَه`, `بِيُقول`, `هُوبَّا`, `قِسط`) must be vocalized via `daheeh_config.json`.
- **Anti-Translatese**: Strictly eliminate literal translation artifacts (`علاوة على ذلك`, `نستنتج مما سبق`).

### 3. Audacity Named Pipes (`mod-script-pipe`)

- Always execute `SelectAll:` prior to applying effects (`NoiseGate:`, `Compressor:`, `Normalize:`).
- Always auto-sync presets from `YouTube_Voice_Optimizer.txt.txt` into `%APPDATA%\audacity\macros\` before spawning `Audacity.exe`.
- Wipe `SessionData` and `AutoSave` temporary directories before opening pipe handles to prevent modal recovery popups.

### 4. Faster-Whisper & Subtitle Pacing

- Enforce 3–6 words per visual chunk (`MAX_WORDS_PER_CHUNK=6`, `SUB_SPLIT_TARGET_WORDS=3`).
- When correcting ASR misspellings in `correct_transcript_spelling.py`, use `difflib.SequenceMatcher` to replace text tokens without altering millisecond timing boundaries.

### 5. Google Flow Multi-Frame Continuity

- For multi-frame sequence sets (`PROGRESSIVE_BUILD_SET`, `HISTORICAL_PARODY`, `CAMERA_ZOOM_SEQUENCE`), locate the previous image card in the DOM and click **"Add to prompt"** to inject delta-motion directives.
- Always extract images using native Playwright viewport screenshots (`img_locator.screenshot(path=...)`) to avoid tainted-canvas CORS locks, with Base64 fetch as fallback.

### 6. FFmpeg Hardware Acceleration & Zero-Drift Video

- **Intel QSV Lookahead**: Always keep `QSV_LOOKAHEAD=0`. Enabling lookahead with software-decoded input streams causes hardware frame pool starvation and silent bitstream corruption.
- **Pixel Formatting**: Append `format=nv12` for QSV encoders (`h264_qsv`) and `format=yuv420p` for CPU (`libx264`) or NVENC (`h264_nvenc`).
- **Hardware Fallback**: All video compiling loops must automatically fall back to CPU `libx264` if hardware acceleration fails.
- **Windows CLI Command Limits**: Filter graphs exceeding ~32 KB must be written to disk and loaded via `-filter_complex_script`.
- **Zero-Drift Frame Math**: Allocate exact integer frame counts (`frame_count = audio_duration * fps`) and force clip 0 to start at frame 0.

### 7. UTF-8 & Windows Console Safety

- Always reconfigure standard streams at the top of every script:
  ```python
  import sys
  if hasattr(sys.stdout, 'reconfigure'):
      sys.stdout.reconfigure(encoding='utf-8', errors='replace')
  ```
- All JSON read/writes must use `encoding="utf-8"` and `ensure_ascii=False`.

---

## 🔄 5. Multi-Profile Rotation & Supervisor Logic

`run_agency.py` acts as the master supervisor and manages browser failure states:

1. **State Machine (`pipeline.json`)**:
   - Each video folder maintains a `pipeline.json` mapping each phase to a boolean (`translate`, `refine`, `voice`, `audacity`, `stitch`, `transcribe`, `images`, `fixtimes`, `video`, `thumbnail`).
   - If a phase crashes, the supervisor catches the error, sends a Telegram alert, and leaves the state flag `false` for automatic restart.
2. **Account Rotation Engine (`rotate_profile_index()` in `utils.py`)**:
   - When a phase hits `FAILOVER_RETRY_LIMIT` (e.g. 3 consecutive failures or quota limits):
     1. Increments `ACTIVE_PROFILE_INDEX` in `.env` (cycles `1` $\rightarrow$ `2` $\rightarrow$ `3` $\rightarrow$ `1`).
     2. Calls `kill_cdp_chrome()` to surgically terminate only the Chrome process listening on `CDP_PORT` using `netstat -ano` and `taskkill /PID`.
     3. Calls `launch_browser_with_profile()` with the new profile directory (`Default`, `Profile 1`, `Profile 2`).
     4. Dispatches a Telegram notification regarding the rotation.
3. **Browser Tab Sanitation (`clean_browser_tabs()` in `run_agency.py`)**:
   - Opens a blank tab and closes all stale tabs between phases to prevent RAM bloat and memory leaks across long batch runs.

---

## 📖 6. Configuration Variable Dictionary

### Environment Config (`.env` / `gemini_model.txt`)

| Key                        | Default                      | Purpose                                                                         |
| :------------------------- | :--------------------------- | :------------------------------------------------------------------------------ |
| `VOICE_GENERATOR_MODEL`    | `Flash-Lite`                 | Gemini Chat model orchestrating TTS markup in Phase 3.                          |
| `IMAGE_PLANNER_MODEL`      | `Pro`                        | Model used to generate master visual roadmaps and storyboards.                  |
| `SCRIPT_BREAKER_MODEL`     | `Flash`                      | Model for splitting YouTube transcripts into narrative paragraphs.              |
| `SCRIPT_TRANSLATOR_MODEL`  | `Pro`                        | Model for initial 30/70 Fusha/Amiya transcreation.                              |
| `REFINE_MODEL`             | `Pro`                        | Model for Phase 2 cadence, humor, and Tashkeel polish.                          |
| `THUMBNAIL_MODEL`          | `Nano Banana Pro`            | Model generating 2D webcomic thumbnail prompts and critiques.                   |
| `TTS_MODEL`                | `gemini-2.5-pro-preview-tts` | Model selected in Google AI Studio Speech Playground.                           |
| `TTS_VOICE_NAME`           | `Achird`                     | Voice actor persona in Speech Playground.                                       |
| `TTS_TEMPERATURE`          | `0.8`                        | Generation temperature for voice prosody.                                       |
| `WHISPER_ENGINE`           | `faster_whisper`             | ASR engine (`faster_whisper` or `hard_whisper`).                                |
| `IMAGE_GENERATOR_TYPE`     | `flow`                       | Visual generator backend (`flow` for Google Flow, `script` for Gemini UI).      |
| `FLOW_IMAGE_MODEL`         | `Nano Banana 2`              | Image model inside Google Flow UI.                                              |
| `FLOW_IMAGE_COUNT`         | `1x`                         | Output count per prompt in Google Flow (`1x`, `x2`, `x4`).                      |
| `FLOW_DISABLE_AGENT`       | `true`                       | Disables Google Flow autonomous agent to prevent unprompted edits.              |
| `ACTIVE_PROFILE_INDEX`     | `1`                          | Active Chrome/Opera profile index (1, 2, or 3).                                 |
| `SWITCH_ACCOUNTS_ENABLED`  | `true`                       | Enables automated failover account rotation.                                    |
| `FAILOVER_RETRY_LIMIT`     | `3`                          | Number of retries before triggering account rotation.                           |
| `CDP_PORT`                 | `9222`                       | Remote debugging port for Playwright connection.                                |
| `BROWSER_TYPE`             | `chrome`                     | Target browser (`chrome` or `opera`).                                           |
| `ENABLE_REFINE_SCRIPT`     | `true`                       | Feature flag to enable/disable Phase 2 refinement.                              |
| `FLIP_AUDACITY_ORDER`      | `false`                      | Sets mastering order (`true`: stitch then polish; `false`: polish then stitch). |
| `TELEGRAM_NOTIFY_PER_STEP` | `true`                       | Dispatches Telegram message on every completed pipeline phase.                  |
| `TELEGRAM_BOT_TOKEN`       | `""`                         | Telegram Bot API token for alert webhooks.                                      |
| `TELEGRAM_CHAT_ID`         | `""`                         | Telegram destination Chat ID.                                                   |

### Video Compiler Config (`video_config.txt`)

| Key                              | Default               | Purpose                                                         |
| :------------------------------- | :-------------------- | :-------------------------------------------------------------- |
| `OUTPUT_WIDTH` / `OUTPUT_HEIGHT` | `2560` / `1440`       | Master video dimensions (1440p 2K widescreen).                  |
| `OUTPUT_FPS`                     | `30`                  | Master video framerate.                                         |
| `ENABLE_HARDWARE_ENCODER`        | `true`                | Enables auto-detection of QSV and NVENC encoders.               |
| `ENCODER_FORCE`                  | `""`                  | Optional manual override (`h264_qsv`, `h264_nvenc`, `libx264`). |
| `QSV_LOOKAHEAD`                  | `0`                   | Lookahead depth (must remain `0` to prevent QSV starvation).    |
| `KEN_BURNS_ZOOM_MIN` / `MAX`     | `1.0` / `1.10`        | Zoom boundaries for camera animations.                          |
| `KEN_BURNS_EASING`               | `smoothstep`          | Camera movement easing curve (`smoothstep` or `linear`).        |
| `CHUNK_SIZE`                     | `40`                  | Number of image clips per temporary MP4 chunk render.           |
| `ENABLE_LOUDNORM_TWOPASS`        | `true`                | Executes EBU R128 two-pass audio loudness normalization.        |
| `LOUDNORM_I` / `TP` / `LRA`      | `-14` / `-1.0` / `11` | Integrated loudness, true peak, and loudness range targets.     |

---

## 📁 7. Run Folder State Invariants

Every run folder under `youtube_runs/<Title>/` must conform to these naming conventions:

```
youtube_runs/<Cleaned_Title>/
├── raw_transcript.txt               # Raw YouTube caption dump
├── breaked_paragraphs.txt           # Structured paragraphs from Phase 1
├── final_output.txt                 # 30/70 Transcreated Arabic text
├── refined_script.txt               # Polished Al-Daheeh script (ground truth)
├── refined_script.docx              # Word doc formatted script
├── master_roadmap.txt               # Visual scene continuity roadmap
├── flow_prompts.json                # JSON keyframe array for Google Flow
├── voice_generation_manifest.json   # Chapter audio synthesis manifest
├── full_episode_voice.wav           # Stitched master WAV track
├── timestamped_transcript.txt       # Sentence-level timestamp timeline
├── timestamped_transcript.srt       # Standard SRT subtitle file
├── image_timestamps.txt             # Image sync timeline [MM:SS] text
├── subtitle_chunks.srt              # 3-word fast subtitle clips
├── audacity_voice/                  # DSP-mastered audio output
│   └── full_episode_voice.wav
├── voice_chapters/                  # Chapter WAV files from AI Studio
│   ├── Chapter_1.wav
│   └── Chapter_2.wav
├── generated_images/                # Final visual assets (e.g. 00_00.png, 00_05.png)
├── generated_images_duplicates/     # Multi-frame duplicate/continuation sets
├── thumbnails/                      # Top CTR 2D webcomic thumbnail variants
│   ├── title_1_thumbnail.png
│   └── title_2_thumbnail.png
├── pipeline.json                    # Supervisor completion state flags
└── youtube_ready_video.mp4          # Final 1440p Master Video
```

---

## 🤖 8. Directives for AI Agents Modifying This Codebase

When writing code or refactoring modules in this repository, you must strictly obey the following rules:

1. **No External Paid APIs**: Never import `google-generativeai`, `openai`, or `anthropic` client SDKs. All AI interactions must use the Playwright CDP session.
2. **Preserve Checkpoint Compatibility**: Never alter checkpoint JSON schemas (`checkpoint.json`, `refine_checkpoint.json`, `voice_generation_manifest.json`, `pipeline.json`) without adding backwards-compatible migration logic.
3. **Maintain Subprocess Safety**: Always pass subprocess arguments as lists (never raw strings with `shell=True`). Always write FFmpeg filter graphs exceeding 1,000 characters to a temporary script file using `-filter_complex_script`.
4. **Preserve 100% Arabic Character Integrity**: Always use UTF-8 encodings when reading or writing text files (`encoding="utf-8"`, `ensure_ascii=False`). Always call `sys.stdout.reconfigure(encoding='utf-8')` on Windows consoles.
5. **Enforce Clean Exits**: Before submitting changes, ensure `ruff check .`, `black --check .`, and `mypy .` pass with zero errors.
6. **Strict Named-Pipe IPC Formatting**: Always append a trailing newline `\n` to Audacity commands and read until an empty line terminator (`\n`) is received from `\\.\pipe\FromSrvPipe`.
7. **Zero Dynamic FPS Modifications**: The pipeline is calibrated strictly for integer frame math at `OUTPUT_FPS=30`. Never introduce fractional or variable framerate calculations.

---

## 🔍 9. Edge-Case Triage & Playwright DOM Recovery Matrix

When automating web sessions with Playwright, Google Web UIs often mutate or exhibit transient states. AI agents must apply these verified recovery strategies:

### A. Google Gemini Web App (`gemini.google.com`)

- **Thinking & Analyzing Indicator Trap**:
  - _Symptom_: Gemini returns intermediate text like `"Analyzing"`, `"Thinking..."`, or `"Visualizing the scenes"`, which tricks naive length checks into capturing incomplete output.
  - _Remediation_: Check `is_gemini_generating(page)` for visible stop buttons (`button[aria-label*='Stop' i]`, `button:has(rect)`) and ensure output text remains stable for at least 4 consecutive polling intervals (~5–6 seconds) after transient keywords disappear.
- **"Gemini said" Prefix Leakage**:
  - _Remediation_: Always strip the accessibility prefix:
    ```python
    if text.startswith("Gemini said"):
        text = text[len("Gemini said"):].strip()
    ```
- **Rich-Text Area Input Locking**:
  - _Remediation_: If `locator.fill()` fails on `rich-textarea div[contenteditable='true']`, fall back to:
    ```python
    textbox.focus()
    page.keyboard.press("Control+a")
    page.keyboard.press("Backspace")
    page.keyboard.insert_text(payload)
    ```

### B. Google AI Studio Speech Playground (`aistudio.google.com/generate-speech`)

- **Splash Screen Overlay**:
  - _Remediation_: Query `text="Turn text into natural-sounding speech..."` and click it to dismiss the intro modal before attempting to focus the prompt textarea.
- **Proactive Context Maintenance**:
  - _Symptom_: After 40+ consecutive audio generations, AI Studio's WebSocket connection degrades or runs into client-side token expiration.
  - _Remediation_: Proactively reload the tab every $N$ chapters (`TTS_PROACTIVE_RELOAD_INTERVAL=40`), re-apply voice settings, and re-focus the generation pane.
- **Stale Audio Detection (MD5 Verification)**:
  - _Remediation_: Calculate the MD5 checksum of `Chapter_{N}.wav` and compare it to `Chapter_{N-1}.wav`. If identical, AI Studio served a cached audio buffer. Delete the file, reload the playground tab, and re-synthesize.

### C. Google Flow (`labs.google/fx/tools/flow`)

- **Splash Modal Bypass**:
  - _Remediation_: Check for `button:has-text('Create with Google Flow')` on load and click with `force=True`.
- **Media Loading Container Failures**:
  - _Symptom_: Card displays `"Something went wrong loading your media"`.
  - _Remediation_: Click the card's native retry button (`button:has-text('Retry')`). If failed after 3 attempts, force a workspace reload using the stored project URL from `flow_workspace_url_profile_*.txt`.
- **CORS / Tainted Canvas Canvas-Lock**:
  - _Remediation_: Do not use HTML5 `<canvas>` extraction or JavaScript blob conversion as primary capture. Use native Playwright element screenshots (`img_locator.screenshot(path=save_path, type="png")`), which capture pixels directly from the Chromium compositor.

---

## 🎛️ 10. Audacity Named Pipe Command Protocol

Audacity receives scripting commands over `\\.\pipe\ToSrvPipe` and returns status messages over `\\.\pipe\FromSrvPipe`. Every command must follow this exact sequence:

```
[Script / Python]                                       [Audacity mod-script-pipe]
       │                                                            │
       ├─────── SelectAll:\n ──────────────────────────────────────►│
       │◄────── BatchCommand finished: OK\n\n ──────────────────────┤
       │                                                            │
       ├─────── NoiseGate:attack=10 decay=100 threshold=-30\n ─────►│
       │◄────── BatchCommand finished: OK\n\n ──────────────────────┤
       │                                                            │
       ├─────── Compressor:attackMs=0.1 thresholdDb=-30\n ─────────►│
       │◄────── BatchCommand finished: OK\n\n ──────────────────────┤
       │                                                            │
       ├─────── Normalize:ApplyVolume=1 PeakLevel=-1\n ────────────►│
       │◄────── BatchCommand finished: OK\n\n ──────────────────────┤
       │                                                            │
       ├─────── Export2:Filename="C:\\output.wav" NumChannels=1\n ─►│
       │◄────── Export2 finished: OK\n\n ───────────────────────────┤
```

### Protocol Rules:

1. **Double-Quote Escaping**: When passing file paths to `Import2:` or `Export2:`, absolute paths must use double backslashes (`C:\\path\\to\\file.wav`) wrapped in escaped quotes: `Export2:Filename="C:\\path\\to\\file.wav" NumChannels=1`.
2. **Preset Macro Synchronization**: Before spawning `Audacity.exe`, `automate_audacity.py` copies `YouTube_Voice_Optimizer.txt.txt` to `%APPDATA%\audacity\macros\YouTube_Voice_Optimizer.txt` and `%APPDATA%\audacity\macros\Achird Gemini Voice cut and enhance.txt`.
3. **Pipe Response Terminator**: Always read lines from `read_pipe` until an empty line `line.strip() == ""` is encountered.

---

## 📐 11. Ken Burns Motion Mathematics & FFmpeg Filter Specs

In `compile_video.py`, camera motions are mathematically generated based on exact integer frames ($N = \text{duration} \times \text{FPS}$).

### 1. Smoothstep Easing Function

To prevent jarring linear camera starts and stops, all camera animations use cubic Hermite polynomial smoothstep easing:

$$t = \frac{\text{on} - 1}{\max(1, N - 1)}$$

$$\text{ease}(t) = t^2 \times (3 - 2t) \quad \text{where } t \in [0, 1]$$

### 2. Camera Motion Coordinate Matrix

| Camera Action   | Zoom Expression (`z`)            | X Expression (`x`)            | Y Expression (`y`)            |
| :-------------- | :------------------------------- | :---------------------------- | :---------------------------- |
| **`zoom_in`**   | `z_min + (z_max - z_min) * ease` | `(iw - iw/zoom)/2`            | `(ih - ih/zoom)/2`            |
| **`zoom_out`**  | `z_max - (z_max - z_min) * ease` | `(iw - iw/zoom)/2`            | `(ih - ih/zoom)/2`            |
| **`pan_left`**  | `z_max`                          | `(iw - iw/zoom) * (1 - ease)` | `(ih - ih/zoom)/2`            |
| **`pan_right`** | `z_max`                          | `(iw - iw/zoom) * ease`       | `(ih - ih/zoom)/2`            |
| **`tilt_up`**   | `z_max`                          | `(iw - iw/zoom)/2`            | `(ih - ih/zoom) * (1 - ease)` |
| **`tilt_down`** | `z_max`                          | `(iw - iw/zoom)/2`            | `(ih - ih/zoom) * ease`       |
| **`static`**    | Scaled & padded to canvas        | Centered (`(ow-iw)/2`)        | Centered (`(oh-ih)/2`)        |

### 3. Filter Graph Script Generation Rule

When concatenating $K$ clips in a chunk, FFmpeg command strings exceed Windows 32 KB argument limits. **Never execute the filter string directly via CLI arguments**. Always write the filter graph to `temp_clips/filter_chunk_{N}.txt` and invoke:

```powershell
ffmpeg -y -hide_banner -loglevel warning `
  -loop 1 -t 5.500 -framerate 30 -i "img1.png" `
  -loop 1 -t 3.200 -framerate 30 -i "img2.png" `
  -filter_complex_script "temp_clips/filter_chunk_0001.txt" `
  -map "[vout]" -c:v h264_qsv -preset fast -global_quality 20 `
  -look_ahead 0 -pix_fmt nv12 -an "temp_clips/chunk_0001.mp4"
```

---

## 🔧 12. Troubleshooting & Immediate Remediation Table

| Symptom                              | Root Cause                                                       | Exact Remediation Command / Fix                                                                                          |
| :----------------------------------- | :--------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------- |
| `Cannot connect to CDP port 9222`    | Chrome is not running or listening on port 9222.                 | Run `python -c "from utils import launch_browser_with_profile; launch_browser_with_profile('chrome', 1)"`                |
| `Audacity pipe connection timeout`   | `mod-script-pipe` is disabled in `audacity.cfg`.                 | Open `%APPDATA%\audacity\audacity.cfg` and add `[Modules]\nmod-script-pipe=1`. Kill and relaunch Audacity.               |
| `QSV frame pool starvation`          | `QSV_LOOKAHEAD` is set to $>0$ on software-decoded streams.      | Set `QSV_LOOKAHEAD=0` in `video_config.txt`.                                                                             |
| `Whisper CUDA Out of Memory`         | Model size too large for available GPU VRAM.                     | Set `WHISPER_MODEL_SIZE=small` or `base` in `transcribe_config.txt`.                                                     |
| `Arabic text renders as ??? in CLI`  | Windows console codepage is set to standard OEM (CP437/CP1252).  | Run `chcp 65001` in PowerShell before executing scripts.                                                                 |
| `Google Flow queue stalled >120s`    | Active project workspace stalled on cloud render.                | Delete `flow_workspace_url_profile_*.txt` in the active run folder to force initialization of a clean project workspace. |
| `FFmpeg: Argument list too long`     | Filter complex passed as command line argument rather than file. | Ensure `-filter_complex_script` is used instead of `-filter_complex`.                                                    |
| `Stale audio generated in chapter N` | AI Studio served cached TTS audio identical to chapter N-1.      | `generate_voice.py` MD5 check auto-deletes duplicate track and reloads tab context.                                      |

---

## 🧪 13. Test Suite & Verification Matrix

All unit and integration tests live in `tests/`:

```
tests/
├── unit/
│   ├── test_timeline.py             # Verifies zero-drift integer frame allocation math
│   ├── test_daheeh_config.py        # Verifies Tashkeel replacement & dialect dictionary integrity
│   ├── test_prompts_parsing.py      # Verifies JSON & pre-planned prompt parsing engines
│   └── test_loudnorm_parser.py      # Verifies EBU R128 stderr JSON metric extraction
├── integration/
│   ├── test_audacity_pipe.py        # Tests non-blocking pipe ping to Audacity
│   └── test_cdp_connection.py       # Tests Chromium CDP port 9222 handshake
└── fixtures/
    ├── sample_transcript.txt        # Mock raw transcript input
    └── sample_flow_prompts.json     # Mock Google Flow keyframe array
```

### Running Targeted Test Assertions:

```powershell
# Verify zero-drift frame timeline calculations
python -m pytest tests/unit/test_timeline.py -v

# Verify Tashkeel diacritic injection engine
python -m pytest tests/unit/test_daheeh_config.py -v

# Run full test suite with coverage
python -m pytest tests/ --cov=. --cov-report=term-missing
```

---

## 🏁 14. Summary of Developer Invariants

Whenever editing or expanding this repository, verify these four questions:

1. **Did I preserve Zero-API automation?** (No paid cloud SDKs introduced).
2. **Is it idempotent?** (Can the pipeline be killed mid-execution and safely resumed via checkpoints?).
3. **Is audio/video synchronization sample-accurate?** (Integer frame allocations, zero drift over 10+ minutes).
4. **Is the dialect authentic?** (30% Academic Fusha : 70% Cairene Amiya, Gary Provost 1-3-1 cadence, phonetic Tashkeel diacritics applied).
