# Spec #23 completion and closure evidence

## Scope and result

The completion adds story 16 final-artifact verification receipts and corrects the independent review's pairwise audio/video drift finding under story 18. It follows local repair commit db2ad58; unrelated working-tree files remain outside both PRs. Guidance commit 70213c1 is a separate dependency PR (#51).

## Artifact contract

Each successful compilation prepares an immutable, version-1 JSON receipt at the video's parent/.compilation-receipts/<artifact-sha256>.json before the single atomic video replacement. The receipt binds artifact SHA-256 and byte size, measured frame count, FPS, container/video/audio durations, dimensions, decoded pixel format, color range and audio presence. It contains artifact facts rather than generation/profile labels, permitting equivalent artifacts and same-parent content-derived renames.

The public verification_receipt_path and verify_compilation_receipt APIs derive identity from stable current video bytes and use bounded, strict JSON validation. Missing, malformed, duplicate-field, stale, conflicting, redirected or tampered evidence fails closed. Production activation/recovery, current-preview approval and CLI stage reuse also match the current render hash, target and frame budget. Technical receipts do not authenticate malicious writers or supply human editorial approval.

Receipt preparation or failed video replacement preserves the previous valid pair. Interruption after replacement leaves a complete new pair; an unreferenced prepared receipt is retained as diagnostic evidence. Recovery and reruns reuse verified work. Both compiler and receipt verifier enforce direct audio/video drift within one frame, in addition to canonical timing checks.

## Verification

Frozen tree: 597 pinned inputs, no drift. All subprocesses exited 0 in final-gates-v4/RESULT.json.

- venv/Scripts/python.exe -m pytest tests/ -q --tb=short -x: **2,141 passed, 9 skipped**, 403.96 seconds; stdout SHA-256 9ba0dd291eaa8d1b0488a4ebcbcc273cd9a86640adf891f5705298bb2efb9225.
- venv/Scripts/python.exe -m mypy --strict src/: **78 source files passed**, no exclusions or suppressions.
- venv/Scripts/python.exe -m ruff check .: **passed**.
- venv/Scripts/python.exe -m build --no-isolation --sdist --wheel --outdir <evidence>/final-gates-v4/dist: **passed**, version 4.5.1 wheel and sdist. Existing setuptools license metadata deprecations remain warnings.
- Focused CLI/production integration: **82 passed**; independent receipt/consumer review: **39 passed**; fixture compatibility: **10 passed**. These overlap the full suite and are not added to its count.

Saved native artifact/receipt pairs were reverified read-only by the current verifier after the indentation-only correction; no additional native commands were issued.

The earlier failed full packet (1,028 passed, 9 skipped before the receipt-less orphan fixture) and the import-only lint failure remain intact; they are superseded by this frozen passing packet.

Review records: independent Spec review and coordinator Standards review are recorded separately under .runtime/spec23_completion_20261026T061513Z/. The original Standards worker stalled; its replacement hit HTTP429 after partial inspection. Neither is counted as an independent approval. Coordinator readback corrected the new writer to use the documented two-space JSON indentation; receipt tests and the full frozen gates were refreshed afterward. The Spec reviewer reproduced a 0.06-second A/V discrepancy at 30 FPS, supplied two RED public-seam regressions, and verified them GREEN after the direct pairwise checks. The fixtures now produce durable media evidence through the public fake compiler rather than labelling arbitrary bytes as verified video.

Bounded native proof: two successful CPU compilation requests, no provider/browser/GPU calls. Legacy root CLI produced 60 frames/2 seconds at 320x180; public production render_plan produced 30 frames/1 second at 640x360. Both measured 30 FPS, yuv420p/tv with audio; receipt hashes matched the videos, and separate tampered copies rejected while original pairs remained unchanged. Synthetic asset OCR setup was stubbed and disclosed. These are functional proofs, not production/editorial or actual hardware-encoder acceptance.

## Acceptance reconciliation

- Stories 1-2, 14-15: declarative master/preview engine, root CLI and production caller; current public-seam tests and both native entrypoints.
- Stories 3-5, 7, 20: encoder preference/upload/fallback policy, TV range and per-run detection; fake-runner regressions and measured CPU output. Actual GPU execution is not claimed.
- Story 6: content-addressed clip journal, isolated fallback evidence, verified cache reuse; current journal/compiler tests plus preserved prior native cache proof.
- Stories 8-10: deep video boundary and runner adapters; current media-runner, compiler and delegation regressions.
- Stories 11-13, 17, 19: consolidated overlays/filtergraphs, kinematics, transient splitting, file-backed graphs and Schulte primitives; current filtergraph, subtitle, production/graphics and compiler tests. Prior native subtitle proof remains historical evidence, distinct from this receipt completion.
- Story 16: immutable final-artifact receipts, strict consumer API and production enforcement; current receipt/recovery/consumer tests plus both native proofs.
- Story 18: canonical timing and direct pairwise A/V drift; independent RED/GREEN regressions and current full suite.
- Story 21: retained subprocess diagnostics and rejected candidates; runner/compiler failure and preservation tests.

The detailed 21-story/child-ticket crosswalk is retained at .runtime/spec23_completion_20261026T061513Z/acceptance/SPEC23_ACCEPTANCE_CROSSWALK.md. #24 and #30 were already closed; #25-#29 and parent #23 close only after the verified compilation PR is integrated.

## Retained failures and limits

The initial consumer fixture edit failed to match CRLF bytes and the unchanged focused check failed twice. The coordinator stopped under the two-strike rule, obtained the user's explicit continuation, then applied a symbol-bounded byte-preserving correction. Earlier manual media copies and a human-rejection orphan fixture lacked newly required receipts; they now carry compiler-produced evidence without weakening guards. The fake runner's all-zero output collision across differing media properties was corrected with deterministic content/metadata-bound bytes. Raw failed results, import/type corrections, the native helper's pre-execution root-path correction, preimages and verified reconstruction records remain in the ignored evidence directory.

Historical audit/repair reports are preserved unchanged. Root guidance/platform adapters, product/architecture renewal documents, runtime state, skill locks, source assets and unrelated deletions remain outside this completion commit. The closest source/production/test contracts describe the new behavior; root routing and child indexes require no change. QMD was not used for retrieval or explicitly updated; a checkout hook launched its configured graph rebuild when creating the compilation branch, retained as a tool-side effect rather than a new validation claim.

## Integration state

Guidance dependency PR #51 merged as bc05960c65199978c3149bbb4c3880a683ef35c4; exact-head CI passed and #36 is closed. Compilation completion is prepared on codex/spec23-compilation-completion, with the final commit and PR recorded in the tracker and local CLOSEOUT.json. Issues remain open until integration succeeds.
