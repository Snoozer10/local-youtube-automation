# Error-Solving Scoped Instructions

These instructions govern error triage, incident documentation, and case management under `docs/error-solving/`.

## Read Order for Error Investigation

1. **Start with the shallow index**: Read [`docs/error-solving/README.md`](README.md). Search by domain/layer (e.g. `video.qsv`, `audio.pipe`, `browser.gemini`, `speech.manifest`, `os.filesystem`) or observed symptom.
2. **Read only the relevant case**: Follow the link from the index to the matching case in `docs/error-solving/cases/`. Do not load the entire legacy register into memory.
3. **Verify against evidence**: Follow evidence links in the case file to verify raw receipts, logs, or reproduction tests before taking action.
4. **Historical reference**: The original monolithic register [`docs/error-solving/understood-errors.md`](understood-errors.md) is preserved untouched as a historical archive with immutable SHA-256 integrity.

## Recording a New Case

When a new error pattern or failure mode is diagnosed:

1. **Use the template**: Copy [`docs/error-solving/TEMPLATE.md`](TEMPLATE.md) to `docs/error-solving/cases/ERR-XXX-<slug>.md`.
2. **Distinguish facts from hypotheses**: Clearly separate observed facts from diagnostic hypotheses, attempted fixes, and remaining gaps.
3. **Link raw evidence**: Provide relative links to receipts, logs, and failing/passing tests.
4. **Update the index**: Add a one-line entry to the index table in [`docs/error-solving/README.md`](README.md).

## Boundaries and Constraints

- **Preserve historical evidence**: Never delete, truncate, or rewrite `understood-errors.md` or existing case evidence.
- **Single layer ownership**: Every case must identify its responsible system layer.
- **Fail closed**: If an error's cause is not isolated, record status as `hypothesis` rather than claiming a definitive fix.
