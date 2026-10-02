# Purpose
Versioned sanitized replay corpus for adaptive semantic-planner failures.

## Ownership
- This folder owns one minimal JSON case per distinct historical failure boundary and sanitized aggregate live-run evidence under `evidence/`.

## Local Contracts
- Every case must validate through `load_semantic_failure_case`, including its input and candidate SHA-256 values.
- Link immutable raw receipts only by digest. Never commit provider response text, chat URLs, profile data, cookies, credentials or secrets.
- Keep request-contract, semantic-compiler and final-validator boundaries explicit. Repair-contract replay binds cardinality and the case brief's episode palette; global-only modes must reject before compilation. Visible-family regression pairs must reject visible mechanical props while accepting a plain local canvas whose purpose describes a cognitive mechanism. A corrected candidate must pass the compiled prefix without a late deterministic validator escape.
- Corpus replay is offline-only and must not import or invoke Gemini, Flow or browser transport.
- Add a new case only for a distinct independently understandable boundary; repeated occurrences belong in sanitized evidence metrics.

- A versioned pending escape record under `evidence/` blocks live advancement until its minimal candidate replay and fix are verified. The readiness report automatically blocks a recorded escape until a corrected, passing replay with the same stable code and completed-receipt digest covers it. The eight-case corpus covers `professor_lineage16_countdown_escape.json`; preserve the original pending record and separate resolution evidence.

- The fixed-tail framing case preserves topology and identity equality with synthetic visual descriptions. It rejects the last editable beat before a diagram-only tail and verifies a corrected fourth framing. Preserve the 8–16 ledger as its historical snapshot.

## Work Guidance
- Preserve existing cases as regression evidence. If a deliberate contract change alters a sanitized model dump, recalculate hashes and explain the lineage change in `tasks/adaptive-visual-tasks.md`.

## Verification
- Run `python -m pytest tests/unit/test_semantic_failure_replay.py -q`.
- Run the public corpus report against `evidence/professor_lineages_8_17.json` and require both replay and validator-audit readiness before any live planning request.

## Child DOX Index
- None.
