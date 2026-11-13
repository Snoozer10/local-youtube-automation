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
1. **Interpreter Selection Invariant**: `pyproject.toml` declares `requires-python = ">=3.10"`. Python 3.11 is the recommended development version, while Python 3.10 is compatibility-tested in CI (`test-py310`). On Windows, default `python` in PATH may point to pre-release interpreters (observed: Python 3.15 dev). `setup.ps1` has been updated to prefer `py -3.11` when available, matching `docs/getting-started.md:42`.
2. **Setup Script Hardening & Failure Propagation**:
   - `setup.ps1` now explicitly halts with non-zero exit code if editable installation (`pip install -e . --no-deps`) or dependency consistency check (`pip check`) fails.
   - `setup.bat` captures `%ERRORLEVEL%` into `%EXIT_CODE%` and propagates failure (`exit /b %EXIT_CODE%`).
   - Synthetic stub suite in disposable workspace proved failure exits (exit 42 on editable install failure, exit 77 on pip check failure) and clean success exits (exit 0).
3. **Probe Discrimination Invariant**: `FFprobe` and `Tesseract` diagnostic probes in `setup.ps1` now explicitly distinguish finding an executable on `PATH` from a successful version check. If the binary is present but returns a non-zero exit code, a specific warning is emitted.
4. **Chrome Guidance & Loopback Port Check**: Chrome CDP diagnostic probe is described strictly as a network port check on `127.0.0.1:9222`, routing users to dedicated-profile startup instructions in `docs/usage/adaptive-mode.md`.
5. **Manifest Alignment & S06 Separation**:
   - Core runtime dependencies in `pyproject.toml` and `requirements.txt` are aligned.
   - `torch` and `openai-whisper` are correctly categorized as `pyproject.toml` `tools` extra (`[project.optional-dependencies] tools`) and unconditional entries in `requirements.txt`.
   - S06 dependency remediation (`torch>=2.6.0`, Whisper allowlist, release build attestation) is kept strictly separate.
6. **Prerequisites Categorization**: Evidence is categorized into observed local evidence, hosted CI evidence, and unverified stage prerequisites. Playwright Chromium browser provisioning is explicitly qualified (offline tests mock CDP; no local browser provisioning receipt exists).

---

## 2. Declared Interpreter vs Host Environment

| Property | Declared in Project | Observed on Host | Reconciliation / Action |
| --- | --- | --- | --- |
| **Minimum Python Version** | `>=3.10` (`pyproject.toml:11`) | Supported | Declared range allows 3.10+. |
| **Recommended Development Version** | 3.11 (`docs/getting-started.md:3`) | `Python 3.11.9` (`WindowsApps\...`) | Authoritative, recommended target for Windows development. |
| **Compatibility-Tested CI Version** | 3.10 (`ci/e03-python310-compat`) | `Python 3.10.20` (`uv\python\...`) | Tested in CI `test-py310` workflow. |
| **Default `python` in PATH** | N/A | `Python 3.15.2` (`C:\Python315\python.exe`) | Development/alpha build lacking binary wheels for core C-extensions. |
| **Launcher `py -3.11`** | Recommended (`docs/getting-started.md:42`) | `Python 3.11.9` (`py -3.11`) | Primary launcher target. |

### Setup Script Repair
`setup.ps1` previously inspected `python` before `py`. On systems with Python 3.15 in PATH, this attempted to install into an unsupported interpreter. `setup.ps1` was patched to check `py -3.11` first, falling back to general detection only if `py -3.11` is unavailable.

---

## 3. Dependency Manifest Audit

### 3.1 Manifest Comparison

```
+------------------------------------+-------------------------+-------------------+----------------------+
| Dependency Package                 | pyproject.toml          | requirements.txt  | requirements-dev.txt |
+------------------------------------+-------------------------+-------------------+----------------------+
| youtube-transcript-api             | >=1.2.0                 | >=1.2.0           | (via -r reqs.txt)    |
| playwright                         | >=1.40.0                | >=1.40.0          | (via -r reqs.txt)    |
| python-docx                        | >=1.1.0                 | >=1.1.0           | (via -r reqs.txt)    |
| python-dotenv                      | >=1.0.0                 | >=1.0.0           | (via -r reqs.txt)    |
| tomli (python < 3.11)              | >=2.0.1                 | >=2.0.1           | (via -r reqs.txt)    |
| faster-whisper                     | >=1.0.0                 | >=1.0.0           | (via -r reqs.txt)    |
| tqdm                               | >=4.66.0                | >=4.66.0          | (via -r reqs.txt)    |
| requests                           | >=2.31.0                | >=2.31.0          | (via -r reqs.txt)    |
| psutil                             | >=5.9.0                 | >=5.9.0           | >=5.9.0              |
| Pillow                             | >=10.0.0                | >=10.0.0          | (via -r reqs.txt)    |
| pytesseract                        | >=0.3.13                | >=0.3.13          | (via -r reqs.txt)    |
| pydantic                           | >=2.0.0                 | >=2.0.0           | (via -r reqs.txt)    |
| torch (CUDA / ASR acceleration)    | [tools] >=2.0.0         | >=2.0.0 (uncond.) | (via -r reqs.txt)    |
| openai-whisper (fallback ASR)      | [tools] >=20231117      | >=20231117 (uncond)| (via -r reqs.txt)   |
| pytest                             | [dev] >=7.4.0           | Omitted           | >=8.0.0,<9.2.0       |
| pytest-cov                         | [dev] >=4.1.0           | Omitted           | >=5.0.0              |
| pytest-mock                        | [dev] >=3.11.0          | Omitted           | >=3.12.0             |
| pytest-playwright                  | Omitted                 | Omitted           | >=0.4.4              |
| pytest-timeout                     | Omitted                 | Omitted           | >=2.3.0              |
| pytest-asyncio                     | Omitted                 | Omitted           | >=0.23.0             |
| black                              | [dev] >=26.3.1          | Omitted           | >=26.3.1             |
| ruff                               | [dev] >=0.1.0           | Omitted           | >=0.4.0              |
| mypy                               | [dev] >=1.5.0           | Omitted           | >=1.9.0              |
| type stubs (requests, tqdm, etc.)  | Omitted                 | Omitted           | >=2.31.0, etc.       |
| pip-audit                          | [dev] >=2.6.0           | Omitted           | >=2.7.0              |
| bandit                             | Omitted                 | Omitted           | >=1.7.8              |
| build                              | Omitted                 | Omitted           | >=1.0.0              |
| pre-commit                         | [dev] >=3.5.0           | Omitted           | >=3.7.0              |
+------------------------------------+-------------------------+-------------------+----------------------+
```

### 3.2 Manifest Drift Analysis
- **Core Runtime Dependencies**: All 12 runtime dependencies declared in `pyproject.toml` are mirrored in `requirements.txt`.
- **Heavy Fallback Dependencies**: `torch` and `openai-whisper` are declared under `[project.optional-dependencies] tools` in `pyproject.toml`, but appear as unconditional requirements in `requirements.txt`. Core runtime speech-to-text uses `faster-whisper` (CTranslate2), which does not require the multi-gigabyte PyTorch wheel.
- **Development & Testing Stack**: `requirements-dev.txt` is the authoritative source for testing and typing. `pyproject.toml` `[project.optional-dependencies] dev` contains older baseline floors and omits Mypy type stubs.
- **S06 Remediation Boundary**: No dependency lockfile or floor upgrades were forced during E07. S06 follow-ups (`torch>=2.6.0`, Whisper allowlist, release build attestation) remain separate.

---

## 4. Windows Development Install Verification

### 4.1 Clean Virtual Environment (`include-system-site-packages = false`)
A fresh Python 3.11 virtual environment was created at `architecture-renewal-intake\e07_windows_setup_20261113\clean_venv`:
- `pyvenv.cfg`:
  ```ini
  home = C:\Users\Snoozer\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0
  include-system-site-packages = false
  version = 3.11.9
  ```
- Interpreter: `Python 3.11.9`
- Package manager: `pip 24.0`

**Documented Sequence Execution**:
1. `.\clean_venv\Scripts\python.exe -m pip install -r requirements.txt`:
   - **Observed Blocker**: The download of `torch>=2.0.0` (~2.7 GB Windows wheel on PyPI) hit a network bandwidth bottleneck (~60 KB/s throttled throughput, projecting >11 hours download duration). The command was cancelled to avoid indefinite blocking.
   - **Status**: Left open pending local wheel caching or pre-mirrored PyTorch wheel access.
2. `.\clean_venv\Scripts\python.exe -m pip install -e docs-e07-reproducible-windows-setup --no-deps`:
   - **Result**: Successfully built `youtube_automation_pipeline-4.5.1-0.editable-py3-none-any.whl` (11,474 bytes, SHA-256 `696780a97c054c3591556d6fe5207c389f11dab951cdf023dcc44a4d5fb3dae3`) and installed `youtube-automation-pipeline-4.5.1`.
3. **Editable Origin Verification Outside Source Directory**:
   - Command executed from `architecture-renewal-intake\e07_windows_setup_20261113`:
     ```powershell
     .\clean_venv\Scripts\python.exe -m pip show youtube-automation-pipeline
     ```
   - **Observed Output**:
     ```
     Name: youtube-automation-pipeline
     Version: 4.5.1
     Location: C:\Users\Snoozer\teamwork_projects\architecture-renewal-intake\e07_windows_setup_20261113\clean_venv\Lib\site-packages
     Editable project location: C:\Users\Snoozer\teamwork_projects\docs-e07-reproducible-windows-setup
     Requires: faster-whisper, Pillow, playwright, psutil, pydantic, pytesseract, python-docx, python-dotenv, requests, tqdm, youtube-transcript-api
     ```
4. **Dependency Consistency Probe (`pip check`)**:
   - Command: `.\clean_venv\Scripts\python.exe -m pip check`
   - Exit code: `1`
   - **Observed Output**: Accurately flagged the 11 missing runtime packages whose installation was prevented by the incomplete `requirements.txt` download.
5. **Resolved Package Inventory (`pip list`)**:
   ```
   Package                     Version Editable project location
   --------------------------- ------- ----------------------------------------------------------------------
   pip                         24.0
   setuptools                  65.5.0
   youtube-automation-pipeline 4.5.1   C:\Users\Snoozer\teamwork_projects\docs-e07-reproducible-windows-setup
   ```

### 4.2 Inherited Site-Packages Environment (`disposable_venv`, `--system-site-packages`)
Retained as proof of complete metadata and runtime dependency satisfaction when packages are pre-installed:
```powershell
.\disposable_venv\Scripts\python.exe -m pip check
```
- **Observed Output**: Zero broken or missing requirements for `youtube-automation-pipeline`. (Single unrelated host warning: `fastapi 0.137.2 has requirement starlette>=0.46.0, but you have starlette 0.37.2`).

### 4.3 Stale `.dist-info` Discovery & Remediation
In existing checkouts where `pyproject.toml` had dependencies removed (e.g. `moviepy`, `torchaudio`), stale `.dist-info` metadata caused false `pip check` failures. Re-running `pip install -e . --no-deps` rebuilds `.dist-info/METADATA`, resolving all phantom dependency breaks.

---

## 5. Setup Script Hardening & Synthetic Stub Verification

### 5.1 Script Enhancements
1. `setup.ps1` was modified to exit with `$LASTEXITCODE` on:
   - Editable install failure (`& $VenvPython -m pip install -e $ScriptDir --no-deps --quiet`).
   - Dependency consistency failure (`$PipCheckOutput = & $VenvPython -m pip check 2>&1; exit $PipCheckExit`).
2. `setup.bat` captures `%ERRORLEVEL%` into `%EXIT_CODE%` and propagates failure:
   ```cmd
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
   set "EXIT_CODE=%ERRORLEVEL%"
   if %EXIT_CODE% NEQ 0 (
       ...
       pause
       exit /b %EXIT_CODE%
   )
   ```
3. Probe discrimination was added to Step 6:
   - `FFprobe`: Verifies binary found on `PATH` via `Get-Command 'ffprobe'`, runs `@(& ffprobe -version 2>&1)`, and checks `$LASTEXITCODE -eq 0`.
   - `Tesseract`: Verifies binary found on `PATH` via `Get-Command 'tesseract'`, runs `@(& tesseract --version 2>&1)`, and checks `$LASTEXITCODE -eq 0`.
   - `FFmpeg`: Verifies binary found on `PATH`, runs `@(& ffmpeg -version 2>&1)`, and probes hardware encoders.

### 5.2 Synthetic Stub Test Suite Results
A disposable test suite (`scratch/test_synthetic_setup.py`) executed 7 automated test scenarios using synthetic command stubs:
- **Test 1**: `setup.ps1` editable install failure stub -> exited with code `42`; matched `[ERROR] Editable project install failed with exit code 42.`
- **Test 2**: `setup.bat < nul` editable install failure propagation -> exited with code `42`; matched `[ERROR] Setup failed with exit code: 42`.
- **Test 3**: `setup.ps1` pip check failure stub -> exited with code `77`; matched `[ERROR] pip check reported dependency issues:`.
- **Test 4**: `setup.bat < nul` pip check failure propagation -> exited with code `77`; matched `[ERROR] Setup failed with exit code: 77`.
- **Test 5**: `setup.ps1` success path -> exited with code `0`; matched `[OK] Dependencies installed successfully.`
- **Test 6**: `setup.bat < nul` success path -> exited with code `0`; matched `[SUCCESS] Setup completed successfully.`
- **Test 7a**: Probe failure distinction -> when stub binaries returned exit code `1`, probes reported:
  - `[OK] FFprobe executable found on PATH: ...` + `[WARNING] FFprobe executable was found on PATH but version check failed with exit code 1.`
  - `[OK] Tesseract OCR executable found on PATH: ...` + `[WARNING] Tesseract executable was found on PATH but version check failed with exit code 1.`
- **Test 7b**: Probe success distinction -> when stub binaries returned exit code `0`, probes reported:
  - `[OK] FFprobe executable found on PATH: ...` + `Version check succeeded: ffprobe version 6.0-synthetic`
  - `[OK] Tesseract OCR executable found on PATH: ...` + `Version check succeeded: tesseract 5.3.0-synthetic`

---

## 6. System Prerequisites Audit & Evidence Separation

### 6.1 Observed Local Evidence
| Component | Verification Check | Observed Status on Host | Evidence Source |
| --- | --- | --- | --- |
| **Python 3.11** | `py -3.11 --version` | `Python 3.11.9` | Local terminal execution |
| **FFmpeg** | `ffmpeg -version` | FFmpeg 8.1.2-full_build (Gyan.dev) on PATH | Local terminal execution |
| **FFprobe** | `ffprobe -version` | FFprobe 8.1.2-full_build (Gyan.dev) on PATH | Local terminal execution |
| **Hardware Encoders** | `ffmpeg -hide_banner -encoders` | 23 encoders verified (`h264_qsv`, `h264_nvenc`, `h264_amf`, `av1_qsv`, `libx264`) | Local terminal execution |
| **Editable Package** | `pip show youtube-automation-pipeline` | Version 4.5.1, Editable location verified | Local terminal execution (`clean_venv` & `disposable_venv`) |
| **Script Error Handling** | `scratch/test_synthetic_setup.py` | 7/7 synthetic tests passed | Automated test receipts |

### 6.2 Hosted CI Evidence
GitHub Actions runs on initial PR #121 head (`5522ec4475ce86e75e4524668558ac88de7c0a0d`):
- **`onboarding`**: [Passed in 5s](https://github.com/Snoozer10/local-youtube-automation/actions/runs/19343714652/job/55338166663) (Python 3.11 on `windows-latest`).
- **`test`**: [Passed in 11m35s](https://github.com/Snoozer10/local-youtube-automation/actions/runs/19343714652/job/55338166699) (Python 3.11 test matrix; 468 passed, 35 skipped).
- **`test-py310`**: [Passed in 8m20s](https://github.com/Snoozer10/local-youtube-automation/actions/runs/19343714652/job/55338166668) (Python 3.10 test matrix; 468 passed, 35 skipped).

### 6.3 Unverified Stage Prerequisites
| Prerequisite | Documented Role | Observed Status on Host | Requirement Classification |
| --- | --- | --- | --- |
| **Audacity mod-script-pipe** | Narration mastering | Executable present; pipe `\\.\pipe\ToSrvPipe` closed (offline) | Optional Stage Feature (daemon required) |
| **Chrome CDP Loopback** | Web automation (Gemini/Flow/TTS) | Chrome present; port 9222 not listening (offline) | Optional Stage Feature (dedicated profile & port required) |
| **Playwright Chromium** | Automated browser execution | Playwright package installed; Chromium binaries not provisioned locally (no receipt; offline tests mock CDP) | Optional Stage Feature (download required) |
| **Tesseract OCR** | Adaptive image validation gate | `pytesseract` library installed; `tesseract.exe` not on PATH | Optional Stage Feature (`winget install UB-Mannheim.TesseractOCR`) |

---

## 7. Required Baseline vs Optional Stage Categorization

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

## 8. Evidence-Backed Changes Applied

1. **`setup.ps1`**:
   - Preferred `py -3.11` before falling back to `python`/`py`.
   - Exited non-zero on editable installation failure or `pip check` failure.
   - Enhanced `FFprobe` and `Tesseract` probes to distinguish executable on `PATH` from version check failure.
   - Described Chrome CDP check as a port check on `127.0.0.1:9222` routing to dedicated-profile instructions in `docs/usage/adaptive-mode.md`.
   - Updated completion banner to `.\run.bat lint-exercises` (or `$VenvPython tools\lint_exercises.py`).
2. **`setup.bat`**:
   - Confirmed failure propagation via `set "EXIT_CODE=%ERRORLEVEL%"` and `exit /b %EXIT_CODE%`.
3. **`docs/getting-started.md`**:
   - Aligned Python versions: Python 3.11 recommended, Python 3.10 compatibility-tested in CI, package metadata allows `>=3.10`.
   - Identified FFmpeg and FFprobe as rendering prerequisites.
   - Described Chrome loopback probe as a port check on 9222 and routed to dedicated-profile instructions.
4. **`docs/agents/setup.md`**:
   - Aligned Python guidance: Python 3.11 recommended, Python 3.10 compatibility-tested.
   - Identified FFmpeg and FFprobe as required rendering prerequisites.
   - Routed browser guidance to dedicated-profile instructions in `docs/usage/adaptive-mode.md`.
5. **`tasks/e07-windows-setup-report.md`**:
   - Corrected manifest table: `torch` and `openai-whisper` under `pyproject.toml` `tools` extra and unconditional `requirements.txt` entries.
   - Separated observed local evidence, hosted CI evidence, and unverified stage prerequisites.
   - Documented clean venv vs inherited-venv verification and synthetic stub test suite receipts.

---

## 9. Verification Checks

All offline repository checks pass cleanly:
```powershell
python tools/check_readme.py     # 7 documents checked; return code 0
python tools/check_secrets.py    # 0 secrets detected; return code 0
git diff --check                 # Clean diff; zero whitespace errors; return code 0
pytest tests/unit/test_readme_contract.py -v   # Passed
```
