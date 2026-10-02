# Purpose
Offline verification, regression evidence and deterministic test fixtures.

## Ownership
- This tree owns unit and integration tests, local stubs and sanitized test-only evidence.

## Local Contracts
- Unit tests must not invoke live Gemini, Flow, browser transport or paid/network services. Use fakes, preserved sanitized fixtures and public production seams.
- Preserve historical regression evidence that remains linked from a durable replay contract. Do not replace a failing fixture merely to make a changed implementation pass.
- fixtures/semantic_graphic_copy_v1.json records sanitized GRAPHIC_COPY_LOSS evidence; the compiler-to-ASS regression must preserve primary and secondary copy for kinetic_type and focus_sweep.
- Test behavior and externally meaningful failure boundaries rather than incidental private call order.

## Work Guidance
- Keep fixtures minimal, deterministic and free of secrets or machine-specific session identifiers.
- When production behavior intentionally changes, add or update the smallest regression that proves the new contract and retain separate cases for distinct failure boundaries.

## Verification
- Run focused changed tests first, then `python -m pytest tests/unit -q` before closeout.

## Child DOX Index
- `fixtures/semantic_failures/AGENTS.md`: sanitized adaptive semantic-failure corpus and evidence ledger.
