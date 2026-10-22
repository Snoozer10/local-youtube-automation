<!-- Durable report copy. Verified source: .runtime/codex_workflow_reconciliation_20261015T220836Z/runtime_inventory/NESTED_PATH_REPORT.md; SHA-256 fba7087a4207773fa876ff48b7993f49fd9f3acf01c6d35598cff04f4abde033. -->

# Nested runtime path report

## Finding

The exact requested path `.runtime/.runtime/codex_antigravity_return_review_20261015T0923Z` is absent. The primary path `.runtime/codex_antigravity_return_review_20261015T0923Z` exists as a directory, but its presence does not establish that the nested path was a typo or intended alias.

No directory was created at the missing path. Since the target does not exist, it has no recursive entries, package map, bytes, file hashes, receipts, or seals to inspect. The absence finding is based on a direct filesystem existence/type check for the full requested target.

## Outcome and limitations

Result: `missing` for the exact nested path. The primary package inventory and report are separate evidence and are not substituted for this absent target. No tests or helpers were run, no symlinks were followed, and no content was manufactured to fill the path.

Evidence locations: exact target `.runtime/.runtime/codex_antigravity_return_review_20261015T0923Z`; primary sibling `.runtime/codex_antigravity_return_review_20261015T0923Z`; recursive inventory is intentionally limited to the primary existing target and is recorded in `INVENTORY.json`.
