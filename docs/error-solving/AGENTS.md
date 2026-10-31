# Error-Solving Scoped Instructions

These instructions govern error triage, incident documentation, and case management under `docs/error-solving/`.

## Read Order for Error Investigation

1. **Start with the shallow index**: Read [`docs/error-solving/README.md`](README.md). Search by domain/layer (`os.filesystem`, `video.qsv`, `audio.pipe`, `speech.manifest`, `browser.gemini`, `pipeline.gate`) or observed symptom (~900 tokens).
2. **Read only the relevant case**: Follow the link from the index to the matching case in [`docs/error-solving/cases/`](cases/) (`ERR-XXX-<slug>.md`, ~600 tokens). Do not load the legacy register into memory.
3. **Parse HADS semantic blocks**:
   - Read `**[BUG]**` and `**[SPEC]**` blocks for authoritative failure modes, verified fixes, and prevention guards.
   - Read `**[?]**` blocks for diagnostic hypotheses and boundary limits — treat with lower confidence.
   - Skip `**[NOTE]**` blocks during rapid triage; consult only if previous failed attempts or historical context are needed.
4. **Verify against evidence**: Follow evidence links in the case file to verify raw receipts, logs, or reproduction tests before taking action.
5. **Historical reference**: The original monolithic register [`docs/error-solving/understood-errors.md`](understood-errors.md) is preserved untouched as a historical archive with immutable SHA-256 integrity.

## Recording a New Case

When a new error pattern or failure mode is diagnosed:

1. **Use the HADS template**: Copy [`docs/error-solving/TEMPLATE.md`](TEMPLATE.md) to `docs/error-solving/cases/ERR-XXX-<slug>.md`.
2. **Distinguish facts from hypotheses**: Use `**[BUG]**` for confirmed root cause and fix; use `**[?]**` for diagnostic hypotheses and unverified gaps.
3. **Link raw evidence**: Provide relative links to receipts, logs, source modules, and passing tests.
4. **Update the index**: Add a one-line entry to the active table in [`docs/error-solving/README.md`](README.md).

## Legacy Heading Promotion (The 3-Gate Rule)

Do not perform unverified bulk extractions of the 61 legacy headings in `understood-errors.md`. Promote legacy records opportunistically:

1. **Gate 1 (Trigger)**: The subsystem or error pattern is touched during active feature work or incident investigation.
2. **Gate 2 (Verification)**: The promoted case includes an active, passing unit test in `tests/unit/` verifying the prevention guard.
3. **Gate 3 (Index)**: Add the new `ERR-XXX` entry to `README.md` and update the `Legacy Headings Resolution Map` anchor row.

## Incidents vs. Error-Solving Boundary

- **[`docs/incidents/`](../incidents/) (Run-Specific Forensics)**: Time-bounded postmortems tied to a specific execution run, episode slug, timestamp, and transient state.
- **`docs/error-solving/cases/` (Canonical Remedies)**: Decontextualized engineering remedies defining invariant failure modes, exact root causes, code prevention guards, and unit tests.
- **Cross-Linking**:
  - In error case files: Link origin postmortems under `Origin Incident: ../../incidents/INCIDENT_<slug>.md`.
  - In incident postmortems: Link reusable remedies under `Canonical Error Case: ../../error-solving/cases/ERR-XXX-<slug>.md`.

## Boundaries and Constraints

- **Preserve historical evidence**: Never delete, truncate, or rewrite `understood-errors.md` or existing case evidence.
- **Single layer ownership**: Every case must identify its responsible system layer (`os.filesystem`, `video.qsv`, `audio.pipe`, `speech.manifest`, `browser.gemini`, `pipeline.gate`).
- **Fail closed**: If an error's cause is not isolated, record status as `hypothesis` rather than claiming a definitive fix.
