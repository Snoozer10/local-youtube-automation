> Current engineering disposition: strict typing, F1 dispositions and local gates pass; formal-review package prepared. See [typing closeout](STRICT_TYPING_REVIEW_20261022.md), [F1 dispositions](F1_REVIEW_DISPOSITIONS_20261022.md) and [master](../../tasks/BRANCH_COMPLETION_MASTER.md). The earlier body below is preserved byte-for-byte as historical evidence; its gate/status counts are superseded.

> Current release disposition: see [release cleanup](RELEASE_CLEANUP_20261021.md), [master](../../tasks/BRANCH_COMPLETION_MASTER.md) and [HANDOFF](HANDOFF.md). The complete earlier report below is preserved byte-for-byte as historical evidence; its gate counts are superseded.

# Source repairs and live-test isolation - 21 October 2026

The four audited findings are repaired and independently reviewed. The full default suite passes. The branch remains unready for release while broader review, lint, full-source typing and production acceptance remain open.

## Repairs

- **SOURCE-01:** exact visible 1x verification now propagates failure in preflight and before either send reservation.
- **SOURCE-02:** body lookup/click/fill/send/capture errors propagate before Done and completed receipt publication. Presence enumeration includes hidden ARIA controls; only confirmed absence permits body omission.
- **SOURCE-03:** six actual live adversarial cases are marked; three empirical live cases moved to `tests/integration/test_empirical_m1_live.py`. Default collection skips all nine before fixtures. Offline cases retain fake transport/process facts; termination boundaries use failure sentinels. A real isolated pytest regression proves fixture/body suppression and opt-in using only a synthetic local case.
- **SOURCE-04:** unrecognized image candidates reject before selection. Capture selects only a single validated identity group; normalized same-identity aliases remain compatible.

## Verification and evidence

Evidence root: `.runtime/codex_source_repairs_20261021/` at HEAD `41d02eb` with a dirty working tree. GATE_TREE_BEFORE.json and GATE_TREE_AFTER.json are identical. Exact source hashes and independent reviewer disposition are in INDEPENDENT_REVIEW.json; earlier NO-GO and the resolved hidden-control issue are retained there.

| Gate | Current result |
|---|---|
| `python -m pytest -q --tb=short -x tests` | 1,933 passed / 9 live skipped in 164.87s; no module exclusions |
| Character focused file | 50 passed; character_followup/RESULTS.json |
| Initial independent combined verification | 57 passed / 9 skipped; before hidden-control follow-up |
| Final synthetic collection tests | 2 passed; commands/gate_sentinel_pytest |
| Scoped repair and CI unit Ruff | Pass |
| Workspace Ruff | FAIL: 90 findings in 31 tools; all flagged files unchanged since task baseline |
| Production mypy | Pass, 24 source files |
| `mypy --strict src/` | Exit 2: scene_graph discovered under two module names; further checks prevented |
| Semantic replay | 14 passed |
| Exercise structure/links | Pass, 35 links |
| Isolated PEP 517 wheel/sdist | Pass; warnings preserved in logs |
| Package byte verification | Wheel 232 members / 148 source copies; sdist 161 / 74; all exact, no forbidden runtime members |
| Canonical artifact guard | All 48 pins unchanged |

GATES.json stores exact commands, outcomes and frozen input identity. PACKAGE_VERIFICATION.json, RUFF_BASELINE_COMPARISON.json and ARTIFACT_GUARD_AFTER.json retain checks. PREIMAGES.json plus additional archival receipts preserve exact preimages; failed results remain. The original-source missing-1x reproducer intentionally fails against the original source, demonstrating the prior bug.

Independent repair review returned GO with no blocking findings at the recorded hashes. Direct new regressions for ambiguous/disabled body controls and multiple same-identity capture aliases remain absent; source review found the logic consistent. Passing tests do not establish zero defects or live readiness.

## Current records and remaining work

HANDOFF, continuity, master, adaptive task status and historical checklist pointers now use this disposition. The old audit body and Antigravity continuity snapshot are preserved unchanged. tests/AGENTS.md owns the new live-test policy; root AGENTS.md, GEMINI.md and production contracts are intentionally unchanged because existing fail-closed rules already own this restored behavior. No child ownership/index changes are needed.

QMD collection coverage remains session-state, tasks and local-contracts. QMD_CLOSEOUT.json records incremental lexical refresh and exact current excerpt readback. Affected embeddings remain incomplete after prior bounded failures; no new embed attempt or semantic retrieval ran.

Whole-branch F1 and release review remain open. Resolve the 90 operational-helper lint findings and broad mypy module discovery before claiming complete software gates; [mypy module-mapping guidance](https://mypy.readthedocs.io/en/stable/running_mypy.html#mapping-file-paths-to-modules) is recorded in MYPY_RESEARCH.md. Reconcile human approval provenance, cumulative pilot spending and full visual/editorial/restart acceptance without overwriting historical approvals or regenerating verified assets by default.

No actual live test, provider/browser action, commit, push or merge ran. `--run-live-browser` enables execution; it does not grant authorization. The synthetic opt-in test exercised only a local fixture/body sentinel.
