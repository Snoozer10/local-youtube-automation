# 🤝 Contributing to the YouTube Video Automation Pipeline

Thank you for your interest in contributing to the **YouTube Video Automation Pipeline**! This project is an enterprise-grade, zero-cloud-bill autonomous media production engine designed to transcreate source content into high-retention 1440p documentaries in the signature **Al-Daheeh (الدحيح)** style.

This guide provides technical specifications, development environment setups, coding conventions, and pull request workflows for contributors.

---

## 📑 Table of Contents

- [Code of Conduct](#-code-of-conduct)
- [Prerequisites & System Setup](#-prerequisites--system-setup)
- [Project Architecture & Module Layout](#-project-architecture--module-layout)
- [Development Conventions & Golden Rules](#-development-conventions--golden-rules)
- [Code Style & Quality Standards](#-code-style--quality-standards)
- [Testing & Validation](#-testing--validation)
- [Pull Request (PR) Workflow](#-pull-request-pr-workflow)
- [Reporting Issues & Feature Proposals](#-reporting-issues--feature-proposals)

---

## 📜 Code of Conduct

All contributors, maintainers, and community members are expected to adhere to our [Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project, you agree to uphold welcoming, ethical, and harassment-free standards.

---

## ⚙️ Prerequisites & System Setup

Because this pipeline interfaces directly with Windows IPC pipes, GPU hardware decoders, and Chromium debugging sessions, development requires the following environment:

### System Requirements

- **Operating System**: Windows 10 / 11 (64-bit required for Win32 Named Pipes, `ctypes.windll`, and CDP process trees).
- **Python**: `3.10` or higher.
- **FFmpeg**: Version 5.0+ installed and available in system `PATH` (with Intel QuickSync or NVIDIA NVENC support).
- **Audacity**: Version 3.x+ with `mod-script-pipe` enabled (**Edit** → **Preferences** → **Modules** → Set `mod-script-pipe` to **Enabled**).
- **Chromium Browsers**: Google Chrome or Opera / Opera GX.

### Local Development Setup

```powershell
# 1. Clone the repository
git clone https://github.com/YOUR-USERNAME/Youtube-Automation.git
cd Youtube-Automation

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install core and development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Initialize pre-commit hooks
pre-commit install
```

### Configuring Local Debugging Profiles

The pipeline connects to pre-authenticated browser profiles on port `9222`:

```powershell
# Launch Chrome in CDP debugging mode
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\ChromeDebugProfile"
```

Create your `.env` (or `gemini_model.txt`) configuration from the template in [README.md](README.md). **Never commit credentials, tokens, or debug profile directories.**

---

## 🏛️ Project Architecture & Module Layout

The codebase follows a modular, phase-based pipeline orchestrated by `run_agency.py`:

```
├── run_agency.py                     # Master autonomous supervisor & batch state machine
├── automate_all.py                   # Phase 1: Transcript extraction & 30/70 transcreation
├── refine_script.py                  # Phase 2: Al-Daheeh cadence, humor & Tashkeel polish
├── generate_voice.py                 # Phase 3: AI Studio TTS voice synthesis (Achird)
├── stitch_chapters.py                # Phase 4: Chapter WAV concatenation
├── automate_audacity.py              # Phase 5: Headless DSP mastering via Named Pipes
├── faster_whisper_transcribe_audio.py# Phase 6: Zero-drift Faster-Whisper ASR & VAD alignment
├── correct_transcript_spelling.py    # Phase 7: SequenceMatcher ASR spelling correction
├── flow_image_generator.py           # Phase 8: Google Flow (Imagen 3) visual generation
├── script_image_generator.py         # Phase 8b: Gemini UI direct visual generation
├── fix_timestamps.py                 # Phase 9: Timeline JSON validation & injection
├── generate_thumbnail.py             # Phase 10: 2D Webcomic CTR thumbnail generator
├── compile_video.py                  # Phase 11: Hardware-accelerated Ken Burns 1440p compositor
│
├── utils.py                          # Core utilities (CDP launcher, configs, Telegram alerts)
├── gemini_utils.py                   # Gemini Web UI selector abstractions & stability polling
├── daheeh_config.json                # Dialect profile, Tashkeel lexicon, and acoustic metrics
├── audit_rubric.md                   # 10-point script quality audit rubric
├── video_config.txt                  # FFmpeg resolution, bitrate, easing, and encoder settings
└── transcribe_config.txt             # Whisper chunking, VAD, and model size settings
```

---

## 📐 Development Conventions & Golden Rules

When contributing code, you must strictly follow these engineering invariants:

### 1. Zero-API-Key Browser Automation (Playwright CDP)

- **Rule**: All generative AI interactions (Gemini, Speech Studio, Flow) must occur via Playwright CDP over `127.0.0.1:9222`. Do not introduce paid cloud API SDKs.
- **DOM Selectors**: Never hardcode single selectors. Use cascading fallback lists in `gemini_utils.py` and wait for DOM text stability before capturing output.

### 2. Mandatory Idempotency & Checkpoint/Resume

- **Rule**: Every long-running phase must save progress to a local JSON checkpoint in `youtube_runs/<Title>/` after each chunk/turn.
- If a script is interrupted (e.g., via `Ctrl+C` or a network drop), running it again must instantly resume from the exact last successful paragraph, chapter, or image.

### 3. Al-Daheeh Linguistic Integrity (30/70 Rule)

- **Rule**: All transcreation and refinement changes must adhere to `daheeh_config.json` and `audit_rubric.md`:
  - **30% Academic Fusha**: Scientific jargon, medical terms, university/journal names, historical dates.
  - **70% Cairene Amiya**: Conversational connectors, analogies, verbs, and pronouns.
  - **1-3-1 Cadence**: Varied sentence lengths (Short punch $\rightarrow$ Explanatory flow $\rightarrow$ Slang punchline).
  - **Tashkeel Vocalization**: Ambiguous slang words (e.g., `كِدَه`, `بِيُقول`, `هُوبَّا`) must be vocalized.

### 4. Zero-Drift Video & Hardware Fallback Rules

- **Rule**: The video compositor (`compile_video.py`) must calculate integer frames (`total_frames = audio_duration * fps`) to guarantee zero sync drift.
- **Intel QSV Lookahead**: Always keep `QSV_LOOKAHEAD=0`. Enabling lookahead with software-decoded streams causes hardware frame pool starvation.
- **Encoder Failover**: All hardware rendering must implement a try/catch loop with automatic fallback to CPU `libx264`.
- **Pixel Formatting**: Append `format=nv12` for QSV encoders and `format=yuv420p` for CPU/NVENC.
- **Command Line Length Limits**: Large filter graphs (>32 KB) must be written to disk and executed using `-filter_complex_script` (never passed raw in CLI arguments).

### 5. UTF-8 & Arabic Console Safety

- **Rule**: Any script handling Arabic text must include:
  ```python
  import sys
  if hasattr(sys.stdout, 'reconfigure'):
      sys.stdout.reconfigure(encoding='utf-8', errors='replace')
  ```
- All JSON writes must use `ensure_ascii=False` and `indent=2`.

---

## 🎨 Code Style & Quality Standards

We enforce strict formatting, linting, and typing across the codebase:

```bash
# Format code (Line length: 100)
black --line-length 100 .

# Run linter
ruff check . --fix

# Run type checker
mypy .
```

### Commit Message Guidelines

We follow the [Conventional Commits](https://www.conventionalcommits.org/) standard:

```
<type>(<scope>): <short description>

[optional body]

[optional footer(s)]
```

- **Types**:
  - `feat`: A new pipeline feature or phase.
  - `fix`: A bug fix or DOM selector repair.
  - `refactor`: Code restructuring without functional change.
  - `perf`: Performance improvements (e.g., FFmpeg encoding or Whisper ASR speed).
  - `docs`: Documentation updates (`README.md`, `Project-workflow.md`).
  - `test`: Adding or updating unit/integration tests.
  - `chore`: Maintenance tasks, dependencies, or `.gitignore` updates.
- **Examples**:
  - `feat(flow): implement multi-frame DOM continuity attachment`
  - `fix(audacity): prevent named-pipe timeout on large wav export`
  - `refactor(whisper): replace openai-whisper with faster-whisper vad engine`

---

## 🧪 Testing & Validation

All pull requests must pass the automated test suite before merging:

```bash
# Run full test suite
python -m pytest tests/ -v

# Run timeline synchronization unit tests
python -m pytest tests/unit/test_timeline.py -v

# Run with test coverage report
python -m pytest tests/ --cov=. --cov-report=term-missing
```

### Writing New Tests

- Unit tests in `tests/unit/` should test pure business logic (timeline math, token parsing, Tashkeel replacement, rubric validation) without external browser/FFmpeg dependencies.
- Integration tests in `tests/integration/` requiring browsers or Audacity must be marked with `@pytest.mark.integration`.

---

## 🚀 Pull Request (PR) Workflow

1. **Fork & Branch**: Create a feature branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. **Implement & Test**: Make your changes, ensure all tests pass, and format code with `black` and `ruff`.
3. **Verify Checkpoints**: Test that your changes do not break checkpoint creation or resumption in `youtube_runs/`.
4. **Sanitize Secrets**: Verify no `.env` files, browser profiles (`C:\ChromeDebugProfile`), or Telegram tokens are staged:
   ```bash
   git diff --staged --check
   ```
5. **Open a PR**: Submit a Pull Request to `main` using the PR template below.

### Pull Request Description Template

```markdown
## Description

<!-- Provide a concise summary of your changes and why they are needed -->

## Type of Change

- [ ] 🐛 Bug fix (non-breaking fix for an existing issue)
- [ ] ✨ New feature (adds capability to the pipeline)
- [ ] ⚡ Performance optimization (FFmpeg, ASR, or Playwright DOM execution)
- [ ] ♻️ Refactoring (code cleanup with no functional behavior change)
- [ ] 📚 Documentation update

## Testing Checklist

- [ ] Unit tests pass (`pytest tests/ -v`)
- [ ] Linting & formatting verified (`ruff check . && black --check .`)
- [ ] Verified checkpoint/resume functionality locally
- [ ] Verified no sensitive tokens or debug profile folders are in the diff
```

---

## 🐛 Reporting Issues & Feature Proposals

### Submitting a Bug Report

When opening an issue, please provide:

1. **Environment**: Windows version, Python version, Browser type (Chrome/Opera).
2. **Failing Phase**: Specific script (e.g., `flow_image_generator.py` or `compile_video.py`).
3. **Traceback**: Full terminal output (redacting any private Telegram chat IDs or tokens).
4. **State File**: Relevant contents of `pipeline.json` or phase checkpoint file.

### Proposing a Feature

Submit a feature request detailing:

- The current bottleneck or limitation in the pipeline.
- The proposed architecture or script modification.
- Impact on existing checkpoints, rendering speed, or output quality.

---

Thank you for helping elevate the **YouTube Video Automation Pipeline**! 🚀
