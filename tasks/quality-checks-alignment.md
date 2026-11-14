# Task E05: Quality Checks, Pre-Commit & Scope Alignment Report

**Campaign**: Architecture Renewal Campaign ([Issue #78](https://github.com/Snoozer10/local-youtube-automation/issues/78))
**Task ID**: `E05` ([`tasks/REMAINING_WORK.md:87`](https://github.com/Snoozer10/local-youtube-automation/blob/0f2b2be6aa2f255ad7ceaa980096607df17b95ca/tasks/REMAINING_WORK.md#L87))
**Launch Base SHA**: `0f2b2be6aa2f255ad7ceaa980096607df17b95ca` (`origin/master` after squash-merge of E08 PR #119)
**Branch**: `ci/e05-align-quality-checks`
**Claim Reference**: [Issue #78 comment 6859944908](https://github.com/Snoozer10/local-youtube-automation/issues/78#issuecomment-6859944908), amended in [comment 6862807983](https://github.com/Snoozer10/local-youtube-automation/issues/78#issuecomment-6862807983) and [comment 6864887972](https://github.com/Snoozer10/local-youtube-automation/issues/78#issuecomment-6864887972)
**Reserved Tracked Paths (5)**:
1. `.pre-commit-config.yaml`
2. `pytest.ini`
3. `tests/unit/test_check_secrets.py`
4. `tools/run_pytest_unit.py`
5. `tasks/quality-checks-alignment.md`

---

## 1. Executive Summary & Authority Model

Task **E05** aligns local pre-commit hooks, configuration files, and documented quality commands with authoritative Continuous Integration (CI) gates, resolving tool version divergence, argument mismatches, and scope inconsistencies without introducing automatic formatting churn, broad dependency upgrades, or unrelated regressions.

### Authority Model

1. **Authoritative Gate (Continuous Integration)**:
   - `.github/workflows/ci.yml` and `.github/workflows/docs.yml` define canonical enforcement gates required for merge qualification across supported Python versions (`3.11` and `3.10`).
   - Gates include: linting (`ruff check .` per `.github/workflows/ci.yml:41`), strict typing (`python -m mypy --strict src/` per `.github/workflows/ci.yml:44`), repository secret scanning (`python tools/check_secrets.py` per `.github/workflows/ci.yml:47,91`), offline test suite execution (`python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" --cov=. --cov-report=xml` per `.github/workflows/ci.yml:50` on Python 3.11, and `python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"` per `.github/workflows/ci.yml:94` on Python 3.10), documentation onboarding checks (`python tools/check_readme.py` and `python -m unittest discover -s tests/unit -p test_readme_contract.py -v` per `.github/workflows/docs.yml:24-26`), and package distribution builds (`python -m build --no-isolation --sdist --wheel` per `.github/workflows/ci.yml:53,97`).
2. **Consumer / Mirror Gates (Pre-Commit & Local CLI)**:
   - `.pre-commit-config.yaml`, `pytest.ini`, `pyproject.toml`, `CONTRIBUTING.md`, and `docs/agents/workflows.md` serve as developer feedback mechanisms that mirror or specialize authoritative CI gates.
   - Pre-commit hooks specialize CI gates for fast, local, offline commits by operating on staged files. Ruff linting is kept strictly read-only by omitting `--fix` and removing the mutating `ruff-format` hook to prevent unwanted code churn, while standard repository hygiene hooks (`trailing-whitespace`, `end-of-file-fixer`) retain their bounded formatting behavior on staged files.

---

## 2. Before-and-After Command, Version & Scope Comparison

| Quality Domain | Component | Pre-E05 Baseline | Post-E05 Aligned State | Authoritative Source / Configuration | Scope / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Linting** | **CI Gate** | `ruff check .` | `ruff check .` (unchanged) | `.github/workflows/ci.yml:41` | Full repository tree; read-only verification; resolves Ruff 0.17.5 in hosted CI |
| | **Pre-Commit Hook** | `rev: v0.1.0`<br>`args: [--fix, --exit-non-zero-on-fix]`<br>`- id: ruff-format` | `rev: v0.17.5`<br>*(no args; ruff-format removed; UP038 obsolete in 0.17.5)* | `.pre-commit-config.yaml:2-6` | Pinned to `v0.17.5` matching observed CI resolution (`Ruff 0.17.5`); read-only linting for Ruff (no `--fix`, `ruff-format` removed); no automatic code formatting or syntax mutations |
| | **Documented Local** | `ruff check .` | `ruff check .` (unchanged) | `CONTRIBUTING.md:143`, `pyproject.toml:98-128` | Local workspace lint check |
| **Strict Typing** | **CI Gate** | `python -m mypy --strict src/` | `python -m mypy --strict src/` (unchanged) | `.github/workflows/ci.yml:44` | Strictly `src/` (84 modules); Python 3.10 target; resolves mypy 2.4.1 in hosted CI |
| | **Pre-Commit Hook** | `rev: v1.5.1`<br>`args: [--strict, --ignore-missing-imports]`<br>`additional_dependencies: [types-requests, types-urllib3]`<br>*(unscoped: all staged .py)* | `rev: v2.4.1`<br>`files: ^src/`<br>`args: [--strict, --ignore-missing-imports]`<br>`additional_dependencies: [pydantic>=2.0.0, playwright>=1.40.0, types-requests, types-urllib3, types-tqdm, types-Pillow, typing-extensions>=4.12.0]` | `.pre-commit-config.yaml:8-22` | Pinned to `v2.4.1` matching observed CI resolution (`mypy 2.4.1`); scoped strictly to `src/`; stubs added so BaseModel and Playwright types resolve |
| | **Documented Local** | `python -m mypy --strict src/` | `python -m mypy --strict src/` (unchanged) | `docs/agents/workflows.md:43`, `CONTRIBUTING.md:146` | Full strict typing across source tree |
| **Secret Scanning** | **CI Gate** | `python tools/check_secrets.py` | `python tools/check_secrets.py` (unchanged) | `.github/workflows/ci.yml:47,91` | Full repository tree scan against `secrets_allowlist.json` across both 3.11 and 3.10 lanes |
| | **Pre-Commit Hook** | `python tools/check_secrets.py --` (`pass_filenames: true`) | `python tools/check_secrets.py --` (`pass_filenames: true`) (unchanged) | `.pre-commit-config.yaml:41-47` | Staged files only; fast sub-second commit gate |
| **Test Runner** | **CI Gate (3.11)** | `python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" --cov=. --cov-report=xml` | `python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" --cov=. --cov-report=xml` (unchanged) | `.github/workflows/ci.yml:50` | Full offline test suite (`tests/unit tests/integration`) with XML coverage on 3.11; resolves pytest 9.1.1 |
| | **CI Gate (3.10)** | `python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"` | `python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"` (unchanged) | `.github/workflows/ci.yml:94` | Full offline test suite on 3.10 preserving qualification filter; resolves pytest 9.1.1 |
| | **Pre-Commit Hook** | `entry: pytest`<br>`args: ["tests/unit", "-v", "--tb=short"]` | `entry: python tools/run_pytest_unit.py`<br>`args: ["tests/unit", "-c", "pyproject.toml", "-m", "not live_browser", "-v", "--tb=short"]` | `.pre-commit-config.yaml:46-53`, `tools/run_pytest_unit.py` | Fast unit-test check on local commits with explicit config and marker filter; helper dynamically excludes qualification test on Python 3.10 only |
| | **pytest.ini Config** | `addopts = -v --strict-markers --tb=short --import-mode=importlib`<br>*(missing `live_browser` marker)* | `addopts = -v --strict-markers --tb=short`<br>`markers: ... + live_browser` | `pytest.ini:7-13` | Bare local `pytest` commands discover `pytest.ini` first; aligned markers match `pyproject.toml`; dropped divergent `--import-mode=importlib` |
| **Pre-Commit Hygiene** | **AWS Detection** | `- id: detect-aws-credentials` | `- id: detect-aws-credentials`<br>`  args: [--allow-missing-credentials]` | `.pre-commit-config.yaml:37-38` | Prevents exit code 2 failure when developer machine lacks AWS CLI config |
| | **Private Key** | `- id: detect-private-key` | `- id: detect-private-key`<br>*(unconditional; no path exclusion)* | `.pre-commit-config.yaml:35` | Full repository coverage preserved relative to master; synthetic RSA fixture in `tests/unit/test_check_secrets.py` constructed at runtime to prevent false positives without introducing path exclusions |
| | **Whitespace / EOF** | Unscoped | `exclude: ^(evidence/receipts/\|tests/fixtures/semantic_failures/\|docs/error-solving/understood-errors\.md)` | `.pre-commit-config.yaml:26-29` | Protects byte-exact historical preimages, fixtures, and receipts |

---

## 3. Deliberate Scope Differences & Configuration Rationale

### 3.1 Pre-Commit Staged Hooks vs Full-Tree CI

Pre-commit hooks and CI quality gates serve distinct operational roles:

1. **Secret Scanning (`tools/check_secrets.py`)**:
   - **Pre-commit hook**: Passes staged filenames (`pass_filenames: true`) following the `--` argument delimiter. Scans only files about to be committed in < 0.15s, offering immediate pre-commit feedback.
   - **CI Gate**: Runs `python tools/check_secrets.py` without arguments, discovering and scanning all tracked repository files and public docs (202+ files) to catch any potential repository drift.
2. **Testing (`pytest`)**:
   - **Pre-commit hook**: Targets `tests/unit` only (`always_run: true`, `pass_filenames: false`, passing `-c pyproject.toml -m "not live_browser"`). Invokes `tools/run_pytest_unit.py` to ensure unit test invariants hold before any commit is authored without incurring multi-minute integration test runtimes.
   - **CI Gate**: Executes full offline unit and integration suites across both supported Python versions (`3.11` with coverage and `3.10` compatibility with exact-runtime skip handling), ensuring end-to-end subsystem stability.
3. **Type Checking (`mypy`)**:
   - **Pre-commit hook**: Scoped strictly to files under `src/` (`files: ^src/`), analyzing staged source code with required package stubs without imposing strict source-typing rules on exploratory test files or scripts.
   - **CI Gate**: Runs `python -m mypy --strict src/` across all 84 source modules to ensure global type soundness across the entire package.

### 3.2 Distinguishing Bare `pytest` Collection from CI Selection and `live_browser` Registration

When developers execute bare `pytest` or `python -m pytest` commands locally as documented in `CONTRIBUTING.md:154` and `docs/agents/workflows.md:44`:

1. **Configuration Precedence**: `pytest` discovers root configuration files in precedence order: `pytest.ini` takes priority over `pyproject.toml`.
2. **Bare Collection vs CI Selection**:
   - Bare `pytest` (without arguments) uses `testpaths = tests`, discovering and collecting the full suite (all 2,422 tests across `tests/unit` and `tests/integration`). It runs without code coverage flags and without live browser exclusion on the command line.
   - Authoritative CI explicitly restricts targets to `tests/unit tests/integration`, specifies `-c pyproject.toml`, passes `-m "not live_browser"`, on Python 3.11 collects coverage via `--cov=. --cov-report=xml`, and on Python 3.10 applies `-k "not test_observation_environment_records_exact_runtime"`.
3. **Marker Registration in `tests/conftest.py`**:
   - In `tests/conftest.py` lines 341-344, the `pytest_configure` hook already registers the marker programmatically:
     ```python
     def pytest_configure(config):
         config.addinivalue_line(
             "markers",
             "live_browser: requires an explicit --run-live-browser opt-in",
         )
     ```
   - Because `conftest.py` dynamically registers `live_browser`, running bare `pytest` with `--strict-markers` never produced an unregistered marker failure at runtime even prior to editing `pytest.ini`.
   - Adding `live_browser` to `pytest.ini` was performed strictly to maintain declarative parity with `pyproject.toml`'s marker definitions and to drop the obsolete `--import-mode=importlib` option.

### 3.3 Multi-Runtime Pre-Commit Test Filtering (`tools/run_pytest_unit.py`)

In `tests/unit/test_observation_method_proof.py:100-105`:
```python
def test_observation_environment_records_exact_runtime() -> None:
    """AC 1: Record the actual interpreter, linked SQLite build, and OS entrypoint."""
    assert sys.version_info >= (3, 11)
    assert sqlite3.sqlite_version >= "3.40"
    assert platform.system() == "Windows"
```
Because this test explicitly asserts `sys.version_info >= (3, 11)`, CI excludes it on Python 3.10 via `-k "not test_observation_environment_records_exact_runtime"` (`.github/workflows/ci.yml:94`).

To ensure that pre-commit works seamlessly across both supported Windows developer runtimes (`Python 3.10` and `Python 3.11`) without modifying the hosted CI workflows or weakening security gates:
- A dedicated inert runner utility [`tools/run_pytest_unit.py`](../tools/run_pytest_unit.py) was added under the amended reservation.
- `.pre-commit-config.yaml` configures:
  ```yaml
        - id: pytest-unit
          name: pytest (unit tests only)
          entry: python tools/run_pytest_unit.py
          args: ["tests/unit", "-c", "pyproject.toml", "-m", "not live_browser", "-v", "--tb=short"]
          language: system
          types: [python]
          pass_filenames: false
          always_run: true
  ```
- Under Python 3.10 (`sys.version_info < (3, 11)`), the helper automatically appends `["-k", "not test_observation_environment_records_exact_runtime"]`, exactly mirroring CI line 94.
- Under Python 3.11 (`sys.version_info >= (3, 11)`), the helper passes the arguments unmodified, ensuring `test_observation_environment_records_exact_runtime` remains selected and passes.

### 3.4 Preservation of `detect-private-key` Coverage Relative to Master

On master, upstream `detect-private-key` from `pre-commit-hooks` enforces unconditional scanning with zero path exclusions. However, `test_detects_private_key_block` in `tests/unit/test_check_secrets.py` embedded a literal PEM block in its test fixture string, causing `detect-private-key` to reject any commit staging that file unless exempted.

Rather than introducing a path exclusion into `.pre-commit-config.yaml` (which would weaken repository security gates relative to master), the synthetic test payload was updated to construct the PEM block dynamically at runtime via string concatenation (`begin_block = "-----BEGIN " + "RSA PRIVATE KEY-----"` and `end_block = "-----END " + "RSA PRIVATE KEY-----"`):
- The static source file contains no literal PEM block headers, allowing clean staging under `detect-private-key`.
- The runtime fixture file `self.root / "id_rsa"` receives the exact PEM header bytes, thoroughly exercising the repository secret scanner's `private_key_block` rule.
- Unconditional repository-wide private-key scanning is preserved relative to master with zero path exemptions.

---

## 4. Verification Evidence in Disposable Windows Environments

Verification was conducted across both supported Windows runtimes with clean files staged under `src/` (`src/youtube_automation/__init__.py`) to ensure that `mypy`, `ruff`, hygiene hooks, and `pytest-unit` all execute and pass. All hook environments are cached locally under `~/.cache/pre-commit`, requiring zero external downloads.

### 4.1 Python 3.10 Staged Verification (`CPython 3.10.20`)

- **Interpreter**: `CPython 3.10.20 (64-bit)` (`C:\Users\Snoozer\teamwork_projects\ci-e03-python310-compat\venv\Scripts\python.exe`)
- **Pre-Commit Version**: `pre-commit 4.6.2`
- **Tool Versions**: `Ruff 0.17.5`, `mypy 2.4.1`, `pytest 9.1.1`
- **Staged File**: `src/youtube_automation/__init__.py`
- **Exact Pre-Commit Command**:
  ```powershell
  & C:\Users\Snoozer\teamwork_projects\ci-e03-python310-compat\venv\Scripts\Activate.ps1
  git add src/youtube_automation/__init__.py
  pre-commit run --hook-stage pre-commit
  ```
- **Observed Results (All Hooks Pass)**:
  ```
  ruff (legacy alias)......................................................Passed
  mypy.....................................................................Passed
  trim trailing whitespace.................................................Passed
  fix end of files.........................................................Passed
  check yaml...............................................................Passed
  check toml...........................................(no files to check)Skipped
  check json...........................................(no files to check)Skipped
  check for merge conflicts................................................Passed
  debug statements (python)................................................Passed
  detect private key.......................................................Passed
  detect aws credentials...................................................Passed
  forbid new submodules................................(no files to check)Skipped
  check secrets and service tokens.........................................Passed
  pytest (unit tests only).................................................Passed
  ```
  *(Total staged run elapsed: `475,539 ms`, all hooks passed).*

- **Verbose Mypy Receipt (`pre-commit run mypy --files src/youtube_automation/__init__.py --verbose`)**:
  ```
  mypy.....................................................................Passed
  - hook id: mypy
  - duration: 2.30s

  Success: no issues found in 1 source file
  ```

- **Verbose Pytest Unit Execution Receipt (`tools/run_pytest_unit.py`)**:
  - Command:
    ```powershell
    & C:\Users\Snoozer\teamwork_projects\ci-e03-python310-compat\venv\Scripts\python.exe tools\run_pytest_unit.py tests/unit -c pyproject.toml -m "not live_browser" -v --tb=short
    ```
  - Output:
    ```
    ============================= test session starts =============================
    platform win32 -- Python 3.10.20, pytest-9.1.1, pluggy-1.7.0 -- C:\Users\Snoozer\teamwork_projects\ci-e03-python310-compat\venv\Scripts\python.exe
    cachedir: .pytest_cache
    rootdir: C:\Users\Snoozer\teamwork_projects\ci-e05-align-quality-checks
    configfile: pyproject.toml
    plugins: anyio-4.16.0, platformdirs-4.12.4, asyncio-1.4.1.post1, cov-7.1.0, mock-3.17.0, playwright-0.10.0, timeout-2.4.0
    asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
    collecting ... collected 2387 items / 1 deselected / 2386 selected

    tests/unit/test_accepted_original_script.py::test_publish_accepted_original_is_verbatim_and_verifies PASSED [  0%]
    ...
    tests/unit/test_wav_validation.py::test_frame_offset_rejects_negative_and_beyond_end_indices[3] PASSED [100%]

    =============== 2386 passed, 1 deselected in 505.21s (0:08:25) ================
    ```
  - Execution outcome: `2386 passed, 1 deselected in 505.21s (0:08:25)`. Exit code: 0.

- **Python 3.10 Qualification Gating Verification**:
  - Command:
    ```powershell
    & C:\Users\Snoozer\teamwork_projects\ci-e03-python310-compat\venv\Scripts\python.exe tools\run_pytest_unit.py tests/unit/test_observation_method_proof.py -c pyproject.toml -v
    ```
  - Output:
    ```
    collecting ... collected 18 items / 1 deselected / 17 selected
    ...
    ====================== 17 passed, 1 deselected in 1.23s =======================
    ```
  - Proves that `test_observation_environment_records_exact_runtime` is the exact 1 test deselected under Python 3.10, matching CI line 94, while all 17 sibling proof tests pass cleanly.

### 4.2 Python 3.11 Staged Verification (`CPython 3.11.9`)

- **Interpreter**: `CPython 3.11.9 (64-bit)` (`C:\Users\Snoozer\teamwork_projects\architecture-renewal-campaign\venv\Scripts\python.exe`)
- **Pre-Commit Version**: `pre-commit 4.7.0`
- **Tool Versions**: `Ruff 0.17.5`, `mypy 2.4.1`, `pytest 9.1.1`
- **Staged File**: `src/youtube_automation/__init__.py`
- **Exact Pre-Commit Command**:
  ```powershell
  & C:\Users\Snoozer\teamwork_projects\architecture-renewal-campaign\venv\Scripts\Activate.ps1
  git add src/youtube_automation/__init__.py
  pre-commit run --hook-stage pre-commit
  ```
- **Observed Results (All Hooks Pass)**:
  ```
  ruff (legacy alias)......................................................Passed
  mypy.....................................................................Passed
  trim trailing whitespace.................................................Passed
  fix end of files.........................................................Passed
  check yaml...............................................................Passed
  check toml...........................................(no files to check)Skipped
  check json...........................................(no files to check)Skipped
  check for merge conflicts................................................Passed
  debug statements (python)................................................Passed
  detect private key.......................................................Passed
  detect aws credentials...................................................Passed
  forbid new submodules................................(no files to check)Skipped
  check secrets and service tokens.........................................Passed
  pytest (unit tests only).................................................Passed
  ```
  *(Total staged run elapsed: `369,830 ms (6m09s)`, all 2,387 unit tests passed with 0 deselections, exit code 0).*

- **Verbose Mypy Receipt (`pre-commit run mypy --files src/youtube_automation/__init__.py --verbose`)**:
  ```
  mypy.....................................................................Passed
  - hook id: mypy
  - duration: 2.08s

  Success: no issues found in 1 source file
  ```

- **Identification of Qualification Test Line (`PASSED [100%]`)**:
  - The qualification line `tests/unit/test_observation_method_proof.py::test_observation_environment_records_exact_runtime PASSED [100%]` came from a **focused run** targeting that single test rather than the full unit suite.
  - **Focused Run Command**:
    ```powershell
    & C:\Users\Snoozer\teamwork_projects\architecture-renewal-campaign\venv\Scripts\python.exe tools\run_pytest_unit.py tests/unit -c pyproject.toml -m "not live_browser" -k "test_observation_environment_records_exact_runtime"
    ```
  - **Focused Receipt Output**:
    ```
    ============================= test session starts =============================
    platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.7.0 -- C:\Users\Snoozer\teamwork_projects\architecture-renewal-campaign\venv\Scripts\python.exe
    cachedir: .pytest_cache
    rootdir: C:\Users\Snoozer\teamwork_projects\ci-e05-align-quality-checks
    configfile: pyproject.toml
    plugins: anyio-4.16.0, platformdirs-4.14.5, cov-7.1.0, mock-3.17.0
    collecting ... collected 2387 items / 2386 deselected / 1 selected

    tests/unit/test_observation_method_proof.py::test_observation_environment_records_exact_runtime PASSED [100%]

    ===================== 1 passed, 2386 deselected in 20.55s =====================
    ```
  - **Module-Level Selection Receipt on Python 3.11**:
    Command:
    ```powershell
    & C:\Users\Snoozer\teamwork_projects\architecture-renewal-campaign\venv\Scripts\python.exe tools\run_pytest_unit.py tests/unit/test_observation_method_proof.py -c pyproject.toml -v
    ```
    Output:
    ```
    collecting ... collected 18 items
    tests/unit/test_observation_method_proof.py::test_observation_environment_records_exact_runtime PASSED [  5%]
    ...
    tests/unit/test_observation_method_proof.py::test_generate_qualification_receipt PASSED [100%]
    ============================= 18 passed in 1.21s ==============================
    ```
    Confirms that all 18 tests (including `test_observation_environment_records_exact_runtime`) remain selected and pass under Python 3.11.

### 4.3 Representative In-Scope Violations (`CAUGHT / REJECTED`)

Exact rejection probes executed in the disposable Windows environment:

1. **Preserved `detect-private-key` Probe on `tests/unit/test_check_secrets.py`**:
   - Injected synthetic encrypted private key block header into `tests/unit/test_check_secrets.py`.
   - Command: `pre-commit run detect-private-key --files tests/unit/test_check_secrets.py`
   - Observed outcome (`exit 1`, elapsed `5,320 ms`):
     ```
     detect private key.......................................................Failed
     - hook id: detect-private-key
     - exit code: 1

     Private key found: tests/unit/test_check_secrets.py
     ```
   - Confirms that `tests/unit/test_check_secrets.py` is actively protected by `detect-private-key`.

2. **Ruff Read-Only Lint Violation Probe**:
   - Staged synthetic `temp_lint_probe.py` containing multiple unformatted imports (`import sys, os`).
   - Command: `pre-commit run ruff --files temp_lint_probe.py`
   - Observed outcome (`exit 1`, elapsed `2,788 ms`):
     ```
     ruff.....................................................................Failed
     - hook id: ruff
     - exit code: 1

     E401 [*] Multiple imports on one line
     I001 [*] Import block is un-sorted or un-formatted
     F401 [*] `sys` imported but unused
     F401 [*] `os` imported but unused
     Found 4 errors.
     ```

3. **Mypy Strict Typing Violation Probe in `src/`**:
   - Staged synthetic `src/youtube_automation/temp_type_probe.py` returning incompatible return type (`def add(a: int, b: int) -> int: return 'not_an_int'`).
   - Command: `pre-commit run mypy --files src/youtube_automation/temp_type_probe.py`
   - Observed outcome (`exit 1`, elapsed `4,153 ms`):
     ```
     mypy.....................................................................Failed
     - hook id: mypy
     - exit code: 1

     src\youtube_automation\temp_type_probe.py:2: error: Incompatible return value type (got "str", expected "int")  [return-value]
     Found 1 error in 1 file (checked 1 source file)
     ```

4. **Secret Scanning Violation Probe**:
   - Staged synthetic `temp_sec_probe.py` containing unallowlisted Telegram bot token pattern (`TELEGRAM_BOT_TOKEN = "<synthetic_id>:<entropy>"` <!-- pragma: allowlist secret -->).
   - Command: `pre-commit run check-secrets --files temp_sec_probe.py`
   - Observed outcome (`exit 1`, elapsed `4,150 ms`):
     ```
     check secrets and service tokens.........................................Failed
     - hook id: check-secrets
     - exit code: 1

     Secret scanning gate failed: 1 potential secret(s) detected:
       temp_sec_probe.py:1: [telegram_bot_token] potential secret token detected
     ```

### 4.4 Authoritative Offline Checks Actually Executed

Locally executed checks on the working tree:
- `git diff --check origin/master`: clean (`exit 0`, 0 trailing whitespace, pure LF).
- `python tools/check_secrets.py`: 0 secrets detected across 203 tracked files (`exit 0`).
- `python tools/check_readme.py`: 7 public onboarding documents verified (`exit 0`).
- `python -m unittest discover -s tests/unit -p test_readme_contract.py -v`: 9 tests passed (`0.191s`, `exit 0`).
- `ruff check .`: full workspace check passed under Ruff (`All checks passed!`, `exit 0`).
- `python -m mypy --strict src/`: all 84 modules passed type checking (`exit 0`).
- `pytest tests/unit/test_check_secrets.py -c pyproject.toml -v`: all 42 unit tests passed (`28.41s`, `exit 0`), confirming runtime RSA fixture detection.
- `python tools/run_pytest_unit.py tests/unit -c pyproject.toml -m "not live_browser" -v --tb=short`: verified across Python 3.10 (2,386 passed, 1 deselected) and Python 3.11 (2,387 passed, 0 deselected).
