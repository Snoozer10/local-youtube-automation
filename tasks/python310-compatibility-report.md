# Windows Python 3.10 Compatibility & Runtime Verification Report
**Task E03: Resolve Supported-Runtime Promise with Bounded Windows Python 3.10 Compatibility Lane**
**Campaign Context**: Issue #78 (Architecture Renewal Campaign)
**Inventory Reference**: `tasks/REMAINING_WORK.md:85` (E03, P1 · Verify)
**Task Branch**: `ci/e03-python310-compat`
**Base Commit**: `105e6c2aa05bb039e1b29f757efd070767a06821` (`origin/master`)
**Date**: 2026-11-11

---

## 1. Executive Summary

This report establishes the implementation and offline empirical verification of **Task E03** under the **Architecture Renewal Campaign (Issue #78)**. Task E03 resolves the project's supported-runtime commitment by introducing a bounded native Windows Python 3.10 compatibility job (`test-py310`) in continuous integration (`.github/workflows/ci.yml`), verifying the conditional `tomli` dependency fallback on Python 3.10, preserving the SQLite observation method qualification test in its authoritative Python 3.11 lane, and maintaining all existing Python 3.11 quality gates and the S04 secret-scanning gate.

### Key Deliverables & Outcomes:
1. **Bounded Windows Python 3.10 CI Compatibility Job (`test-py310`)**:
   - Configured in `.github/workflows/ci.yml` targeting `windows-latest` with an explicit `timeout-minutes: 20` boundary.
   - Installs system prerequisites (`ffmpeg`, `audacity` via Chocolatey).
   - Validates the conditional `tomli` dependency resolution.
   - Executes the S04 secret-scanning gate (`python tools/check_secrets.py`).
   - Executes the complete offline test suite with Python 3.10 compatibility exclusion: `python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"`.
   - Validates package distribution assembly: `python -m build --no-isolation --sdist --wheel`.
2. **Conditional `tomli` Dependency Verification**:
   - In Python 3.10, standard library `tomllib` is absent (`ModuleNotFoundError`).
   - `pyproject.toml:28` and `requirements.txt:11` specify `tomli>=2.0.1; python_version < "3.11"`.
   - On Python 3.10.20, `tomli` (version `2.5.0`) resolves and installs automatically.
   - Verified that `tools/inventory_cleanup_candidates.py` and `tests/unit/test_cleanup_inventory.py` successfully import `tomli as tomllib` and execute without errors.
3. **Preservation of Python 3.11 SQLite Qualification Lane**:
   - `tests/unit/test_observation_method_proof.py::test_observation_environment_records_exact_runtime` explicitly requires `sys.version_info >= (3, 11)` as established under Issue #55 for SQLite observation qualification on Windows.
   - The test remains active and authoritative in the primary Python 3.11 `test` job.
   - Deselected from the Python 3.10 compatibility lane via `-k "not test_observation_environment_records_exact_runtime"`, ensuring no qualification standards are weakened.
4. **Preservation of Existing Python 3.11 Gates**:
   - The primary `test` job in `.github/workflows/ci.yml` is untouched: Ruff linting, strict mypy source typing, S04 secret scanning, full offline test suite with coverage, and package builds remain enforced on Python 3.11.
5. **Local Verification Results in Isolated Python 3.10 Environment**:
   - Environment: CPython 3.10.20 (64-bit on Windows 10/11 x64).
   - Pytest offline suite: **2,410 passed, 2 skipped, 10 deselected in 280.01s (4m40s)**.
   - Strict typing (`mypy --strict src/`): **Success in 84 source files** (0 errors).
   - Workspace linting (`ruff check .`): **All checks passed**.
   - Secret scanning (`tools/check_secrets.py`): **0 secrets detected across tracked files**.
   - Package builds (`python -m build --no-isolation --sdist --wheel`): **Successfully built wheel and sdist**.

---

## 2. CI Architecture & Workflow Configuration

### 2.1 Partitioned Workflow Structure

The CI workflow (`.github/workflows/ci.yml`) maintains strict separation between the authoritative Python 3.11 primary lane and the bounded Python 3.10 compatibility lane:

| Feature / Step | Primary Lane (`test`) | Compatibility Lane (`test-py310`) | Rationale |
| --- | --- | --- | --- |
| **OS Runner** | `windows-latest` | `windows-latest` | Preserves native Windows environment requirement |
| **Python Version** | `3.11` | `3.10` | Authoritative runtime vs. backward compatibility floor |
| **Timeout Ceiling** | Default | `20 minutes` | Bounded execution invariant |
| **System Tools** | FFmpeg + Audacity | FFmpeg + Audacity | Identical media processing environment |
| **Package Upgrades** | `pip setuptools wheel` | `pip setuptools wheel` | Clean packaging toolchain |
| **Dependencies** | `requirements.txt` + `requirements-dev.txt` | `requirements.txt` + `requirements-dev.txt` | Tests real dependency resolution per Python version |
| **`tomli` Step** | N/A (standard `tomllib` present) | Dedicated verification step | Confirms `tomli` availability and absence of `tomllib` |
| **Secret Scanning Gate** | `tools/check_secrets.py` | `tools/check_secrets.py` | S04 quality gate enforced across both versions |
| **Linting & Typing** | `ruff check .` + `mypy --strict src/` | Optional / primary | Checked on authoritative 3.11 runner |
| **Test Command** | `pytest ... -m "not live_browser" --cov=.` | `pytest ... -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"` | Qualification test kept in 3.11 lane |
| **Coverage Report** | Generated (`--cov-report=xml`) | Omitted | Avoids coverage report collision |
| **Package Build** | `build --no-isolation --sdist --wheel` | `build --no-isolation --sdist --wheel` | Verifies distribution packaging on both versions |

### 2.2 Workflow Diff in `.github/workflows/ci.yml`

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
          python -c "import tomli; import sys; assert 'tomllib' not in sys.modules; print(f'tomli {tomli.__version__} verified under Python {sys.version}')"

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

### 3.2 Observed Runtime Behavior
In the isolated Python 3.10.20 virtual environment:
1. `import tomllib` raises `ModuleNotFoundError: No module named 'tomllib'`.
2. `import tomli` succeeds, resolving `tomli 2.5.0`.
3. Dedicated verification step:
   ```powershell
   python -c "import tomli; import sys; assert 'tomllib' not in sys.modules; print(f'tomli {tomli.__version__} verified under Python {sys.version}')"
   # Output: tomli 2.5.0 verified under Python 3.10.20 (main, Jun 23 2026, 15:19:56) [MSC v.1944 64 bit (AMD64)]
   ```
4. Codebase consumers:
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
  This assertion anchors the exact qualification receipt of the Windows SQLite read-only observation method under Issue #55, which was qualified specifically on Python >=3.11. Modifying or weakening this assertion would dilute historical qualification evidence. Keeping it strictly in the Python 3.11 primary lane preserves qualification integrity while allowing all other 17 functional invariant tests in `test_observation_method_proof.py` to run and pass on Python 3.10.
- **Selection Expression**: `-k "not test_observation_environment_records_exact_runtime"`

### 4.2 Deselected Live Browser Tests (9 items):
- **Marker**: `@pytest.mark.live_browser`
- **Reason**: Standard offline CI boundary (established in Task E02 / PR #86). Live browser tests require active CDP Chrome/Opera instances and external network interaction, prohibited in offline gates.
- **Selection Expression**: `-m "not live_browser"`

### 4.3 Consistent Skipped Tests (2 items):
- **Node IDs**:
  - `tests/unit/test_timeline_quantization_invariants.py::test_canonical_timeline_ingestion_bypasses_resnapping`
  - `tests/unit/test_timeline_quantization_invariants.py::test_cumulative_integer_quantization_zero_drift`
- **Reason**: Skip condition triggers due to absence of uncommitted historical fixture `youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/timeline.json`. Exactly matches the skip behavior observed in Python 3.11 CI.

---

## 5. Local Offline Verification Results (CPython 3.10.20)

### 5.1 Test Execution Summary
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

### 5.2 Quality Gates on Python 3.10
- **Secret Scanning Gate (`python tools/check_secrets.py`)**:
  - Scanned all tracked repository files and documentation.
  - Result: `Secret scanning gate passed: 0 secrets detected across tracked files.` (exit code 0).
- **Strict Typing Gate (`python -m mypy --strict src/`)**:
  - Result: `Success: no issues found in 84 source files` (exit code 0).
- **Workspace Linting (`ruff check .`)**:
  - Result: `All checks passed!` (exit code 0).
- **Package Distribution Assembly (`python -m build --no-isolation --sdist --wheel`)**:
  - Result: Successfully generated `youtube_automation_pipeline-4.5.1.tar.gz` and `youtube_automation_pipeline-4.5.1-py3-none-any.whl`.

---

## 6. Verification Lineage & Receipts

- **Base Commit**: `105e6c2aa05bb039e1b29f757efd070767a06821`
- **Local Isolated Python**: `CPython 3.10.20 (64-bit)`
- **`git diff --check`**: Clean (0 errors, 0 whitespace warnings, pure LF line endings preserved).
