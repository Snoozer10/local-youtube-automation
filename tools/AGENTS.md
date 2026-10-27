# Tools contracts

## Purpose
- Maintain offline QA/release utilities and explicitly invoked manual diagnostics.

## Ownership
- This scope owns `tools/*.py`, including exercise lint, release-note extraction and artifact receipt auditing.
- Root contracts retain provider grants, browser/app ownership, leases and production acceptance.

## Local Contracts
- Imports are inert: operational app/browser/process actions and source writes run only through an explicit `main()` or CLI entrypoint.
- Manual diagnostic execution requires its concrete bounded scope. A CLI flag or successful import is not a live-action grant.
- Preserve legacy command-line behavior when moving operational bodies under entrypoint guards; keep dependencies available in the scope that uses them.
- Artifact auditors verify caller-selected receipts without activating production state.

## Work Guidance
- Separate maintained release checks from exploratory diagnostics. Do not run the diagnostics as a generic release test sweep.
- Source changes follow the root exact-byte archive and DOX controls.

## Verification
- Run workspace Ruff and offline AST parsing/compilation after tool changes.
- Review guarded bodies and module-global references when introducing entrypoint guards; do not import operational helpers to test inertness.
- `tools/lint_exercises.py` is the existing offline exercise-layout/link check.

## Retired Cohorts
- Ad-hoc browser CDP exploration and hardcoded run inspection scratch scripts (check_project_9320.py, check_h10_project.py, inspect_h10_prompts.py, 	est_banana_21.py, 	est_banana_pro.py, 	est_raw_cdp.py, 	est_cdp_quick.py) were retired in Issue #41 after proving 0 callers, 0 runtime/packaging references, and recording byte-exact preimages in evidence/receipts/RETIRED_COHORT_TOOLS_SCRATCH.json.

## Child DOX Index
- None.
