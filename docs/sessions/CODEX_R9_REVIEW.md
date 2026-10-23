# Task ID: R9-review-records

## Scope and disposition

- Codex review of Antigravity's R9 candidate on `codex/adaptive-multi-channel-visual-engine`, HEAD `41d02eb`, dirty working tree.
- Antigravity's `ANTIGRAVITY_R8_RESULT.md` remains its self-report. It is not independent acceptance evidence.
- R9 is **rejected for visual approval**. Keep the current candidate local; no provider use, approval, publication, or stage advancement is authorized.
- Candidate raw and typed fingerprints agree: `6bd5c7f6c03fc91fc759214ae762c4ff6cfb1083375636c0bdf7aac39eb2b024`. Renderer lineage is 9.

## Source repair and verification

- Antigravity changed `render.py` to floor timer centiseconds with `frame * 100 // fps`. The pilot displays 00:39 at local frame 119 / global frame 2284, one second after clock local frame 89 / global frame 2254; the full pilot ends at frame 2296. Frame 119 is not the pilot's end.
- FFmpeg plus local Tesseract confirms a phase-dependent 120 fps early tick. Phases 1/7/13/19/109 show 00:39 on prior frames 120/126/132/138/228 before nominal tick frames 121/127/133/139/229. Phase 2 (121→122) and phase 103 (222→223) transition correctly. No 120 fps fix is implemented.
- Recommended fix: render timer text by frame index in shared production and inspection paths, using canonical `timer_segments`; preserve generic ASS, timed labels, and assets; bump renderer/cache identity; and prove actual pixels at supported rates including 120 fps. Generic cue fade is unchanged and separate from timer quantization.
- Tester changed only `tests/unit/test_production_render.py`; Antigravity's source change to `render.py` remains in the candidate.

## Visual review

- Root reviewed early/late contact coverage for all 21 shots. Investigator reviewed original early samples for each rejected shot and three distinct phases of shot 4; identical phase hashes substitute only where equivalence was confirmed. Contact sheets do not establish individual middle-frame review.
- Revised graphics 2, 4, 6, 8, and 9 remain rejected as copy-led static treatments: document/list (2); decorative left-to-right scan against RTL text (4); static slogan and unspoken “nontraditional thinking” (6); cursor without an interaction target (8); question panels without an explanation (9).
- Separate original-PNG investigator scores (semantic / continuity / readability / attractiveness): 2 = 3/4/4/3; 4 = 4/4/4/3; 6 = 3/4/4/3; 8 = 4/4/4/3; 9 = 4/4/4/3.
- No actual 480 px derivative was available; phone-scale readability remains unverified. R9 is not approved. No provider use, publication, or stage advancement is authorized.

## Preservation and final gates

- `.runtime/codex_r9_preservation.json` verifies both R8 and R9 manifests at 83 proofs / 21 rows, all 21 accepted asset records/bytes/pixels/recipes, the original active plan, archived R7/R9 preimages, and unchanged timeline. Only overlay/viewer-takeaway fields changed on shots 2/4/6/8/9; semantic links, 16 raw shot records, and plan metadata are unchanged; cue rebind was a no-op.
- The R9 archive manifest incorrectly reports zero R8 proofs; the original R8 proof manifest correctly records 83. Cause: `archive_r8_and_apply_r9.py` reads top-level `manifest['proofs']` although proofs are nested in rows. The separate receipt preserves proof evidence; leave the original archive unchanged.
- `local_review21rows` has plan fingerprint/package header but no per-row proof hashes. Audio and spend baselines are unavailable; unchanged audio and zero provider spend are unverified.
- Tester gates passed: focused suite 45; `tests/unit` 974 passed in 36.99s; Ruff clean; production mypy clean across 20 files; exercise lint exit 0 (3 sections, 7 exercises, 35 files, 35 links); drills exit 0 (36 passed, 1 skipped, 16.52s). Real FFmpeg 24/25/30/60 samples ran; FFmpeg absence has an explicit skip. Codex changed tests only; Antigravity changed production source.
- Root reran `git diff --check` after the documentation edits; it passed with existing CRLF warnings.

## Next
- R9 review milestone is complete. R10 design work is active for the frame-indexed high-rate timer repair; no source fix is implemented yet.
- Implement and verify the frame-indexed high-rate timer correction, then produce fresh current proof.
- Redesign shots 2/4/6/8/9 around source-bound actions; review originals and actual 480 px derivatives before reconsidering approval.
- Quota: baseline 33%, cumulative allowance 22 percentage points, ceiling 55%, current 37%. The allowance covers bounded local repair only; provider operations remain unauthorized.
