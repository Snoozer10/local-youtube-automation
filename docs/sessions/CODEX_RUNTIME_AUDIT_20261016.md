<!-- Durable report copy. Verified source: .runtime/codex_workflow_reconciliation_20261015T220836Z/runtime_inventory/PRIMARY_AUDIT_REPORT.md; SHA-256 ed7d0e4314a4760ef4fafa8d594f272f8242944a95d6849b7b963b2aeab1a0a5. -->

# Primary runtime audit

## Finding

The requested primary runtime package exists as a directory at `.runtime/codex_antigravity_return_review_20261015T0923Z`. This report covers an inventory of its entries and a bounded read of selected status, control, comparison, and seal receipts. It does not claim that all logs or media were opened.

## Inventory

The recursive inventory contains 10,015 entries: 4,986 regular files (98,298,102 bytes), 3,383 directories, and 1,646 symlinks. Symlinks were recorded without following their targets. SHA-256 was persisted for 400 regular files; 4,586 regular files are marked `unprocessed_budget` in `INVENTORY.json`. Two later Node hash batches timed out without persisting results, so the remaining hash allowance was treated as spent. The machine inventory preserves each relative path, type, size, hash (or null), and status.

Top-level subpackages (recursive counts; bytes count regular files only):

| Subpackage | Files | Directories below | Symlinks | Bytes |
|---|---:|---:|---:|---:|
| `03_evidence` | 6 | 2 | 0 | 75,114 |
| `build_source` | 838 | 176 | 0 | 19,378,885 |
| `candidate` | 675 | 159 | 0 | 16,211,898 |
| `candidate-preimages-AR10` | 2 | 0 | 0 | 32,375 |
| `candidate-preimages-AR10-relative-fix` | 2 | 0 | 0 | 32,815 |
| `canonical_closeout_preimages_20261015T103851Z` | 4 | 0 | 0 | 128,589 |
| `canonical_preimages_20261015` | 5 | 0 | 0 | 153,426 |
| `checkpoint_probe_20261015T183703Z` | 54 | 18 | 0 | 253,291 |
| `checkpoint_receipt_repair_20261015T203839Z` | 82 | 25 | 0 | 946,339 |
| `forensic_20261015T174850Z` | 33 | 1 | 0 | 219,842 |
| `gates` | 56 | 5 | 0 | 1,813,935 |
| `retry_checkpoint_20261015T123151Z` | 35 | 3 | 0 | 241,258 |
| `sealed_snapshot` | 37 | 0 | 0 | 213,304 |
| `short_temp_20261015T130502Z` | 36 | 4 | 0 | 242,389 |
| `tmp` | 3,077 | 2,974 | 1,646 | 58,094,316 |
| `__pycache__` | 1 | 0 | 0 | 12,131 |

`INVENTORY.json` contains the computed subpackage map and complete entry list. The 400 persisted file digests are inventory evidence only; their set does not establish that all package payloads match a seal.

## Status and outcomes

The root `FINAL_REVIEW_SEAL.json` records `SEALED_PROMOTION_HELD`, 108 manifest entries, `promotion_applied=false`, and an unmet full-unit gate with one checkpoint `WinError 5` failure whose cause was unverified. Its recorded seal time is 2026-10-15T10:42:19.912Z. This status predates the later checkpoint-receipt repair and is stale as a live execution status.

The later `checkpoint_receipt_repair_20261015T203839Z/FINAL_DIAGNOSTIC_VERIFICATION.json` records four controls passed, zero failed; one focused prefix run with 234 passed and 1,549 deselected out of 1,783 collected; exact worker PID/Job identity validation; and 645 candidate pins stable before and after. It records no matching exception, retries 0, and interprets the original WinError 5 as not reproduced with cause still `UNKNOWN`. The outcome accepts this bounded diagnostic only. It explicitly leaves the full-suite gate open and source promotion held.

The root `FINAL_VALIDATION.json` records 645 baseline files checked, zero code changes, four authorized documentation changes, promotion not applied, and branch not ready for final review. These are recorded receipt claims, not a fresh whole-tree comparison in this audit.

## Source, tests, candidate, and build differences

`CANDIDATE_PRECHECK_MANIFEST.json` records a source checkout and candidate copy with 645 pinned files. The package inventory separately finds 838 regular files under `build_source` and 675 under `candidate`; these counts include generated and package-local material and are not a direct equality test.

`RETURN_PIN_COMPARISON.json` has eight source/test/tool rows. Only two rows report both declared preimage and postimage matches; six rows report both mismatches: `src/youtube_automation/core/audacity_windows.py`, `src/youtube_automation/core/window_readiness.py`, `src/youtube_automation/production/cli.py`, `tests/unit/test_audacity_window_readiness.py`, `tests/unit/test_audacity_windows.py`, and `tools/audacity_help_once.py`. The package `REPORT.md` line 4 summarizes these as twelve incorrect pre/post declarations. This is a mismatch in the return table's declarations, not evidence that the six current files are wrong.

The stored artifact comparison receipts report 191/191 wheel members and 121/121 sdist members, with no member additions/removals; payload differences are limited to generated `RECORD` and top-level namespace metadata. `BUILD_DIFFERENCE_DISPOSITION.json` says code payloads match and attributes the namespace metadata difference to generated directory presence under broad setuptools discovery. `ARTIFACT_NAMESPACE_COMPARISON.json` records `youtube_runs` in the original build and `youtube_automation` in the candidate. This audit did not rerun the comparison helper or independently hash all source, test, or archive members.

## Seal and receipt claims

The seal records 108 entries and three root reference digests. The coordinator separately reports verification in `.runtime/codex_workflow_reconciliation_20261015T220836Z/SEAL_REFERENCE_VERIFICATION.json`: the root `FINAL_REVIEW_MANIFEST.json`, `sealed_snapshot/REPORT.md`, `sealed_snapshot/LEDGER.md`, and repaired `checkpoint_receipt_repair_20261015T203839Z/MANIFEST_FINAL.json` each matched their referenced SHA-256 and byte count. I inspected that coordinator receipt's four records; I did not independently rerun those four digest operations as part of this audit. Four reference identities do not prove all 108 manifest payloads or all runtime files.

Selected JSON receipts and reports were read directly from disk to confirm the status fields summarized above. Their claims are content evidence; where their paths are among the 4,586 unprocessed files, this audit has not independently hashed their bytes.

## Evidence and limits

- Root handoff: `docs/sessions/HANDOFF.md` lines 5, 12–15, 19–25, 29. It records later bounded verification, held promotion, unknown failure cause, and spent execution caps.
- Package summary: `REPORT.md` line 4 and headings at lines 1–40; `RETURN_PIN_COMPARISON.json`; `CANDIDATE_PRECHECK_MANIFEST.json`.
- Later diagnostic: `checkpoint_receipt_repair_20261015T203839Z/FINAL_DIAGNOSTIC_VERIFICATION.json` lines 2–47; final repair summary `checkpoint_receipt_repair_20261015T203839Z/FINAL_REPORT.md` lines 1–23.
- Gate and seal: `FINAL_REVIEW_SEAL.json`; `FINAL_VALIDATION.json`; `FINAL_GATE_DISPOSITION.json`; coordinator receipt `.runtime/codex_workflow_reconciliation_20261015T220836Z/SEAL_REFERENCE_VERIFICATION.json`.
- Build comparison: `ARTIFACT_PAYLOAD_COMPARISON.json`; `BUILD_DIFFERENCE_DISPOSITION.json`; `ARTIFACT_NAMESPACE_COMPARISON.json`.

This was a read-only audit of runtime evidence. No tests, helpers, builds, provider actions, or source changes were made. Large logs and media were statted but not loaded. Symlink targets were not followed. The inventory hash cap left 4,586 regular files without digests; full source-versus-candidate hashing and whole-manifest payload verification remain outside this report. QMD's runtime collection snapshot was stale (last indexed 2026-10-15T10:39:23.020Z, eight documents), so package evidence was read from disk rather than inferred from that index.

## Coordinator verification addendum

Verified after the inventory report: all ten root files still match the promotion plan's before hashes, and all ten candidate files match its after hashes; all ten pairs differ. Promotion is therefore still HELD in actual bytes, not merely in a status claim. Evidence: [.runtime/codex_workflow_reconciliation_20261015T220836Z/PROMOTION_HELD_FRESH_CHECK.json](../../.runtime/codex_workflow_reconciliation_20261015T220836Z/PROMOTION_HELD_FRESH_CHECK.json). This checks twenty files, not the entire source tree.

The runtime-only source report remains unchanged. The durable copy adds this independent verification; its original source hash is recorded in the header and RUNTIME_REPORT_INTEGRATION.json. File identities and a passing diagnostic do not establish a native Windows root cause or a passing full suite.
