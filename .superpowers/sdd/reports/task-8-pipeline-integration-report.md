# Task 8 Report: Pipeline Integration (run_agency.py Phase 9)

## Summary
Updated `run_agency.py` Phase 9 to pass the run folder explicitly to `compile_video.py`
and harden error handling (timeout, captured output, detailed Telegram alerts).

## Changes (run_agency.py:197-224)
- **Explicit run folder**: `subprocess.run([sys.executable, "compile_video.py", folder], ...)` — no longer relies on `compile_video.py` guessing the latest run via mtime.
- **Timeout**: `timeout=3600` (1h) prevents indefinite hangs.
- **Captured output**: `capture_output=True, text=True, encoding='utf-8'` — prints stdout on success, prints stdout+stderr on failure.
- **Detailed errors**: `CalledProcessError` now prints `{e.stdout}\n{e.stderr}`; Telegram alert includes `e.stderr[:500]`.
- **Timeout handling**: new `TimeoutExpired` except → Telegram alert + `continue`.
- **Checkpoint resume preserved**: `compile_video.main(run_folder)` auto-resumes from `compile_checkpoint.json` if present; `state["video"]` guard in run_agency skips re-compile if already True.

## Validation
- `python -m py_compile run_agency.py` → exit 0
- Integration via `validate_legacy.py` (Task 7) confirmed `compile_video.py` accepts explicit `run_folder` arg and renders correctly.

## Files Touched
- `run_agency.py` — Phase 9 block (lines 197-224)

## Commit
`feat: pipeline integration — explicit run folder + timeout + detailed errors`