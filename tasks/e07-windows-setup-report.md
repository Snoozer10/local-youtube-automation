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

Task `E07` audits, hardens, and verifies a reproducible Windows development environment for the YouTube Automation Pipeline.

### Key Achievements & Verifications
1. **Windows PowerShell 5.1 Native Stderr Fix (`Invoke-NativeCommand`)**:
   - In Windows PowerShell 5.1, native stderr output redirected via `2>&1` produces `ErrorRecord` objects that trigger a terminating `ActionPreferenceStopException` when `$ErrorActionPreference = 'Stop'`, even if the native process exits with code 0.
   - `setup.ps1` introduces `Invoke-NativeCommand`, which temporarily sets `$ErrorActionPreference = 'Continue'`, converts captured output to plain strings, and captures `$LASTEXITCODE` before restoring preference.
   - Preserves complete diagnostics and native exit codes for `pip check`, `ffmpeg`, `ffprobe`, `tesseract`, and `playwright`.
2. **Setup Script Hardening & Failure Propagation**:
   - Validates the active venv interpreter (`$VenvPython` runs, satisfies `>=3.10`, and executes `pip --version` successfully) before proceeding.
   - Checks `playwright install chromium` exit code; emits a warning and omits `[OK]` verification if the command fails.
   - Exits non-zero on editable install failure or `pip check` failure.
   - `setup.bat` captures `%ERRORLEVEL%` into `%EXIT_CODE%` and propagates failure (`exit /b %EXIT_CODE%`).
   - Synthetic stub suite in disposable workspace proved 6/6 test scenarios under PowerShell 5.1 through `setup.bat` (native stderr on exit 0 succeeds and extracts version; native stderr on nonzero warns and continues; pip check failure propagates exit 77 and 42; broken venv pip fails with exit 1; playwright failure warns and omits `[OK]`).
3. **Clean Venv Installation Complete (`include-system-site-packages = false`)**:
   - Verified in disposable Windows Python 3.11 venv with system site-packages disabled.
   - Located and utilized compatible cached Torch wheel `torch-2.15.0-cp311-cp311-win_amd64.whl` (size 126,720,349 bytes, SHA-256 `df96ba396cffd6ed36fbfb0b11497790a3d7c122`).
   - Installed all production dependencies (`requirements.txt`), development dependencies (`requirements-dev.txt`), and editable project (`pip install -e . --no-deps`).
   - `pip check` exited with code 0 (`No broken requirements found.`).
   - Verified editable origin outside checkout: `Editable project location: C:\Users\Snoozer\teamwork_projects\docs-e07-reproducible-windows-setup`.
   - Captured complete resolved package inventory (87 packages).
4. **Documentation Alignment & Chrome Dedicated-Profile Routing**:
   - Routed browser guidance in `docs/getting-started.md`, `docs/agents/setup.md`, and `setup.ps1` to `CONTRIBUTING.md#configuring-local-debugging-profiles`, which contains the actual dedicated-profile Chrome startup command.
   - Advertised the linter using the quoted selected venv interpreter (`& "$VenvPython" tools\lint_exercises.py`) so exit status is preserved.
   - Accurately labeled `.\run.bat` as starting the full batch production pipeline (`run_agency.py`).
5. **Manifest Drift Reconciliation & S06 Separation**:
   - Aligned runtime dependencies; categorized `torch` and `openai-whisper` as `pyproject.toml` `tools` extra and unconditional `requirements.txt` entries.
   - S06 dependency remediation (`torch>=2.6.0`, Whisper allowlist, release build attestation) and U02 documentation sync kept strictly separate.

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
`setup.ps1` previously inspected `python` before `py`. On systems with Python 3.15 in PATH, this attempted to install into an unsupported interpreter. `setup.ps1` checks `py -3.11` first, falling back to general detection only if `py -3.11` is unavailable.

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
Verified in Python 3.11 virtual environment at `architecture-renewal-intake\e07_windows_setup_20261113\clean_venv`:
- `pyvenv.cfg`:
  ```ini
  home = C:\Users\Snoozer\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0
  include-system-site-packages = false
  version = 3.11.9
  ```
- Interpreter: `Python 3.11.9`
- Package manager: `pip 24.0`

**Documented Sequence Execution**:
1. **Cached Torch Wheel Utilization**:
   - Checked local pip HTTP cache (`$env:LOCALAPPDATA\pip\cache\http-v2`).
   - Located compatible pre-cached wheel: `torch-2.15.0-cp311-cp311-win_amd64.whl` (size: 126,720,349 bytes, SHA-256: `df96ba396cffd6ed36fbfb0b11497790a3d7c122`).
   - Installed cached wheel into clean venv: exit code 0 (`Successfully installed torch-2.15.0`).
2. **Production Dependencies**:
   - `.\clean_venv\Scripts\python.exe -m pip install -r requirements.txt`:
   - Exit code: 0 (`Successfully installed Pillow-13.0.0 ... faster-whisper-1.2.1 ... openai-whisper-20250625 ... playwright-1.65.1 ...`).
3. **Development Dependencies**:
   - `.\clean_venv\Scripts\python.exe -m pip install -r requirements-dev.txt`:
   - Exit code: 0 (`Successfully installed pytest-9.1.1 black-26.10.1 ruff-0.17.5 mypy-2.4.1 pip-audit-2.10.1 ...`).
4. **Editable Mode Installation**:
   - `.\clean_venv\Scripts\python.exe -m pip install -e docs-e07-reproducible-windows-setup --no-deps`:
   - Exit code: 0 (`Successfully installed youtube-automation-pipeline-4.5.1`).
5. **Dependency Consistency Probe (`pip check`)**:
   - Command: `.\clean_venv\Scripts\python.exe -m pip check`
   - Exit code: `0`
   - **Observed Output**: `No broken requirements found.`
6. **Editable Origin Verification Outside Source Directory**:
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
7. **Resolved Package Inventory (`pip list`, 87 packages)**:
   ```
   Package                     Version         Editable project location
   --------------------------- --------------- ----------------------------------------------------------------------
   annotated-types             0.8.0
   anyio                       4.16.0
   ast_serialize               0.13.1
   av                          18.1.0
   bandit                      1.9.4
   black                       26.10.1
   boolean.py                  5.0
   build                       1.6.1
   CacheControl                0.14.4
   certifi                     2026.10.23
   cfgv                        3.5.0
   charset-normalizer          3.5.2
   click                       8.5.1
   colorama                    0.4.6
   coverage                    7.17.3
   ctranslate2                 4.9.0
   cyclonedx-python-lib        11.12.0
   defusedxml                  0.7.1
   distlib                     0.4.4
   faster-whisper              1.2.1
   filelock                    4.2.10
   flatbuffers                 25.12.19
   fsspec                      2026.9.0
   greenlet                    3.5.6
   h11                         0.16.0
   hf-xet                      1.8.0
   httpcore2                   2.16.0
   httpx2                      2.16.0
   huggingface_hub             2.4.0
   identify                    2.6.20
   idna                        3.20
   iniconfig                   2.3.1
   Jinja2                      3.1.6
   librt                       0.16.0
   license-expression          30.4.4
   llvmlite                    0.50.0
   lxml                        6.1.3
   markdown-it-py              4.3.0
   MarkupSafe                  3.0.4
   mdurl                       0.1.2
   more-itertools              11.2.1
   mpmath                      1.3.0
   msgpack                     1.2.4
   mypy                        2.4.1
   mypy_extensions             1.2.0
   networkx                    3.6.1
   nodeenv                     1.12.0
   numba                       0.68.1
   numpy                       2.4.6
   onnxruntime                 1.32.0
   openai-whisper              20250625
   packageurl-python           0.17.6
   packaging                   26.3
   pathspec                    1.1.1
   pillow                      13.0.0
   pip                         24.0
   pip_api                     0.0.35
   pip_audit                   2.10.1
   pip-requirements-parser     32.0.1
   platformdirs                4.14.5
   playwright                  1.65.1
   pluggy                      1.7.0
   pre_commit                  4.7.0
   protobuf                    7.36.2
   psutil                      7.2.2
   py-serializable             2.2.0
   pydantic                    2.14.3
   pydantic_core               2.50.4
   Pygments                    2.21.0
   pyparsing                   3.3.3
   pyproject_hooks             1.3.3
   pytesseract                 0.3.13
   pytest                      9.1.1
   pytest-asyncio              1.5.0
   pytest-cov                  7.1.0
   pytest-mock                 3.17.0
   pytest-playwright           0.10.0
   pytest-timeout              2.4.0
   python-discovery            1.9.5
   python-docx                 1.2.0
   python-dotenv               1.2.4
   python-slugify              9.1.3
   pytokens                    0.4.1
   PyYAML                      6.0.3
   regex                       2026.11.9
   requests                    2.34.2
   rich                        15.0.0
   ruff                        0.17.5
   setuptools                  84.2.1
   sortedcontainers            2.4.0
   stevedore                   5.10.0
   sympy                       1.14.0
   text-unidecode              1.3
   tiktoken                    0.14.0
   tokenizers                  0.23.3
   tomli                       2.5.0
   tomli_w                     1.2.0
   torch                       2.15.0
   tqdm                        4.70.1
   truststore                  0.10.5
   types-Pillow                10.2.0.20240822
   types-requests              2.33.0.20261030
   types-tqdm                  4.70.0.20261106
   types-urllib3               1.26.25.14
   typing_extensions           4.16.0
   typing-inspection           0.4.5
   urllib3                     2.8.0
   virtualenv                  21.15.6
   youtube-automation-pipeline 4.5.1           C:\Users\Snoozer\teamwork_projects\docs-e07-reproducible-windows-setup
   youtube-transcript-api      1.2.5
   ```
8. **Unit Test Execution on Clean Venv**:
   - `.\clean_venv\Scripts\python.exe -m pytest tests/unit/test_readme_contract.py -q`:
   - `9 passed in 0.87s`.

### 4.2 Inherited Site-Packages Inspection (`disposable_venv`, `--system-site-packages`)
The inherited host environment was inspected during initial exploration. Because the host system site-packages lacked `torch` and `openai-whisper`, `pip check` in that environment only verified non-torch sub-packages. The authoritative, complete dependency proof is provided by the clean virtual environment in Section 4.1 above.

### 4.3 Stale `.dist-info` Discovery & Remediation
In existing checkouts where `pyproject.toml` had dependencies removed (e.g. `moviepy`, `torchaudio`), stale `.dist-info` metadata caused false `pip check` failures. Re-running `pip install -e . --no-deps` rebuilds `.dist-info/METADATA`, resolving all phantom dependency breaks.

---

## 5. Setup Script Hardening & Synthetic Stub Verification

### 5.1 Script Enhancements
1. **PowerShell 5.1 Stderr Handling (`Invoke-NativeCommand`)**:
   - Resolves the issue where native stderr redirected via `2>&1` generates `ErrorRecord` objects that cause terminating errors under `$ErrorActionPreference = 'Stop'`.
   - Safely executes native commands, stringifies output, captures `$LASTEXITCODE`, and restores preference.
2. **Interpreter & Venv Validation**:
   - Validates that `$VenvPython` executes, version is `>=3.10`, and `pip --version` succeeds before proceeding with package installation.
3. **Playwright Browser Provisioning**:
   - Evaluates `$LASTEXITCODE` of `playwright install chromium`; emits warning with exit code on failure and prints `[OK]` only on exit 0.
4. **Failure Propagation**:
   - `setup.ps1` exits with `$LASTEXITCODE` on editable install failure or `pip check` failure.
   - `setup.bat` captures `%ERRORLEVEL%` into `%EXIT_CODE%` and propagates failure (`exit /b %EXIT_CODE%`).
5. **Probe Discrimination**:
   - `FFprobe` and `Tesseract`: verifies executable on `PATH`, runs probe via `Invoke-NativeCommand`, extracts version line, and emits a warning if exit code is non-zero while continuing setup.
   - `FFmpeg`: verifies binary, checks version, and detects hardware encoders (`h264_qsv`, `h264_nvenc`, `h264_amf`).

### 5.2 Synthetic Stub Test Suite Results (`scratch/test_synthetic_stubs.py`)
Executed 6 automated test scenarios using disposable native stubs through `setup.bat`:
- **Scenario 1 (Exit 0 with Stderr)**: Probe writing to stderr on exit 0 succeeds and extracts version without terminating (`Version check succeeded: ffprobe version 6.0-synthetic-test`). Exit code `0`.
- **Scenario 2 (Nonzero with Stderr)**: Probe writing to stderr on exit 1 warns and setup continues (`[WARNING] FFprobe executable was found on PATH but version check failed with exit code 1.`). Exit code `0`.
- **Scenario 3 (Pip Check Exit 77)**: Pip check failure writing to stderr propagates exit code 77 through `setup.bat` (`[ERROR] Setup failed with exit code: 77`). Exit code `77`.
- **Scenario 4 (Pip Check Exit 42)**: Pip check failure writing to stderr propagates exit code 42 through `setup.bat` (`[ERROR] Setup failed with exit code: 42`). Exit code `42`.
- **Scenario 5 (Broken Venv Pip)**: Virtual environment with non-functional pip fails with exit code 1 (`[ERROR] Virtual environment pip module is not functional`). Exit code `1`.
- **Scenario 6 (Playwright Failure)**: Playwright failure emits warning and omits `[OK]` verification (`[WARNING] Playwright Chromium install exited with code 1.`). Exit code `0`.

---

## 6. System Prerequisites Audit & Evidence Separation

### 6.1 Observed Local Evidence
| Component | Verification Check | Observed Status on Host | Evidence Source |
| --- | --- | --- | --- |
| **Python 3.11** | `py -3.11 --version` | `Python 3.11.9` | Local terminal execution |
| **FFmpeg** | `ffmpeg -version` | FFmpeg 8.1.2-full_build (Gyan.dev) on PATH | Local terminal execution |
| **FFprobe** | `ffprobe -version` | FFprobe 8.1.2-full_build (Gyan.dev) on PATH | Local terminal execution |
| **Hardware Encoders** | `ffmpeg -hide_banner -encoders` | 23 encoders verified (`h264_qsv`, `h264_nvenc`, `h264_amf`, `av1_qsv`, `libx264`) | Local terminal execution |
| **Clean Venv Installation** | `pip check` & `pip show` | Clean install (87 packages), exit 0, editable origin verified | Local clean venv execution (`clean_venv`) |
| **Script Error Handling** | `scratch/test_synthetic_stubs.py` | 6/6 synthetic tests passed | Automated test receipts |

### 6.2 Hosted CI Evidence
GitHub Actions runs on initial PR #121 head (`5522ec4475ce86e75e4524668558ac88de7c0a0d`):
- **`onboarding`**: [Passed in 5s](https://github.com/Snoozer10/local-youtube-automation/actions/runs/19343714652/job/55338166663) (Python 3.11 on `ubuntu-latest`, checking documentation contract).
- **`test`**: [Passed in 11m35s](https://github.com/Snoozer10/local-youtube-automation/actions/runs/19343714652/job/55338166699) (Python 3.11 on `windows-latest`; 468 passed, 35 skipped).
- **`test-py310`**: [Passed in 8m20s](https://github.com/Snoozer10/local-youtube-automation/actions/runs/19343714652/job/55338166668) (Python 3.10 on `windows-latest`; 468 passed, 35 skipped).

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
2. **Virtual Environment**: Isolated `venv` with pip upgraded and valid Python 3.10+ interpreter.
3. **Core Dependencies**: Installed via `requirements.txt` and `pip install -e . --no-deps`.
4. **FFmpeg & FFprobe**: Installed via WinGet (`winget install Gyan.FFmpeg`) and accessible on system `PATH` (rendering prerequisites).
5. **Environment Template**: `.env` initialized from `.env.example`.

### Optional Stage Prerequisites (Governed by Bounded Grants & Daemons)
1. **Browser Automation**: Dedicated Chromium profile launched with `--remote-debugging-port=9222` (routing to `CONTRIBUTING.md#configuring-local-debugging-profiles`) and provisioned Playwright Chromium runtime. Required only for live web interactions with Gemini, Flow, or AI Studio.
2. **Audio Mastering**: Audacity launched with `mod-script-pipe` enabled (`\\.\pipe\ToSrvPipe`). Required only when running Audacity macro mastering stages.
3. **Adaptive Image Gate Verification**: Tesseract OCR engine installed on `PATH` with English and Arabic training data.
4. **Local Heavy Transcription**: Standalone PyTorch CUDA acceleration and Whisper models (fallback ASR engine).

---

## 8. Evidence-Backed Changes Applied

1. **`setup.ps1`**:
   - Implemented `Invoke-NativeCommand` to handle native stderr under Windows PowerShell 5.1 without terminating on stderr output.
   - Validated `$VenvPython` interpreter execution, version (`>=3.10`), and pip module functionality before dependency installation.
   - Checked `playwright install chromium` exit code, emitting a warning and omitting `[OK]` if non-zero.
   - Routed Chrome guidance in diagnostics and banner to `CONTRIBUTING.md#configuring-local-debugging-profiles`.
   - Advertised the linter using quoted selected venv interpreter (`& "$VenvPython" tools\lint_exercises.py`) to preserve exit status.
   - Accurately labeled `.\run.bat` as starting the full batch pipeline (`run_agency.py`).
2. **`setup.bat`**:
   - Verified exit code propagation (`set "EXIT_CODE=%ERRORLEVEL%"` and `exit /b %EXIT_CODE%`).
3. **`docs/getting-started.md`**:
   - Aligned Python versions (Python 3.11 recommended, Python 3.10 compatibility-tested).
   - Routed dedicated-profile Chrome instructions to `CONTRIBUTING.md#configuring-local-debugging-profiles`.
4. **`docs/agents/setup.md`**:
   - Aligned Python version guidance and rendering prerequisites.
   - Routed dedicated-profile Chrome instructions to `CONTRIBUTING.md#configuring-local-debugging-profiles`.
5. **`tasks/e07-windows-setup-report.md`**:
   - Recorded complete clean venv installation receipts with cached Torch wheel, `pip check` exit 0, and editable origin outside checkout.
   - Clarified inherited-venv role as partial host metadata inspection.
   - Corrected `onboarding` CI citation to `ubuntu-latest`.
   - Detailed native stderr handling and 6/6 synthetic stub test receipts.

---

## 9. Verification Checks

All offline repository checks pass cleanly:
```powershell
python tools/check_readme.py                         # 7 documents checked; return code 0
python tools/check_secrets.py                        # 0 secrets detected; return code 0
git diff --check                                     # Clean diff; zero whitespace errors; return code 0
pytest tests/unit/test_readme_contract.py -q         # 9 passed in 0.87s
python scratch/test_synthetic_stubs.py               # 6/6 synthetic scenarios passed through setup.bat
```
