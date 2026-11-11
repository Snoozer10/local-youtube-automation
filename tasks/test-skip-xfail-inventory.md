# Test Skip, XFail & Deselection Inventory

**Task E08**: Maintain a skip/xfail inventory and resolve accidental coverage holes (`tasks/REMAINING_WORK.md:90`)  
**Campaign**: [Issue #78](https://github.com/Snoozer10/local-youtube-automation/issues/78)  
**Task Branch**: `test/e08-skip-xfail-inventory`  
**Base Commit**: `2bbebb5b6c4b94e8b8bfbbcfd33991a1f2a04f66` (`origin/master` after PRs #117 and #118)  
**Claim & Amendment**: [Initial claim (`6804442193`)](https://github.com/Snoozer10/local-youtube-automation/issues/78#issuecomment-6804442193) · [Reservation amendment (`6805250627`)](https://github.com/Snoozer10/local-youtube-automation/issues/78#issuecomment-6805250627)  
**Date**: 2026-11-11

---

## 1. Executive Summary

This inventory audits all test skips, expected failures (`xfail`), unexpected passes (`XPASS`), and CI/CLI deselections across the repository on verified base `2bbebb5b6c4b94e8b8bfbbcfd33991a1f2a04f66` and compares exact-revision GitHub Actions CI receipts against isolated offline Windows Python `3.11.9` and `3.10.20` collection and execution.

### Key Findings

1. **Zero `xfail` and zero `XPASS`**: AST and text inspection of all `146` `test_*.py` files (`2,422` collected test items), `tests/conftest.py`, `pyproject.toml`, and `pytest.ini` found zero `@pytest.mark.xfail`, `pytest.xfail(...)`, `@unittest.expectedFailure`, or `marks=pytest.mark.xfail` declarations. Both hosted CI lanes (`test` and `test-py310`), `onboarding`, and all local offline runs recorded **`0` xfailed** and **`0` XPASS**.
2. **Baseline CI & clean-checkout skips were a confirmed accidental coverage hole (`2` tests)**: On `2bbebb5b6c4b94e8b8bfbbcfd33991a1f2a04f66`, both `test` (`2,411 passed, 2 skipped, 9 deselected`) and `test-py310` (`2,410 passed, 2 skipped, 10 deselected`) unconditionally skipped two tests in `tests/unit/test_timeline_quantization_invariants.py` (`test_canonical_timeline_ingestion_bypasses_resnapping` and `test_cumulative_integer_quantization_zero_drift`) because they required an untracked, gitignored file at `youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/timeline.json`. Because `tests/unit/test_timeline.py` only covers `.txt` shims (`image_timestamps.txt` and `timestamped_transcript.txt`), skipping those two tests left canonical `timeline.json` ingestion via `parse_image_timeline()` -> `prepare_synchronized_timeline()` and `40,030`-frame / `293`-span cumulative quantization drift checks completely unexercised in CI and clean checkouts.
3. **Narrow E08 repair (`tests/unit/test_timeline_quantization_invariants.py`)**: After amending Issue #78 reservations ([`6805250627`](https://github.com/Snoozer10/local-youtube-automation/issues/78#issuecomment-6805250627)), replaced reliance on the missing untracked directory with a deterministic synthetic `tmp_path` `timeline.json` fixture (`293` spans totaling `40,030` frames at `30` fps / `1334.34` seconds, including two `3`-frame `0.10s` spans under the `0.15s` legacy grouping threshold to prove bypass of comedic grouping and acoustic re-snapping). Post-fix offline runs achieved **`0` accidental skips** across both Python `3.11.9` (`2,413 passed, 9 skipped` under full default `tests/` — only `live_browser` skipped) and isolated Python `3.10.20` (`2,412 passed, 0 skipped, 10 deselected`).
4. **Intentional gates preserved**:
   - All `9` `@pytest.mark.live_browser` integration tests remain deselected in CI (`-m "not live_browser"`) and skipped pre-fixture locally (`tests/conftest.py:347-356`) unless `--run-live-browser` is passed under an approved E09 live run grant.
   - `tests/unit/test_observation_method_proof.py::test_observation_environment_records_exact_runtime` remains deselected solely on `test-py310` (`-k "not test_observation_environment_records_exact_runtime"`) to preserve Python `>= 3.11` SQLite qualification evidence in `test` while running the other `17` functional tests in that module on Python `3.10`.
   - Conditional native FFmpeg (`10` test-level checks + `tests/conftest.py:199` `dummy_audio_file` fixture) and Windows OS privilege/junction checks (`2` tests) remain intact and pass in CI and locally.
5. **Deferred boundaries respected**: CI/pre-commit/`pytest.ini` alignment stays with **E05**, broader recovery-test gaps stay with **E11**, and **no live provider, browser, CDP, Audacity, or publication allowance** was exercised.

---

## 2. Lane & Environment Totals Reconciliation

Collection with `-c pyproject.toml` and bare `pytest.ini` both discover `146` `test_*.py` files under `tests/` (`142` under `tests/unit/`, `4` under `tests/integration/`), of which `143` files yield **`2,422` test items** (`2,387` unit + `35` integration) and `3` files are intentional `92`-byte zero-test stubs routing saved-artifact audits to `tools/audit_adaptive_artifact_receipt.py`. Outside `tests/`, `tools/test_*.py` (`14` scripts) and `exercises/*/solution/test_exercise.py` (`7` drill scripts) sit outside `testpaths = ["tests"]`.

### 2.1 Inventory Totals by Lane and Outcome

| Execution Lane / Selection | Config & Command Selection | Interpreter | Collected | Selected | Deselected | Passed | Skipped | XFail | XPASS | Failed / Err |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **CI `test` (base `2bbebb5`, Run `43078236906` / Job `130723679673`)** | `-c pyproject.toml tests/unit tests/integration -m "not live_browser"` | CPython `3.11.9` | 2,422 | 2,413 | 9 | 2,411 | 2 | 0 | 0 | 0 |
| **CI `test-py310` (base `2bbebb5`, Run `43078236906` / Job `130723680020`)** | `-c pyproject.toml tests/unit tests/integration -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"` | CPython `3.10.11` | 2,422 | 2,412 | 10 | 2,410 | 2 | 0 | 0 | 0 |
| **CI `onboarding` (base `2bbebb5`, Run `43078236924` / Job `130723679900`)** | `python -m unittest discover -s tests/unit -p test_readme_contract.py -v` | CPython `3.11.18` (Linux) | 9 | 9 | 0 | 9 | 0 | 0 | 0 | 0 |
| **Local Offline Baseline (Py 3.11 CI selection, pre-fix)** | `-c pyproject.toml tests/unit tests/integration -m "not live_browser"` | CPython `3.11.9` | 2,422 | 2,413 | 9 | 2,411 | 2 | 0 | 0 | 0 |
| **Local Offline Baseline (Py 3.10 CI selection, pre-fix)** | `-c pyproject.toml tests/unit tests/integration -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"` | CPython `3.10.20` | 2,422 | 2,412 | 10 | 2,410 | 2 | 0 | 0 | 0 |
| **Local Post-Fix Full Default `tests/` (Py 3.11)** | `-c pyproject.toml tests/ -v -ra` | CPython `3.11.9` | 2,422 | 2,422 | 0 | 2,413 | 9 | 0 | 0 | 0 |
| **Local Post-Fix CI Selection (Py 3.10, isolated venv)** | `-c pyproject.toml tests/unit tests/integration -m "not live_browser" -k "not test_observation_environment_records_exact_runtime" -v -ra` | CPython `3.10.20` | 2,422 | 2,412 | 10 | 2,412 | 0 | 0 | 0 | 0 |

### 2.2 Log-Derived Node-ID Parity Notes (CI vs Local)

Two formatting differences observed when reconciling raw CI logs against local `--collect-only -q` are deterministic log artifacts rather than test discrepancies:
1. **`pytest-playwright` parameterization suffix**: CI (`requirements-dev.txt` installs `pytest-playwright==0.10.0`) and our isolated Python `3.10.20` venv parameterize `tests/unit/test_tts_workspace_redirect.py::test_non_speech_workspace_fails_detection` with `[chromium-page0]`, `[chromium-page1]`, `[chromium-page2]`, whereas the hub Python `3.11.9` `venv` (which lacks `pytest-playwright`) emits `[page0]`, `[page1]`, `[page2]`. Both execute the same 3 test cases.
2. **GitHub Actions secret masking**: Hosted CI masks 3 credential-shaped parametrize node IDs with `***` in stdout (`test_redacts_credential_assignments_from_jsonl_and_last_cli[***-fake password phrase]` in `test_failure_record.py`, plus two `[***aistudio.google.com/...]` cases in `test_tts_workspace_redirect.py`). Exact 1:1 set equality holds for all `2,413` (`test`) and `2,412` (`test-py310`) selected items.

---

## 3. Master Skip, XFail & Deselection Inventory

### 3.1 Group A — Live Browser Integration Gate (`9` Nodes, Intentional Gate)

- **Mechanism**: `@pytest.mark.live_browser` decorator; CI filters `-m "not live_browser"`; local collection without `--run-live-browser` attaches `pytest.mark.skip(reason="live browser/CDP/socket test requires --run-live-browser")` in `tests/conftest.py:347-356` before fixture setup or test body runs.
- **Status**: **Kept intact**. Never executed offline or in CI.
- **Owning Area**: Browser CDP & process ownership (`tests/integration/`, `src/youtube_automation/browser/`, `src/youtube_automation/core/utils.py`; `tests/AGENTS.md:13`).
- **Offline Substitutes**:
  - `tests/unit/test_live_browser_opt_in.py` (`2` tests: verifies pre-fixture skip without opt-in, opt-in execution on synthetic test, and AST marker coverage across `test_empirical_m1_live.py` and `test_m1_adversarial_challenge.py`).
  - `tests/unit/test_browser_probe_fail_closed.py` (`5` tests), `tests/unit/test_browser_process_ownership.py` (`22` tests), `tests/unit/test_ui_guard.py` (`28` tests), and the `2` offline tests in `tests/integration/test_m1_adversarial_challenge.py` (`test_05_foreign_targets_adversarial_oracle`, `test_08_tab_hygiene_edge_cases`).
- **Offline Gap**: Does not prove live loopback HTTP/WebSocket CDP stability on `127.0.0.1:9222`, live `C:\ChromeDebugProfile` registry PID binding, or live tab-churn timing against real Chromium.
- **Explicit Live Acceptance Path**: Requires a bounded live run card and explicit owner allowance under **E09** (`tasks/REMAINING_WORK.md:91`, `docs/sessions/ANTIGRAVITY_BACKLOG_LIVE_RUNS.md`) using an owned browser profile (`C:\ChromeDebugProfile`, port `9222`, `.runtime/owned_browsers.json`), executed explicitly via:
  ```powershell
  python -m pytest tests/integration -c pyproject.toml --run-live-browser -m live_browser -v
  ```

| Exact Node ID | Location | CI `test` / `test-py310` | Local Default `tests/` | Trigger / Reason |
|---|---|---|---|---|
| `tests/integration/test_empirical_m1_live.py::test_empirical_live_port_9222_socket_and_rapid_polling` | `line 18` | Deselected (`-m "not live_browser"`) | Skipped pre-fixture | Requires live Chrome CDP on `127.0.0.1:9222` (`--run-live-browser`) |
| `tests/integration/test_empirical_m1_live.py::test_empirical_live_process_ownership_and_exclusive_binding` | `line 65` | Deselected (`-m "not live_browser"`) | Skipped pre-fixture | Requires live `.runtime/owned_browsers.json` + running `chrome.exe` (`--run-live-browser`) |
| `tests/integration/test_empirical_m1_live.py::test_empirical_detailed_diagnostics` | `line 117` | Deselected (`-m "not live_browser"`) | Skipped pre-fixture | Requires live Chrome socket/HTTP/PID diagnostics (`--run-live-browser`) |
| `tests/integration/test_m1_adversarial_challenge.py::test_01_live_cdp_targets_and_foreign_targets` | `line 24` | Deselected (`-m "not live_browser"`) | Skipped pre-fixture | Requires live `/json/list` & `.runtime/owned_browsers.json` (`--run-live-browser`) |
| `tests/integration/test_m1_adversarial_challenge.py::test_02_tab_hygiene_stress` | `line 56` | Deselected (`-m "not live_browser"`) | Skipped pre-fixture | Connects Playwright CDP (`port 9222`) & spawns live tabs (`--run-live-browser`) |
| `tests/integration/test_m1_adversarial_challenge.py::test_03_concurrent_http_loopback_stress` | `line 109` | Deselected (`-m "not live_browser"`) | Skipped pre-fixture | Fires 50 concurrent loopback HTTP CDP requests (`--run-live-browser`) |
| `tests/integration/test_m1_adversarial_challenge.py::test_04_websocket_loopback_concurrent_queries` | `line 142` | Deselected (`-m "not live_browser"`) | Skipped pre-fixture | Connects live CDP WebSocket & runs 25 concurrent queries (`--run-live-browser`) |
| `tests/integration/test_m1_adversarial_challenge.py::test_06_multi_connection_websocket_stress` | `line 230` | Deselected (`-m "not live_browser"`) | Skipped pre-fixture | Opens 10 concurrent WebSocket CDP connections (`--run-live-browser`) |
| `tests/integration/test_m1_adversarial_challenge.py::test_07_tab_churn_during_target_probing` | `line 260` | Deselected (`-m "not live_browser"`) | Skipped pre-fixture | Churns live Playwright tabs during CDP target probing (`--run-live-browser`) |

---

### 3.2 Group B — Python 3.10 Compatibility Lane SQLite Qualification Deselection (`1` Node, Intentional Gate)

| Exact Node ID | Location | CI `test` (Py 3.11) | CI `test-py310` (Py 3.10) | Local Py 3.11 / Py 3.10 | Owner / Area |
|---|---|---|---|---|---|
| `tests/unit/test_observation_method_proof.py::test_observation_environment_records_exact_runtime` | `line 100` | Executed & **PASSED** | **Deselected** (`-k "not test_observation_environment_records_exact_runtime"`) | Executed & **PASSED** on Py 3.11; deselected on Py 3.10 | Production ledger qualification (`Issue #55`, `E03` PR #115) |

- **Exact Condition & Reason**: Asserts `sys.version_info >= (3, 11)`, `sqlite3.sqlite_version >= "3.40"`, and `platform.system() == "Windows"` to pin the exact authoritative Windows Python `>= 3.11` SQLite read-only observation qualification runtime (`tasks/python310-compatibility-report.md:160-170`).
- **Offline Substitute in `test-py310`**: All other `17` functional SQLite read-only observation invariant tests in `tests/unit/test_observation_method_proof.py` run and pass on Windows Python `3.10.11` (CI) and `3.10.20` (local).
- **Acceptance Path**: Executed continuously in the authoritative Windows Python `3.11` CI job (`test`); no live allowance needed (`E10` governs runtime requalification if SQLite/OS environment changes).

---

### 3.3 Group C — Historical Timeline Fixture Skips (`2` Nodes, Confirmed Accidental Coverage Hole -> Fixed)

| Exact Node ID | Baseline CI (`test` & `test-py310`) | Baseline Reason | Owning Area | Post-Fix Offline Outcome (Py 3.11 & Py 3.10) |
|---|---|---|---|---|
| `tests/unit/test_timeline_quantization_invariants.py::test_canonical_timeline_ingestion_bypasses_resnapping` | **SKIPPED** (`2` of `2`) | `Production timeline not found at youtube_runs\Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!\timeline.json` (baseline `2bbebb5` `line 57`) | Timeline & video compilation (`compiler.py:829,884`, `timeline/engine.py:478`) | **PASSED** (`tmp_path` synthetic canonical fixture) |
| `tests/unit/test_timeline_quantization_invariants.py::test_cumulative_integer_quantization_zero_drift` | **SKIPPED** (`2` of `2`) | `Production timeline not found at youtube_runs\Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!\timeline.json` (baseline `2bbebb5` `line 87`) | Timeline & video compilation (`compiler.py:829,884`, `timeline/engine.py:478`) | **PASSED** (`tmp_path` synthetic canonical fixture) |

- **Why It Was an Accidental Coverage Hole**:
  1. Both tests relied on an untracked, gitignored production run directory (`youtube_runs/Terrence Howard...`) present only on the original author's workstation, causing permanent skips on every CI runner and clean checkout (`offline-vs-ci-test-selection-report.md:199,376-377`).
  2. Unlike `tests/unit/test_timeline.py` (which tests only `.txt` shims: `image_timestamps.txt` and `timestamped_transcript.txt`) and `tests/unit/test_timeline_engine.py` (`load_timeline_or_shim` length/`sec`/`name` only), these two tests are the sole unit tests exercising `parse_image_timeline(run_folder)` reading a `293`-span canonical `timeline.json` and feeding those blocks into `prepare_synchronized_timeline(blocks, audio_duration=1334.34, fps=30)` across `40,030` frames without re-snapping or comedic grouping.
- **Narrow Synthetic Fix Applied (`tests/unit/test_timeline_quantization_invariants.py`)**:
  - Added `_write_synthetic_canonical_timeline(run_dir: Path) -> Path` writing a schema-valid `timeline.json` into pytest `tmp_path` with `293` contiguous integer-frame spans summing to `40,030` frames (`fps = 30`, `audio_duration = 1334.34`, SHA-256 checksums, plus two `3`-frame `0.10s < 0.15s` leading spans that legacy comedic grouping would merge if canonical bypass failed).
  - Removed the `youtube_runs/...` `pytest.skip(...)` branches; preserved the existing pure-LF (`\n`) formatting and the other `4` synthetic tests in the file untouched.

---

### 3.4 Group D — Conditional Native-Tool Skips (`FFmpeg` / `FFprobe`, Intentional Binary Guards)

All tests below **executed and PASSED** in CI (`test` Py `3.11.9` and `test-py310` Py `3.10.11`, where Chocolatey installs `ffmpeg`) and on local Windows (WinGet `ffmpeg` / `ffprobe` on `PATH`), because full supported Windows environments include FFmpeg (`tasks/REMAINING_WORK.md:89`, `E07`). No accidental skip occurred in any observed run.

| Test / Fixture Node ID | Line | Trigger Condition | Outcome in CI & Local | Owner / Area | Offline Substitute / Note |
|---|---|---|---|---|---|
| `tests/unit/test_production_source_narration.py::test_source_narration_import_is_exact_resumable_and_tamper_evident` | `20` | `@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"))` | **PASSED** (all lanes) | Production narration (`source_narration.py:196,210`) | Calls real `ffprobe`/`ffmpeg` trim on a synthetic `tmp_path` WAV; `test_source_narration_requires_matching_caption_window` runs FFmpeg-free |
| `tests/unit/test_production_source_narration.py::test_source_narration_recovers_after_activation_crash_without_ffmpeg` | `133` | `@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"))` | **PASSED** (all lanes) | Production narration recovery (`source_narration.py:196,210`) | Initial import setup invokes `ffprobe`/`ffmpeg`, then simulated crash recovery proves `subprocess.run` is never called during recovery |
| `tests/unit/test_production_render.py::test_real_aspect_crop_keeps_off_center_subject` | `595` | `if not shutil.which("ffmpeg"): pytest.skip("Real FFmpeg unavailable")` | **PASSED** (all lanes) | Production render (`render.py`, `filter_graph.py`) | Pure filtergraph unit assertions precede this check in `test_production_render.py`; test checks real decoded RGB crop pixels |
| `tests/unit/test_production_render.py::test_real_schulte_render_keeps_grid_lines_and_numbers_visible` | `786` | `if not shutil.which("ffmpeg"): pytest.skip("Real FFmpeg unavailable")` | **PASSED** (all lanes) | Production render / ASS pixel proof | Validates real `libass` grid/text pixel placement via `ffmpeg` |
| `tests/unit/test_production_render.py::test_real_ffmpeg_preview_and_approval_gate` | `831` | `if not shutil.which("ffmpeg") or not shutil.which("ffprobe"): pytest.skip("Real FFmpeg tools unavailable")` | **PASSED** (all lanes) | Production render & review lineage | Encodes synthetic preview MP4 + probes real container/color range |
| `tests/unit/test_production_render.py::test_real_hold_produces_identical_decoded_frames` | `1012` | `if not shutil.which("ffmpeg"): pytest.skip("Real FFmpeg unavailable")` | **PASSED** (all lanes) | Production render static hold (`framemd5`) | Pure filter string checks exist elsewhere; checks bit-exact decoded frames |
| `tests/unit/test_production_render.py::test_timer_ass_time_boundary_quantization_and_ffmpeg_pixel_render` | `1086` | `if not shutil.which("ffmpeg"): pytest.skip("FFmpeg is required for timer pixel-boundary verification")` | **PASSED** (all lanes) | Production render timer ASS quantization | Lines `1058-1083` run pure-Python `_timer_ass_time`/`_ass_time` math unconditionally before FFmpeg pixel crop verification |
| `tests/unit/test_production_render.py::test_high_rate_overlay_recipe_keeps_global_timer_phase_and_restores_pts` | `1176` | `if not shutil.which("ffmpeg"): pytest.skip("FFmpeg required high-rate timer pixel verification")` | **PASSED** (all lanes) | Production render high-FPS `overlay_filter_recipe` | Verifies rendered timer crops at `>100` fps across cut boundaries |
| `tests/unit/test_production_render.py::test_high_rate_recipe_preserves_ass_layer_and_same_layer_order` | `1360` | `if not shutil.which("ffmpeg"): pytest.skip("FFmpeg is required for ASS layer-order verification")` | **PASSED** (all lanes) | Production render ASS layer ordering | Compares split-pass vs single-pass decoded PNG pixels |
| `tests/unit/test_production_render.py::test_high_rate_generic_ass_timing_remains_unscaled` | `1463` | `if not shutil.which("ffmpeg"): pytest.skip("FFmpeg required high-rate generic fade pixel verification")` | **PASSED** (all lanes) | Production render fade PTS scaling | Compares decoded fade PNG frames at `101`/`119`/`120` fps |
| `tests/conftest.py::dummy_audio_file` (`12` tests in `tests/integration/test_run_singlepass.py`) | `199` | `if r.returncode != 0: pytest.skip("ffmpeg unavailable for audio generation")` | **PASSED** (`12` of `12` in all lanes) | Shared integration fixture (`test_run_singlepass.py` lines `21-356`, `442`) | Generates synthetic 10s WAV via `ffmpeg` before mocked `FakePopen` compilation tests; note unguarded `subprocess.run` on line `197` (and in `test_images_dir` line `173`) would raise `FileNotFoundError` rather than `pytest.skip` if `ffmpeg` binary is missing (recorded for **E07** environment docs) |

*(Asymmetry note for completeness: `tests/unit/test_adaptive_render_color_range.py:74-75` uses `pytest.fail(...)` rather than `pytest.skip(...)` when `ffmpeg`/`ffprobe` are missing; keeping FFmpeg required/present matches E07 setup scope.)*

---

### 3.5 Group E — Conditional Windows Privilege / Junction Skips (`2` Nodes, Intentional OS Guards)

| Exact Node ID | Line | Trigger Condition | CI (`test` & `test-py310`) & Local | Owner / Area | Fallback Coverage Note |
|---|---|---|---|---|---|
| `tests/unit/test_production_render_proofs.py::test_proof_output_rejects_symlinked_destination` | `274` | `pytest.skip(f"symlink creation unavailable: {exc}")` on `OSError` (`WinError 1314`) | **PASSED** (Developer Mode enabled on CI & host) | Production render proofs containment (`render_proofs.py:43-55`) | Non-symlink path containment tests run unconditionally (`render_proofs.py` also validates `.resolve().is_relative_to(root)`); standard non-Developer-Mode Windows hosts without `SeCreateSymbolicLinkPrivilege` would skip this test cleanly |
| `tests/unit/test_check_secrets.py::SecretScanningGateTests::test_git_scan_rejects_tracked_path_through_junction_outside_repo` | `542` | `self.skipTest("Windows mklink junction creation not available")` if `cmd /c mklink /J` returns nonzero | **PASSED** (all lanes) | Tools security gate (`tools/check_secrets.py`) | Explicit-path and `..` traversal rejection cases run without junctions; NTFS junctions work unprivileged on Windows NTFS |

---

## 4. Collection Scope, Config & Non-Code Boundaries (E05 / E11 / E07 Handoffs)

No config, CI workflow, pre-commit hook, or recovery test was modified in E08 per task boundaries:
1. **`pytest.ini` vs `pyproject.toml` (deferred to E05)**: Both discover the exact same `2,422` tests under `tests/`. However, `pytest.ini` omits `live_browser` from its `markers =` list (avoiding `--strict-markers` failure only because `tests/conftest.py:341-344` calls `config.addinivalue_line`) and specifies `--import-mode=importlib`, which `pyproject.toml` omits. Alignment belongs to **E05**.
2. **Intentional zero-item stub files (`3` files in `tests/unit/`)**: `test_h10_dog_cues_pilot.py`, `test_professor_full_episode_timing.py`, and `test_soldier_samar_pilot.py` (`92` bytes each) contain module docstrings redirecting saved-artifact receipt audits to opt-in `tools/audit_adaptive_artifact_receipt.py` (`tests/AGENTS.md:26`), yielding `0` pytest items.
3. **Out-of-testpaths suites**: `tools/test_*.py` (`14` manual/live browser/CDP diagnostic scripts under `tools/AGENTS.md`) and `exercises/*/solution/test_exercise.py` (`7` hardware/workflow exercise scripts) live outside `tests/` and are never collected by pytest `testpaths = ["tests"]`.
4. **Broader recovery coverage**: Reserved separately for **E11** (`tasks/REMAINING_WORK.md:93`).

---

## 5. Verification Evidence & Receipts

### 5.1 Pre-Fix Exact-Revision Hosted CI Receipts (`2bbebb5b6c4b94e8b8bfbbcfd33991a1f2a04f66`)

- **CI `test` (Windows CPython `3.11.9`)**: [Run `43078236906` / Job `130723679673`](https://github.com/Snoozer10/local-youtube-automation/actions/runs/43078236906/job/130723679673) — `2411 passed, 2 skipped, 9 deselected in 292.50s (0:04:52)`, `0` xfailed, `0` XPASS; `ruff check .`, `mypy --strict src/`, `tools/check_secrets.py`, and `python -m build --no-isolation --sdist --wheel` passed.
- **CI `test-py310` (Windows CPython `3.10.11`)**: [Run `43078236906` / Job `130723680020`](https://github.com/Snoozer10/local-youtube-automation/actions/runs/43078236906/job/130723680020) — `tomli 2.5.0` verified with `importlib.util.find_spec('tomllib') is None`; `2410 passed, 2 skipped, 10 deselected in 244.49s (0:04:04)`, `0` xfailed, `0` XPASS; `tools/check_secrets.py` and `build` passed.
- **CI `onboarding` (Linux CPython `3.11.18`)**: [Run `43078236924` / Job `130723679900`](https://github.com/Snoozer10/local-youtube-automation/actions/runs/43078236924/job/130723679900) — `tools/check_readme.py` passed; `unittest discover -s tests/unit -p test_readme_contract.py -v` ran `9` tests (`OK` in `0.020s`).

### 5.2 Local Post-Fix Offline Verification Receipts

All post-fix checks ran in isolated worktree `C:\Users\Snoozer\teamwork_projects\test-e08-skip-xfail-inventory` with `PYTHONPATH` pinned to the worktree (`src;.;tests`) and zero network/live-provider/browser calls:
- **Focused Timeline Suites (`36` tests across `test_timeline_quantization_invariants.py`, `test_timeline.py`, `test_timeline_engine.py`)**:
  - CPython `3.11.9`: **`36 passed, 0 skipped in 2.97s`**.
  - CPython `3.10.20` (isolated venv): **`36 passed, 0 skipped in 19.54s`**.
- **Full Default `tests/` Collection Execution (`CPython 3.11.9`, `-c pyproject.toml -v -ra`)**:
  - **`2413 passed, 9 skipped in 385.06s (0:06:25)`**, **`0` xfailed, `0` XPASS, `0` failed**. Every skipped test (`9` of `9`) is an intentional `@pytest.mark.live_browser` test gated pre-fixture by `tests/conftest.py`.
- **CI Selection Under Isolated `CPython 3.10.20` (`-c pyproject.toml -v -ra -m "not live_browser" -k "not test_observation_environment_records_exact_runtime"`)**:
  - **`2412 passed, 10 deselected in 336.07s (0:05:36)`**, **`0` skipped, `0` xfailed, `0` XPASS, `0` failed**.
- **Static & Packaging Gates**:
  - Verified on committed head prior to PR submission (`ruff check .`, `python -m mypy --strict src/`, `python tools/check_secrets.py`, `python tools/check_readme.py`, `python -m unittest discover -s tests/unit -p test_readme_contract.py -v`, and `git diff --check`; CI executes both test lanes and onboarding on the pushed PR head).
- **Preimage & Private Receipt Location**:
  - `C:\Users\Snoozer\teamwork_projects\architecture-renewal-intake\e08_skip_xfail_20261111\` retains byte-exact preimage `test_timeline_quantization_invariants.py.preimage` (SHA-256 `5fe652d0017740524386cf2d73fe5b354d3eb75695324d473c7dc8834a26f816`), collection dumps, and raw CI/local execution logs.
