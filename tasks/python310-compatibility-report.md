# Windows Python 3.10 Compatibility & Runtime Verification Report
**Task E03: Resolve Supported-Runtime Promise with Bounded Windows Python 3.10 Compatibility Lane**
**Campaign Context**: Issue #78 (Architecture Renewal Campaign)
**Inventory Reference**: `tasks/REMAINING_WORK.md:85` (E03, P1 · Verify)
**Task Branch**: `ci/e03-python310-compat`
**Base Commit**: `105e6c2aa05bb039e1b29f757efd070767a06821` (`origin/master`)
**Date**: 2026-11-11

---

## 1. Executive Summary

This report documents the implementation, empirical offline verification, and hosted CI execution of **Task E03** under the **Architecture Renewal Campaign (Issue #78)**. Task E03 resolves the project's supported-runtime commitment by introducing a bounded native Windows Python 3.10 compatibility job (`test-py310`) in continuous integration (`.github/workflows/ci.yml`). This job provides compatibility coverage for the declared minimum runtime (`requires-python = ">=3.10"` in `pyproject.toml:11`), acknowledging that while upstream Python 3.10 has reached end of life, the package maintains backward-compatibility coverage across supported Windows installations.

The implementation verifies the conditional `tomli` dependency fallback on Python 3.10, preserves the SQLite observation method qualification test in its authoritative Python 3.11 lane, and preserves all existing Python 3.11 quality gates and the S04 secret-scanning gate.

### Key Deliverables & Outcomes:
1. **Bounded Windows Python 3.10 CI Compatibility Job (`test-py310`)**:
   - Added to `.github/workflows/ci.yml` targeting `windows-latest` with an explicit `timeout-minutes: 20` boundary.
   - Installs system prerequisites (`ffmpeg`, `audacity` via Chocolatey).
   - Upgrades `pip`, `setuptools`, `wheel`.
   - Verifies conditional `tomli` dependency resolution using `importlib.util.find_spec("tomllib")`.
   - Executes S04 secret-scanning gate (`python tools/check_secrets.py`).
   - Executes offline test suite: `python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"`.
   - Validates package distribution assembly: `python -m build --no-isolation --sdist --wheel`.
2. **Conditional `tomli` Dependency Verification**:
   - In Python 3.10, standard library `tomllib` is absent.
   - `pyproject.toml:28` and `requirements.txt:11` specify `tomli>=2.0.1; python_version < "3.11"`.
   - Verified with `importlib.util.find_spec("tomllib") is None` to ensure `tomllib` is genuinely unavailable in the module search path rather than merely not imported.
   - Verified that `tools/inventory_cleanup_candidates.py` and `tests/unit/test_cleanup_inventory.py` successfully import `tomli as tomllib` and execute without errors.
3. **Preservation of Python 3.11 SQLite Qualification Lane**:
   - `tests/unit/test_observation_method_proof.py::test_observation_environment_records_exact_runtime` explicitly requires `sys.version_info >= (3, 11)` as established under Issue #55 for SQLite observation qualification on Windows.
   - Preserved in the authoritative Python 3.11 `test` job.
   - Deselected from the Python 3.10 compatibility lane via `-k "not test_observation_environment_records_exact_runtime"`, preventing any weakening of qualification evidence.
4. **Preservation of Existing Python 3.11 Primary Gates**:
   - The primary `test` job in `.github/workflows/ci.yml` is untouched: Ruff linting, strict mypy source typing (84 files), S04 secret scanning, full offline test suite with coverage, and package builds remain enforced on Python 3.11.
5. **Runtime Environments & Empirical Receipts**:
   - **Local Isolated Environment**: CPython 3.10.20 (64-bit on Windows 10/11 x64).
     - Pytest offline suite: **2,410 passed, 2 skipped, 10 deselected in 280.01s (4m40s)**.
     - Strict typing (`mypy --strict src/`): **Success in 84 source files** (0 errors).
     - Workspace linting (`ruff check .`): **All checks passed**.
     - Secret scanning (`tools/check_secrets.py`): **0 secrets detected**.
     - Package builds: **Successfully built wheel and sdist**.
   - **Hosted CI Compatibility Job (`test-py310`, CPython 3.10.11)**:
     - Run 43035654936 Job 130573651732: **PASSED in 10m2s**.
     - Pytest offline suite: **2,410 passed, 2 skipped, 10 deselected in 248.15s (4m08s)**.
   - **Hosted CI Primary Job (`test`, CPython 3.11)**:
     - Run 43035654936 Job 130573652255: **PASSED in 11m44s**.
     - Pytest offline suite: **2,411 passed, 2 skipped, 9 deselected in 311.76s (5m11s)**.

---

## 2. CI Architecture & Workflow Configuration

### 2.1 Partitioned Workflow Structure

The CI workflow (`.github/workflows/ci.yml`) maintains strict separation between the authoritative Python 3.11 primary lane and the bounded Python 3.10 compatibility lane:

| Feature / Step | Primary Lane (`test`) | Compatibility Lane (`test-py310`) | Rationale |
| --- | --- | --- | --- |
| **OS Runner** | `windows-latest` | `windows-latest` | Native Windows environment requirement |
| **Python Version** | `3.11` (CPython 3.11 hosted) | `3.10` (CPython 3.10.11 hosted) | Authoritative runtime vs. declared minimum compatibility floor |
| **Timeout Ceiling** | Default | `20 minutes` | Bounded execution invariant |
| **System Tools** | FFmpeg + Audacity | FFmpeg + Audacity | Identical media processing environment |
| **Package Upgrades** | `pip setuptools wheel` | `pip setuptools wheel` | Clean packaging toolchain |
| **Dependencies** | `requirements.txt` + `requirements-dev.txt` | `requirements.txt` + `requirements-dev.txt` | Real dependency resolution per Python version |
| **`tomli` Step** | N/A (standard `tomllib` present) | Dedicated verification step | Confirms `tomli` availability and absence of `tomllib` via `find_spec` |
| **Secret Scanning Gate** | `tools/check_secrets.py` | `tools/check_secrets.py` | S04 quality gate enforced across both versions |
| **Linting & Typing** | `ruff check .` + `mypy --strict src/` | Optional / primary | Checked on authoritative 3.11 runner |
| **Test Command** | `pytest ... -m "not live_browser" --cov=.` | `pytest ... -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"` | Qualification test kept in 3.11 lane |
| **Coverage Report** | Generated (`--cov-report=xml`) | Omitted | Avoids coverage report collision |
| **Package Build** | `build --no-isolation --sdist --wheel` | `build --no-isolation --sdist --wheel` | Verifies distribution packaging on both versions |

### 2.2 Workflow Configuration in `.github/workflows/ci.yml`

```yaml
  test-py310:
    runs-on: windows-latest
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v6.0.2

      - name: Set up Python 3.10
        uses: actions/setup-python@v6.2.0
        with:
          python-version: "3.10"
          cache: "pip"

      - name: Install system dependencies
        run: |
          choco install ffmpeg audacity -y --no-progress
          "C:\ProgramData\chocolatey\bin" | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
          # Note: Audacity mod-script-pipe requires manual enable in CI
        shell: pwsh

      - name: Upgrade pip, setuptools, wheel
        run: python -m pip install --upgrade pip setuptools wheel

      - name: Install production dependencies
        run: pip install -r requirements.txt

      - name: Install development/test dependencies
        run: |
          pip install -r requirements-dev.txt
          python -m playwright install --with-deps

      - name: Verify conditional tomli dependency
        run: |
          python -c "import importlib.util, sys, tomli; assert importlib.util.find_spec('tomllib') is None, 'tomllib must be unavailable on Python 3.10'; print(f'tomli {tomli.__version__} verified under Python {sys.version}')"

      - name: Quality gate (secret scanning)
        run: python tools/check_secrets.py

      - name: Run offline tests (Python 3.10 compatibility)
        run: python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"

      - name: Package build check
        run: python -m build --no-isolation --sdist --wheel
```

---

## 3. Conditional Dependency (`tomli`) Verification

### 3.1 Dependency Declaration Contract
- `pyproject.toml:28`: `"tomli>=2.0.1; python_version < '3.11'"`
- `requirements.txt:11`: `tomli>=2.0.1; python_version < "3.11"  # TOML parser fallback for Python 3.10`

### 3.2 Observed Runtime Behavior & `find_spec` Verification
1. **Unavailability Check**:
   Using `importlib.util.find_spec("tomllib")` strictly verifies that `tomllib` is absent from `sys.meta_path` and the standard library module search path:
   ```powershell
   python -c "import importlib.util; assert importlib.util.find_spec('tomllib') is None"
   ```
   This is strictly superior to checking `sys.modules`, which only confirms whether the module has already been imported into memory.
2. **`tomli` Availability**:
   On Python 3.10 (both local 3.10.20 and hosted 3.10.11), `import tomli` resolves `tomli 2.5.0`.
   ```powershell
   python -c "import importlib.util, sys, tomli; assert importlib.util.find_spec('tomllib') is None, 'tomllib must be unavailable on Python 3.10'; print(f'tomli {tomli.__version__} verified under Python {sys.version}')"
   # Output: tomli 2.5.0 verified under Python 3.10.20 (main, Jun 23 2026, 15:19:56) [MSC v.1944 64 bit (AMD64)]
   ```
3. **Codebase Consumers**:
   - `tools/inventory_cleanup_candidates.py`:
     ```python
     try:
         import tomllib
     except ModuleNotFoundError:  # Python 3.10 compatibility
         import tomli as tomllib
     ```
     Executed against repo root: `Audited targets: 30 | Actionable cleanup candidates: 3` (exit code 0).
   - `tests/unit/test_cleanup_inventory.py::test_scanner_falls_back_to_tomli_when_tomllib_is_unavailable`:
     Passed in 7.19s alongside all 7 module unit tests.

---

## 4. Test Selection & Exclusion Rationale

### 4.1 Excluded Test Node (1 item):
- **Node ID**: `tests/unit/test_observation_method_proof.py::test_observation_environment_records_exact_runtime`
- **Reason for Exclusion**:
  ```python
  def test_observation_environment_records_exact_runtime() -> None:
      """AC 1: Record the actual interpreter, linked SQLite build, and OS entrypoint."""
      assert sys.version_info >= (3, 11)
      assert sqlite3.sqlite_version >= "3.40"
      assert platform.system() == "Windows"
  ```
  This assertion anchors the exact qualification receipt of the Windows SQLite read-only observation method under Issue #55, qualified on Python >=3.11. Keeping this check in the Python 3.11 primary lane preserves qualification evidence without weakening the qualification requirement, while permitting all other 17 functional invariant tests in `test_observation_method_proof.py` to pass on Python 3.10.
- **Selection Expression**: `-k "not test_observation_environment_records_exact_runtime"`

### 4.2 Deselected Live Browser Tests (9 items):
- **Marker**: `@pytest.mark.live_browser`
- **Reason**: Standard offline CI boundary (Task E02 / PR #86). Live browser tests require active CDP Chrome/Opera instances and external network interaction, excluded from offline CI gates.
- **Selection Expression**: `-m "not live_browser"`

### 4.3 Consistent Skipped Tests (2 items):
- **Node IDs**:
  - `tests/unit/test_timeline_quantization_invariants.py::test_canonical_timeline_ingestion_bypasses_resnapping`
  - `tests/unit/test_timeline_quantization_invariants.py::test_cumulative_integer_quantization_zero_drift`
- **Reason**: Skip condition triggers due to absence of uncommitted historical fixture `youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/timeline.json`. Exactly matches the skip behavior observed in Python 3.11 CI.

---

## 5. Empirical Verification Results

### 5.1 Local Offline Verification (CPython 3.10.20 on Windows 10/11 x64)
- **Interpreter**: `CPython 3.10.20 (main, Jun 23 2026, 15:19:56) [MSC v.1944 64 bit (AMD64)]`
- **Test Command**:
  ```powershell
  python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"
  ```
- **Observed Counts**:
  - Collected: 2,422 items
  - Selected: 2,412 items
  - Deselected: 10 items (9 `live_browser` + 1 SQLite qualification test)
  - **Passed: 2,410 items**
  - **Skipped: 2 items** (timeline fixture absence)
  - **Failed: 0 items**
  - **Execution Time**: 280.01 seconds (4 minutes 40 seconds)
- **Quality Gates**:
  - Secret Scanning (`python tools/check_secrets.py`): `Secret scanning gate passed: 0 secrets detected across tracked files.`
  - Strict Typing (`python -m mypy --strict src/`): `Success: no issues found in 84 source files`
  - Workspace Linting (`ruff check .`): `All checks passed!`
  - Package Builds (`python -m build --no-isolation --sdist --wheel`): Built `youtube_automation_pipeline-4.5.1.tar.gz` and `youtube_automation_pipeline-4.5.1-py3-none-any.whl`.

### 5.2 Hosted CI Verification (GitHub Actions Run 43035654936)

| Metric | Hosted Compatibility Job (`test-py310`) | Hosted Primary Job (`test`) |
| --- | --- | --- |
| **Job ID** | `130573651732` | `130573652255` |
| **Interpreter** | CPython 3.10.11 (64-bit Windows) | CPython 3.11 (64-bit Windows) |
| **Total Job Duration** | 10 minutes 2 seconds | 11 minutes 44 seconds |
| **Pytest Log Duration** | **248.15 seconds (4m 08s)** | **311.76 seconds (5m 11s)** |
| **Items Collected** | 2,422 items | 2,422 items |
| **Items Selected** | 2,412 items | 2,413 items |
| **Items Passed** | **2,410 passed** | **2,411 passed** |
| **Items Skipped** | **2 skipped** | **2 skipped** |
| **Items Deselected** | **10 deselected** (9 `live_browser` + 1 SQLite) | **9 deselected** (9 `live_browser`) |
| **`tomli` Step** | `tomli 2.5.0` verified (`tomllib` unavailable) | N/A |
| **Secret Scanning Gate** | 0 secrets detected (exit code 0) | 0 secrets detected (exit code 0) |
| **Package Build** | Wheel + Sdist built successfully | Wheel + Sdist built successfully |
| **Linting & Typing** | Enforced via authoritative primary lane | `ruff check .` + strict mypy (84 files) passed |

---

## 6. Verification Lineage & Receipts

- **Base Commit**: `105e6c2aa05bb039e1b29f757efd070767a06821`
- **Local Isolated Python**: `CPython 3.10.20 (64-bit)`
- **Hosted CI Python (3.10)**: `CPython 3.10.11 (64-bit)` in `c:\hostedtoolcache\windows\python\3.10.11\x64`
- **Hosted CI Python (3.11)**: `CPython 3.11 (64-bit)` in `c:\hostedtoolcache\windows\python\3.11.x\x64`
- **`git diff --check`**: Clean (0 errors, 0 whitespace warnings, pure LF line endings preserved).
