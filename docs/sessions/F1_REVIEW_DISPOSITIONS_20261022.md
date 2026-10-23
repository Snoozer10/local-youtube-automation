# F1 review dispositions - 22 October 2026

**Task ID:** TYPE-CLOSEOUT-20261022  
**Scope:** Current-source and test review matrix, 20 code rows plus two documentation rows. Engineering/formal-review scope is complete; this matrix does not grant merge or publication approval.

## Code review matrix

| ID | Current disposition |
|---|---|
| A1 | Contenteditable capture and post-send failure handling preserve reservations and avoid false completion. |
| A2 | Canary scope, dependencies, order, and selected cast are bounded and checked. |
| A3a | Existing orphan journals block new creation and spending. |
| A3b | Typed setup failures stop the attempt; generic retry behavior remains separately covered. |
| A4 | Alias and preview validation precede canonical image lineage. |
| A5 | Feedback checks bind to the current plan/brief or same source. |
| A6 | Archived human rejection binds to preview bytes and gates approval/recovery. |
| A7 | Private selector removal and public compatibility are verified; final audio freeze passed. |
| A8 | Planner/compiler lineage, immutable 6×6 grid, and canonical cues are covered. |
| B1a | Cache recomputes current inputs and validates the physical preview. |
| B1b | Approval rechecks recipe and preview under publication guard. |
| B2 | Timer starts must be distinct; repeated ambiguous limits reject. |
| B3 | Geometry constants are present; exact centering remains a test-assertion limit. |
| B4 | Cue intervals clip across shot boundaries without restarting ASS timing. |
| B5 | High-rate ASS splitting preserves Unicode separators. |
| B6 | Unsupported, ambiguous, and out-of-range bound limits reject safely. |
| B7a | Renderer, cue, pictogram, encoder, config, and tool inputs bind into fingerprints. |
| B7b | Canonical semantic ASS hashing is separate from physical artifact bytes. |
| B7c | Critic canvas dimensions are explicit and alternate dimensions fingerprint separately. |
| B8 | Current CI Ruff route verified; final repository Ruff gate passed. |

## Documentation rows

| ID | Current disposition |
|---|---|
| Docs compiler/renderer lineage | Source lineage verified at 24/15/14; historical documentation is not used as current evidence. |
| Docs cue lineage | Unsupported cue-4 claim is absent from current source constants; no cue-version claim is inferred. |

## Proof and accepted limits

- Independent review matrix: `.runtime/codex_typing_20261021/review/TYPE-F1-INDEPENDENT-20261021-FIRST.json`.
- Final disposition and seals: `.runtime/codex_typing_20261021/F1_DISPOSITION.json`, `.runtime/codex_typing_20261021/ENGINEERING_RESULT.json`.
- All 20 code and two documentation rows map to current dispositions. The final strict mypy, full tests, Ruff, build, lint, and replay gates all exited zero.
- Three test weaknesses were repaired and independently reviewed; two child cases were preserved.
- Accepted limits: containment is asserted instead of exact preview-board centering; lazy-facade smoke evidence is a runtime probe, not a committed regression; viewer JavaScript was not exercised; DOM mocks do not prove live UI behavior.
- Pilot spending, human approval provenance, current render recipes, and restart reconciliation remain explicitly excluded and unverified. No provider, GUI, browser, or live action occurred.
- The early reduced-scope diagnostic configuration was rejected and is not acceptance evidence. The final gate used unchanged project configuration.

Canonical records and QMD lexical readback are synchronized; see `.runtime/codex_typing_20261021/QMD_CLOSEOUT.json`. Embeddings remain incomplete; semantic retrieval was not used.


Exact source fingerprint: `af6222b47abf68ebaf67977cec8f47855c401e49b83ab04295b5a00a6afec662`. Local review package: `.runtime/codex_typing_20261021/formal_review/`. No commit, push, remote CI, formal review request or merge was performed.
