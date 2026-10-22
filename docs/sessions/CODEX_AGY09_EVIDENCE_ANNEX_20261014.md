# Additive AGY09 evidence annex — 2026-10-14

Original artifacts remain byte-identical. Corrections qualify evidence; they do not retroactively create execution proof or approve production.

| ID | Classification | Source within AGY09_attempt01 | Correction |
|---|---|---|---|
| AGY09-A01 | CONTRADICTED | RETURN.md:51 | Actual3352bytes; manifest correct; prior additive correction retained. |
| AGY09-A02 | CONTRADICTED | frozen_helpers/verify_candidate.py:370-375 | Only folder existence checked; all_outputs_isolated hardcoded true. Historical containment unverified. |
| AGY09-A03 | UNVERIFIABLE | RETURN.md:51-58; SEAL.json:3 | Exact argv/cwd/environment/invoked helper/exit/capture-close receipts absent; current seal bindings match. |
| AGY09-A04 | UNVERIFIABLE | RETURN.md:32,118 | Static helpers support intended offline scope. Complete tool trace/pre-session snapshot absent; do not infer either compliance or violation. |
| AGY09-A05 | VERIFIED | helpers/assemble_candidate.py:94-102; word_timing_provenance.json | Reconstructed after chunk69 overlap clamp240.740→240.800s. Keep original bounds and60ms transformation explicit; no acoustic correction. |
| AGY09-A06 | VERIFIED | TASK_STATUS.json; run_candidate/validation.json | 30 independent structural checks pass. D1/C7/audio fidelity/canonical D2 acceptance remain open. |

Independent receipts: .runtime/codex_agy09_detailed_review_20261014T190516Z/INDEPENDENT_VERIFICATION.json and INTERPOLATION_CLAMP_RECONCILIATION.json. Prior stdout-size mapping remains in .runtime/codex_agy09_review_20261014T185304Z/ADDITIVE_CORRECTIONS.json.
