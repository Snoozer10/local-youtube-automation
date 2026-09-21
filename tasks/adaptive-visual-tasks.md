# Adaptive visual engine — implementation checklist

Plan: [adaptive-visual-plan.md](adaptive-visual-plan.md). Usage: [adaptive-visual-usage.md](adaptive-visual-usage.md). Checked means implemented with the evidence below; live aesthetic checks remain separate.

Current state: staged adaptive implementation and offline verification complete for the checked items. Unattended full production is NOT complete. No live generation or historical regeneration has been launched. Three actual channel profiles are requested for pilot setup. The newer merged branch adds prompt loading, voice and viewer changes; the current verification record below supersedes the older baseline.

## A. Branch and baseline
- [x] A1 Fetch origin/master, verify clean worktree and PR #20 merge, create requested branch from dad17b3.
- [x] A2 Read DOX/current GEMINI.md and CI workflows; preserve historical task records.
- [x] A3 Save architecture and dependency-ordered checklist with acceptance criteria.
- [x] A4 Record full unit/lint baseline and pre-existing failures.

## B. P0 visual correctness (depends on A)
- [x] B1 Remove numeric framing instructions from active prompt sources; no coordinate literals reach diffusion.
- [x] B2 Remove unsolicited telemetry/placards; ordinary subject scenes receive no fabricated charts.
- [x] B3 Preserve full edit intent; retain/add/remove/replace/reframe operations; late clauses survive.
- [x] B4 Normalize current/legacy subject and setting fields for asset selection.
- [x] B5 Require exact same-scene references; no silent independent-generation fallback (contract and missing-reference adapter tests; successful live attachment remains E2).
- [x] B6 Honest static holds/animation disable; verify long and single-frame clips.
- [x] B7 Complete-asset and full-frame background OCR gates; unavailable OCR is not success.
- [x] B8 Focused prompt, Flow, text and render regressions pass.

## C. Adaptive brief compiler (depends on A)
- [x] C1 Strict versioned channel/analysis/brief models separate topic from identity.
- [x] C2 Explicit saved-channel selection for runs/batches; separate cross-channel outputs.
- [x] C3 Bounded raw-script section analysis via Gemini browser; synthesize whole-episode context.
- [x] C4 Deterministic policy resolution and bounded response repair; no analysis-generated executable code/selectors.
- [x] C5 Atomic brief persistence with source/profile hashes; validated resume only.
- [x] C6 Integrate before restructuring/translation; adapt refinement while preserving channel language/voice.
- [x] C7 Propagate resolved brief to adaptive shot planning, Flow and thumbnail prompts; adaptive runs bypass the legacy roadmap.
- [x] C8 Test contrasting channel policies, whole-script section coverage, invalid profiles and changed input hashes. Semantic accuracy on mixed-topic live scripts remains part of G4.

## D. Editorial shot planning (depends on C)
- [x] D1 Versioned shot plan with narration IDs, many-to-many timing and full coverage checks.
- [x] D2 Require treatment and visual purpose; instruct semantic idiom handling. Actual interpretation quality remains a pilot acceptance criterion.
- [x] D3 No mandatory progressive groups/camera cycles in adaptive mode; host remains channel policy.
- [x] D4 Distinguish local crop/reveal reuse from new generation; stable entity/scene IDs.
- [x] D5 Compile complete prompts and validate reference dependencies; prohibit invented evidence in planning instructions. Factual correctness still requires editorial review.
- [ ] D6 Test idiom, close-up, multi-span hold, multiple shots per span and boundaries.

## E. Assets and composition (depends on D)
- [x] E1 Asset receipts include recipe, bytes, dimensions, references and validation state.
- [ ] E2 Verified exact browser attachments and reference recovery after reload/resume.
- [ ] E3 Crop bounds/source resolution checks; no fixed upper-third focal target.
- [ ] E4 Explicit holds/pushes/pans/reframes, local reveals and shaped Arabic overlays.
- [x] E5 Derived edit timeline preserves canonical speech timing and invents no acoustic punches.
- [x] E6 Review contact sheets/report include prompts, reasons, references and rejections.
- [x] E7 Real temporary FFmpeg checks: frame count, static fidelity, overlays and valid encoding.

## F. Durable production (depends on E receipts)
- [x] F1 SQLite resource ledger with fenced claims, attempts, heartbeats and reclaim after expiry; stale publication is blocked. Durable per-stage scheduling is still F7.
- [ ] F2 Browser/clipboard/audio/encoder leases; bounded expiry and release.
- [ ] F3 Content-based invalidation, selective retries and preserved accepted outputs.
- [ ] F4 Validate complete generation before atomic activation; reconcile interrupted publication.
- [ ] F5 Crash/restart, stale worker, corrupted cache, missing output and competing claims tests.
- [ ] F7 Durable per-stage job scheduling, crash reconciliation and bounded circuit breakers, beyond shared resource leases.
- [ ] F6 Prior reliability backlog: exact run targeting, owned-process cleanup, propagated persistence errors, bounded subprocess reads and physical chapter offsets.

## G. Rollout and closeout
- [x] G1 Full unit suite, workspace lint, CI-equivalent checks and exercise linter; record outcomes.
- [x] G2 DOX pass: update root/child ownership and GEMINI current rules.
- [x] G3 CLI usage, migration, rollback and adaptive opt-in documentation.
- [ ] G4 Three contrasting 60-90 second pilots using selected channel profiles (live validation).
- [ ] G5 User reviews relevance/progression/continuity/readability/motion before full episodes.
- [ ] G6 Full-episode validation following pilot acceptance.

## Partial items and next work

| Item | Implemented | Remaining acceptance |
|---|---|---|
| C7 | Adaptive shot planner replaces legacy roadmap; Flow and thumbnail prompts consume the resolved brief. Thumbnails use content-bound accepted-image receipts and preserve legacy behavior for legacy runs. | Live visual quality, optional local thumbnail typography and editorial selection remain G4/G5. |
| D6 | Multi-span hold, multiple shots in one span, pagination, references and exact frame boundaries tested. | Live idiom and close-up interpretation on real narration. |
| E2 | Exact URL/project lookup plus decoded pixel identity and chip count; missing/wrong-project references block. | Successful live attachment and automatic restoration after project/account changes. |
| E3 | Bounded focal coordinates/zoom, even dimensions, maximum 2x source enlargement. The renderer now uses accepted source dimensions and the planned focal point for aspect cropping; a real FFmpeg off-center subject frame is verified. Review reports expose focal coordinates. | Confirm the model chose the actual subject point on generated images during pilot review; add a semantic or manual correction mechanism if it did not. |
| E4 | Explicit holds, pushes, pulls and focal-safe pans, local label/arrow/highlight timing; ASS Arabic encoding. Zoomless/no-travel motion is rejected. | Visual Arabic shaping/font/margins and local overlay motion/readability on pilot frames. |
| F2 | Shared browser leases on adaptive URL writing, analysis/planning/Flow, thumbnails and TTS; encoder lease on both renderer entrypoints. Adaptive TTS uses its own CDP tab and refuses to launch or terminate an unowned browser. Adaptive Audacity and stitching share the Audacity lease, and Audacity refuses to seize unrelated open processes. | Owned browser launch/profile rotation and legacy processes do not yet share all locks. Adaptive TTS deliberately stops instead of rotating accounts until ownership is tracked. |
| F3 | Hashed writing caches, brief/source/profile validation, asset model recipes, immutable accepted copies, clip byte hashes and renderer/tool recipes. | Full dependency-driven selective stage retries; changed source/profile with existing downstream output currently requires a fresh run. |
| F4 | Verify assets/timing/approval and unchanged inputs before atomic video activation; content-derived final filenames preserve old masters. Adaptive chapter stitching verifies that polished bytes match the saved manifest, then writes and frame-checks a temporary WAV before fenced replacement of the audio master. | Crash injection across all publication boundaries and explicit reconciliation of interrupted stages. |
| F5 | Competing claims, lease expiry, stale publication, corrupted writing/clip caches, missing exact references and stale approval tested. | Process-level crash/restart suite and all missing-output variants. |
| F6 | Explicit audio run arguments, adaptive supervisor isolation, correct polished-audio path, bounded new renderer subprocesses. Adaptive narration partitions the verified script without a second rewrite; completed WAVs require matching MD5. Adaptive voice cannot rerun after DSP starts. Adaptive Audacity refuses unrelated sessions, requires the checked-in preset and explicit pipe success, keeps checkpoints on incomplete work, and syncs exact gapless chapter offsets without rewriting the raw voice checkpoint. Adaptive stitching blocks partial or changed polish and atomically replaces the master. | Legacy Audacity cleanup, bounded pipe reads, remaining persistence surfaces and cross-stage process ownership audit. |
| G4–G6 | Offline synthetic renders only. | User channel profiles, three live 60–90 second pilots, actual editorial feedback and subsequent full episodes. |

## Verification evidence

- Base: `dad17b3` from updated origin/master after PR #20; requested branch created. Baseline was 520 unit tests passing and clean workspace Ruff.
- Final CI command: `venv/Scripts/python.exe -m pytest tests/unit -v --cov=. --cov-report=xml` — **557 passed in 25.64 seconds**. Local output: `.runtime/adaptive-ci-verification.txt` (ignored runtime evidence).
- Workspace `venv/Scripts/ruff.exe check .` passed.
- Strict new-package typing: `venv/Scripts/python.exe -m mypy src/youtube_automation/production --follow-imports=silent` passed for 11 files. Imported legacy modules are not asserted type-clean.
- `venv/Scripts/python.exe tools/lint_exercises.py` passed: 3 sections, 7 exercises, 35 files and 35 links. Hardware/browser/Audacity drills were not run.
- Real temporary FFmpeg: exact 30-frame/one-second preview with audio and an Arabic ASS label; master blocked before approval; changed render settings rejected after approval; tampered clip regenerated; canonical timeline bytes unchanged.
- Interrupted activation injection: failure while writing the new preview pointer leaves the previous pointer and accepted master hash intact. Per-invocation scratch files prevent expired workers from sharing pending video/filter files.
- Separate real FFmpeg hold test: all 12 decoded frame hashes identical on a detailed synthetic source.
- No Gemini/Flow/TTS/Audacity production session launched, network settings changed, historical run regenerated, remote branch pushed, PR opened or release published by these checks.
- After the user's merge, a fresh baseline passed 577 unit tests. The narration/thumbnail slice passed 588 tests (2026-09-20), workspace Ruff, production-package mypy (13 files) and exercise structural lint. The thumbnail browser test uses fakes; no live Gemini/Flow/TTS/Audacity run or aesthetic pilot was performed.
- Focal-crop slice: real FFmpeg frames retained off-centre subjects through both vertical and horizontal source-aspect crops. A camera recipe bump invalidates prior cached clips. The full unit suite passed **591 tests**; workspace Ruff and production-package mypy passed. Real pilot quality is still unverified.
- Adaptive audio-boundary slice: **600 unit tests** passed, plus workspace Ruff, production-package mypy (13 files), exercise structural lint and 7 focused integration tests. Offline tests cover gapless chapter offsets, changed polished bytes, incomplete polish, explicit Audacity pipe failures, user-owned Audacity protection, atomic stitching and explicit run arguments. No Audacity process, browser account, network setting or historical run was changed by these tests.
- Adaptive TTS ownership slice: shared browser lease, an owned tab that closes on exit, no adaptive browser launch or global profile rotation, and removal of a hard-coded AI Studio Chrome resolver address. **603 unit tests** passed, plus workspace Ruff, production-package mypy (13 files) and exercise structural lint. No live CDP account or system DNS setting was changed.
