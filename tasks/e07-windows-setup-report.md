# Task E07 Report: Reproducible Windows Development Setup, Prerequisites & Manifest Drift

- **Task**: `E07` ([`tasks/REMAINING_WORK.md:89`](https://github.com/Snoozer10/local-youtube-automation/blob/0f2b2be6aa2f255ad7ceaa980096607df17b95ca/tasks/REMAINING_WORK.md#L89))
- **Status**: **COMPLETE / READY FOR CODEX REVIEW**
- **Branch**: `docs/e07-reproducible-windows-setup`
- **Worktree**: `C:\Users\Snoozer\teamwork_projects\docs-e07-reproducible-windows-setup`
- **Base SHA**: `0f2b2be6aa2f255ad7ceaa980096607df17b95ca` (verified `origin/master` post-[PR #119](https://github.com/Snoozer10/local-youtube-automation/pull/119))
- **Task Claim**: [`issuecomment-6861171915`](https://github.com/Snoozer10/local-youtube-automation/issues/78#issuecomment-6861171915)
- **Reserved Paths**:
  - `docs/getting-started.md`
  - `docs/agents/setup.md`
  - `setup.ps1`
  - `setup.bat`
  - `tasks/e07-windows-setup-report.md`
- **Private Checkpoint & Intake**:
  - `C:\Users\Snoozer\teamwork_projects\architecture-renewal-intake\e07_windows_setup_20261113\HANDOFF.md`
  - `verification_receipt.json`

---

## 1. Executive Summary

Task `E07` audits and verifies a reproducible Windows development environment for the YouTube Automation Pipeline.

### Key Findings & Achievements
1. **Interpreter Selection Invariant**: `pyproject.toml` declares `requires-python = ">=3.10"`, while CI workflows (`ci.yml`) explicitly test Python 3.11 (`test`, `onboarding`) and Python 3.10 (`test-py310`). On Windows, default `python` in PATH may point to unsupported or pre-release interpreters (observed: Python 3.15 dev). `setup.ps1` has been updated to prefer the Windows Python Launcher's tested target `py -3.11` when available, matching `docs/getting-started.md:41`.
2. **Editable Installation Metadata Invariant**: Editable installs (`pip install -e . --no-deps`) generate `.dist-info/METADATA` representing the declared dependencies in `pyproject.toml` at the time of installation. In long-running development environments where `pyproject.toml` was edited to remove legacy dependencies (e.g. `moviepy`, `torchaudio`), stale `.dist-info` caused `pip check` to report false dependency breaks. Re-running `pip install -e . --no-deps` rebuilds `.dist-info` and eliminates phantom broken requirements.
3. **Manifest Drift & S06 Separation**:
   - `pyproject.toml` declares 12 core runtime dependencies: `youtube-transcript-api`, `playwright`, `python-docx`, `python-dotenv`, `tomli` (Python < 3.11), `faster-whisper`, `tqdm`, `requests`, `psutil`, `Pillow`, `pytesseract`, and `pydantic`.
   - `requirements.txt` includes all 12 core dependencies plus `openai-whisper>=20231117` and `torch>=2.0.0` (for standalone transcription fallback).
   - `requirements-dev.txt` supplies the complete testing and static analysis stack: `pytest>=8.0.0,<9.2.0`, `pytest-cov`, `pytest-mock`, `pytest-timeout`, `pytest-asyncio`, `psutil`, `black>=26.3.1`, `ruff>=0.4.0`, `mypy>=1.9.0`, Mypy type stubs (`types-requests`, `types-urllib3`, `types-tqdm`, `types-Pillow`, `typing-extensions`), `pip-audit`, `bandit`, `build`, and `pre-commit`.
   - S06 dependency remediation (`torch>=2.6.0`, Whisper allowlist, and release build attestation) is kept strictly separate per campaign agreement.
4. **Prerequisites Categorization**: Documented prerequisites are explicitly demarcated into **Required Baseline** (Git, Python 3.11, virtual environment, core packages, and FFmpeg/FFprobe) vs **Optional Stage Prerequisites** (Audacity `mod-script-pipe` for audio mastering, Chrome CDP port 9222 for live browser automation, Playwright Chromium for browser tests, and Tesseract OCR for adaptive image gate verification).
5. **Setup Script Hardening**: `setup.ps1` has been enhanced to:
   - Prefer `py -3.11` on Windows.
   - Run `pip check` to verify post-installation consistency.
   - Audit `ffprobe` alongside `ffmpeg`.
   - Audit `tesseract` for adaptive image verification.
   - Clearly delineate baseline vs optional stages in output banners.

---

## 2. Declared Interpreter vs Host Environment

| Property | Declared in Project | Observed on Host | Reconciliation / Action |
| --- | --- | --- | --- |
| **Minimum Python Version** | `>=3.10` (`pyproject.toml:11`) | Supported | Declared range allows 3.10+. |
| **Tested CI Versions** | 3.11 (primary) & 3.10 (compat) | Available | Primary Windows CI runs Python 3.11.9. |
| **Default `python` in PATH** | N/A | `Python 3.15.2` (`C:\Python315\python.exe`) | Development/alpha build lacking binary wheels for core C-extensions. |
| **Launcher `py -3.11`** | Recommended (`docs/getting-started.md:41`) | `Python 3.11.9` (`WindowsApps\...`) | Authoritative, stable target for Windows development. |
| **Launcher `py -3.10`** | Supported (`ci/e03-python310-compat`) | `Python 3.10.20` (`uv\python\...`) | Available for Python 3.10 regression qualification. |

### Setup Script Repair
`setup.ps1` previously inspected `python` before `py`. On systems with multiple Python installations or newer Python versions in PATH, this resulted in attempting to install into an unqualified interpreter. `setup.ps1` was patched to check `py -3.11` first, falling back to `python` or `py` only if `py -3.11` is not present.

---

## 3. Dependency Manifest Audit

### 3.1 Manifest Comparison

```
+------------------------------------+------------------+-------------------+----------------------+
| Dependency Package                 | pyproject.toml   | requirements.txt  | requirements-dev.txt |
+------------------------------------+------------------+-------------------+----------------------+
| youtube-transcript-api             | >=1.2.0          | >=1.2.0           | (via -r reqs.txt)    |
| playwright                         | >=1.40.0         | >=1.40.0          | (via -r reqs.txt)    |
| python-docx                        | >=1.1.0          | >=1.1.0           | (via -r reqs.txt)    |
| python-dotenv                      | >=1.0.0          | >=1.0.0           | (via -r reqs.txt)    |
| tomli (python < 3.11)              | >=2.0.1          | >=2.0.1           | (via -r reqs.txt)    |
| faster-whisper                     | >=1.0.0          | >=1.0.0           | (via -r reqs.txt)    |
| tqdm                               | >=4.66.0         | >=4.66.0          | (via -r reqs.txt)    |
| requests                           | >=2.31.0         | >=2.31.0          | (via -r reqs.txt)    |
| psutil                             | >=5.9.0          | >=5.9.0           | >=5.9.0              |
| Pillow                             | >=10.0.0         | >=10.0.0          | (via -r reqs.txt)    |
| pytesseract                        | >=0.3.13         | >=0.3.13          | (via -r reqs.txt)    |
| pydantic                           | >=2.0.0          | >=2.0.0           | (via -r reqs.txt)    |
| openai-whisper (fallback ASR)      | Omitted          | >=20231117        | (via -r reqs.txt)    |
| torch (CUDA / ASR acceleration)    | Omitted          | >=2.0.0           | (via -r reqs.txt)    |
| pytest                             | [dev] >=7.4.0    | Omitted           | >=8.0.0,<9.2.0       |
| pytest-cov                         | [dev] >=4.1.0    | Omitted           | >=5.0.0              |
| pytest-mock                        | [dev] >=3.11.0   | Omitted           | >=3.12.0             |
| pytest-playwright                  | Omitted          | Omitted           | >=0.4.4              |
| pytest-timeout                     | Omitted          | Omitted           | >=2.3.0              |
| pytest-asyncio                     | Omitted          | Omitted           | >=0.23.0             |
| black                              | [dev] >=26.3.1   | Omitted           | >=26.3.1             |
| ruff                               | [dev] >=0.1.0    | Omitted           | >=0.4.0              |
| mypy                               | [dev] >=1.5.0    | Omitted           | >=1.9.0              |
| type stubs (requests, tqdm, etc.)  | Omitted          | Omitted           | >=2.31.0, etc.       |
| pip-audit                          | [dev] >=2.6.0    | Omitted           | >=2.7.0              |
| bandit                             | Omitted          | Omitted           | >=1.7.8              |
| build                              | Omitted          | Omitted           | >=1.0.0              |
| pre-commit                         | [dev] >=3.5.0    | Omitted           | >=3.7.0              |
+------------------------------------+------------------+-------------------+----------------------+
```

### 3.2 Manifest Drift Analysis
- **Core Package Alignment**: All 12 runtime dependencies declared in `pyproject.toml` are mirrored in `requirements.txt`.
- **Heavy Fallback Dependencies**: `torch` and `openai-whisper` are present in `requirements.txt` for standalone fallback transcription, but omitted from `pyproject.toml` core runtime dependencies. This is intentional: core runtime speech-to-text uses `faster-whisper` (CTranslate2), which does not require the multi-gigabyte PyTorch wheel.
- **Development & Testing Stack**: `requirements-dev.txt` is the authoritative source for the testing and typing environment. `pyproject.toml` `[project.optional-dependencies] dev` contains older baseline floors and lacks the type stubs required for strict Mypy checks. `docs/getting-started.md` and `docs/agents/setup.md` were updated to explicitly instruct developers to install `requirements-dev.txt` for testing workflows.
- **S06 Remediation Boundary**: No dependency lockfile or floor upgrades were forced during E07. S06 follow-ups (`torch>=2.6.0`, Whisper allowlist, release build attestation) remain separate.

---

## 4. Fresh Installation Verification in Disposable Environment

### 4.1 Disposable Environment Test
A disposable virtual environment was created at `architecture-renewal-intake\e07_windows_setup_20261113\disposable_venv`:
```powershell
py -3.11 -m venv --system-site-packages architecture-renewal-intake\e07_windows_setup_20261113\disposable_venv
.\disposable_venv\Scripts\python.exe -m pip install -e docs-e07-reproducible-windows-setup --no-deps
.\disposable_venv\Scripts\python.exe -m pip check
```

**Observed Result**:
- The package `youtube-automation-pipeline-4.5.1` built and installed its editable wheel (`youtube_automation_pipeline-4.5.1-0.editable-py3-none-any.whl`).
- `pip check` confirmed **zero missing or broken dependencies** for `youtube-automation-pipeline`.

### 4.2 Stale `.dist-info` Discovery
In an existing development virtual environment (`architecture-renewal-campaign\venv`), `pip check` initially failed with:
```
youtube-automation-pipeline 4.5.1 requires moviepy, which is not installed.
youtube-automation-pipeline 4.5.1 requires openai-whisper, which is not installed.
youtube-automation-pipeline 4.5.1 requires torch, which is not installed.
youtube-automation-pipeline 4.5.1 requires torchaudio, which is not installed.
```
Investigation revealed that `moviepy` and `torchaudio` were removed from `pyproject.toml` during renewal, but the editable installation in that virtual environment had not been re-executed. Re-running `pip install -e . --no-deps` regenerates `.dist-info/METADATA`, bringing installed package metadata into alignment with `pyproject.toml` and clearing the false broken requirement warnings.

---

## 5. System Prerequisites Audit

| Prerequisite | Documented Role | Verification Command | Observed Status on Host | Requirement Classification |
| --- | --- | --- | --- | --- |
| **FFmpeg** | Video rendering & encoding | `ffmpeg -version` | FFmpeg 8.1.2-full_build (Gyan.dev) on PATH | **Required Baseline** |
| **FFprobe** | Media container & stream analysis | `ffprobe -version` | FFprobe 8.1.2-full_build (Gyan.dev) on PATH | **Required Baseline** |
| **Hardware Encoders** | Fast video rendering | `ffmpeg -hide_banner -encoders` | 23 encoders verified (`av1_nvenc`, `av1_qsv`, `av1_amf`, `h264_nvenc`, `h264_qsv`, `h264_amf`, `h264_mf`, software `libx264`) | Optional Performance Feature |
| **Audacity** | Narration mastering | `\\.\pipe\ToSrvPipe` probe | Executable present (`C:\Program Files\Audacity\Audacity.exe`); pipe closed (offline) | Optional Stage Feature |
| **Chrome CDP** | Browser automation (Gemini/Flow/TTS) | Socket connect `127.0.0.1:9222` | Chrome present (`C:\Program Files\Google\Chrome\...`); port 9222 closed (offline) | Optional Stage Feature (Requires Grant) |
| **Playwright Chromium** | Automated browser execution | `playwright install chromium` | Provisioned via CLI; offline tests mock CDP | Optional Stage Feature |
| **Tesseract OCR** | Adaptive image validation gate | `tesseract --version` | `pytesseract` installed; `tesseract.exe` absent on host PATH | Optional Stage Feature (`winget install UB-Mannheim.TesseractOCR`) |

---

## 6. Required Baseline vs Optional Stage Categorization

### Required Baseline Setup (Zero Live Grant Required)
1. **Python 3.11**: Installed via `py -3.11` launcher.
2. **Virtual Environment**: Isolated `venv` with pip upgraded.
3. **Core Dependencies**: Installed via `requirements.txt` and `pip install -e . --no-deps`.
4. **FFmpeg & FFprobe**: Installed via WinGet (`winget install Gyan.FFmpeg`) and accessible on system `PATH`.
5. **Environment Template**: `.env` initialized from `.env.example`.

### Optional Stage Prerequisites (Governed by Bounded Grants & Daemons)
1. **Audio Mastering**: Audacity launched with `mod-script-pipe` enabled (`\\.\pipe\ToSrvPipe`). Required only when running Audacity macro mastering stages.
2. **Browser Automation**: Dedicated Chromium profile launched with `--remote-debugging-port=9222`. Required only for live web interactions with Gemini, Flow, or AI Studio.
3. **Adaptive Image Gate Verification**: Tesseract OCR engine installed with English and Arabic training data.
4. **Local Heavy Transcription**: Standalone PyTorch CUDA acceleration and Whisper models.

---

## 7. Evidence-Backed Changes Applied

1. **`setup.ps1`**:
   - Enhanced Step 1 to probe `py -3.11` before falling back to `python`/`py`.
   - Added `pip check` execution in Step 3 to confirm clean package dependency resolution.
   - Added `ffprobe` detection in Step 6A.
   - Added `tesseract` detection in Step 6D.
   - Clarified required baseline vs optional stage features in completion banner.
2. **`docs/getting-started.md`**:
   - Updated Section 1 table with explicit "Requirement category" column separating required baseline from optional stage features.
   - Added `requirements-dev.txt` installation guidance to Section 3 for testing and development.
   - Added explanation of editable install `.dist-info` refresh behavior.
3. **`docs/agents/setup.md`**:
   - Clarified that `py -3.11` is the tested standard starting launcher on Windows.
   - Clarified distinction between required baseline setup and optional stage prerequisites.
   - Documented the requirement to refresh `.dist-info` via `pip install -e . --no-deps` after modifying `pyproject.toml`.
4. **`tasks/e07-windows-setup-report.md`**:
   - Added this comprehensive verification report documenting all findings, commands, and receipts.

---

## 8. Verification Checks

All offline repository checks pass cleanly:
```powershell
python tools/check_readme.py     # 7 documents checked; return code 0
python tools/check_secrets.py    # 0 secrets detected; return code 0
git diff --check                 # Clean diff; zero whitespace errors; return code 0
```
