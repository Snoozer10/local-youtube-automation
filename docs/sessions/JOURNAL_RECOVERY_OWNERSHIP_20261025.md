# Journal Recovery Ownership

Status: VERIFIED against baseline c774383. Gates passed; the user authorized one atomic commit and push for these scoped changes.

## Result
- Invalidation owns stage-output enumeration, canonical archive destinations, expected-journal comparison, conflict rejection, hash checks and interrupted recovery.
- Brief migration retains bounded metadata inventory, episode/narration lineage, eligibility and checkpoint phases. Audio adoption retains its existing recovery sequence.
- Callers use public operations instead of private pattern/journal imports or duplicated journal envelopes and archive formulas.
- Existing persisted formats, exact archive bytes, installation-wide publication guards and restart behavior are preserved.

## Accepted scope
The user selected the candidate and confirmed Q1, Q2 and final Q3 implementation. This completes only the selected ownership repair; other architecture-renewal work remains outside this change. No provider action, publication or release was performed.

## Verification
Full suite: **1979 passed, 9 skipped in 285.78s (0:04:45)**. The live cases remained skipped under default collection. Local execution used venv Python 3.11.9; mypy retained the configured Python 3.10 source contract.

| Gate | Result | Local ignored receipt (unavailable in a fresh clone) |
|---|---|---|
| baseline | PASS | [baseline.json](../../.runtime/journal_ownership_20261024T234158Z/baseline.json) |
| focused | PASS | [focused.json](../../.runtime/journal_ownership_20261024T234158Z/focused.json) |
| full | PASS | [full.json](../../.runtime/journal_ownership_20261024T234158Z/full.json) |
| lint | PASS | [lint.json](../../.runtime/journal_ownership_20261024T234158Z/lint.json) |
| typing | PASS | [typing.json](../../.runtime/journal_ownership_20261024T234158Z/typing.json) |
| production_typing | PASS | [production_typing.json](../../.runtime/journal_ownership_20261024T234158Z/production_typing.json) |
| build | PASS | [build.json](../../.runtime/journal_ownership_20261024T234158Z/build.json) |
| replay | PASS | [replay.json](../../.runtime/journal_ownership_20261024T234158Z/replay.json) |

Focused suite: 107 passed (baseline 104). Three added public-interface tests cover duplicate journal sources, unexpected journal fields, and valid reordered recovery with exact binary bytes. Full-source strict typing checked 73 files. Package byte readback checked 92 files in wheel and sdist. All 244 frozen inputs remained unchanged through verification.

## Review and evidence
The following .runtime links point to local ignored evidence and are unavailable in a fresh clone:
- [Independent review](../../.runtime/journal_ownership_20261024T234158Z/REVIEW.md): no blocking findings in the pinned diff; source/test pins were independently read back. This is a bounded review, not proof of zero defects.
- [Accepted decisions and research](../../.runtime/journal_ownership_20261024T234158Z/DECISIONS.md).
- [Exact binary preimages](../../.runtime/journal_ownership_20261024T234158Z/PREIMAGES.json).
- [Frozen inputs](../../.runtime/journal_ownership_20261024T234158Z/FROZEN_INPUTS.json) and [unchanged readback](../../.runtime/journal_ownership_20261024T234158Z/FROZEN_READBACK.json).
- [Package contents](../../.runtime/journal_ownership_20261024T234158Z/PACKAGE_READBACK.json).
- [Mixed-byte span proof](../../.runtime/journal_ownership_20261024T234158Z/coordinator_briefs_span_result.json) and [import-layout proof](../../.runtime/journal_ownership_20261024T234158Z/briefs_import_format_receipt.json).

## Failures and fixes
The first worker patch verifier stalled in whole-file SequenceMatcher before source writes. Its exact owned processes were stopped; deterministic original-coordinate byte spans replaced that verifier and reconstructed the original bytes exactly. The failed helper remains as local ignored evidence. A prior broad focused run was canceled at 86% and is not counted as a pass; the final 107-case run completed. Initial source lint found one I001 import-layout error; a bounded formatting patch repaired it, followed by a passing workspace lint. Ruff 0.16.6 research: [official I001 rule](https://docs.astral.sh/ruff/rules/unsorted-imports/). Local ignored failed lint output is preserved as source_lint.log/json. The new ownership-doc sentence required an LF ending for git whitespace checks; only that added ending was corrected, with its intermediate failed state and reconstruction receipt preserved as local ignored preimages/ evidence.

## Documentation disposition
Production AGENTS ownership and coordinator HANDOFF were updated for this refactor. Root AGENTS, tests AGENTS, the glossary and Child DOX indexes remain unchanged: global policy, test policy, vocabulary and document hierarchy did not change. Mixed line endings were retained with byte-span receipts. Prior release/branch receipts remain historical evidence for their original tree.

## Resume
Verification was performed against baseline c774383 on master, with pre-existing dirty work preserved. The user authorized one atomic commit and push containing only changes scoped to this session. Broader architecture-renewal work remains outside this change and open. Professor D1 remains deferred and no new live/provider grant exists. QMD remains unchanged under prior user direction.
