# Adaptive visual engine — implementation checklist

Plan: [adaptive-visual-plan.md](adaptive-visual-plan.md). Usage: [adaptive-visual-usage.md](adaptive-visual-usage.md). Checked means implemented with the evidence below; live aesthetic checks remain separate.

Current state: staged adaptive implementation and offline verification complete for the checked items. Unattended full production is NOT complete. No live Flow generation or historical regeneration has been launched. The three actual channel profiles, existing-upload caption excerpts and channel analyses are prepared; published narration audio is on the owner's work drive and will be provided later. The newer merged branch adds prompt loading, voice and viewer changes; the current verification record below supersedes the older baseline.

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
- [x] D6 Test idiom, close-up, multi-span hold, multiple shots per span and boundaries. Live semantic quality remains G4h.

## E. Assets and composition (depends on D)
- [x] E1 Asset receipts include recipe, bytes, dimensions, references and validation state.
- [x] E2 Verified exact browser attachments and reference recovery after reload/resume.
- [x] E3 Crop bounds/source resolution checks; no fixed upper-third focal target. Live subject-point accuracy remains G4j.
- [x] E4 Explicit holds/pushes/pans/reframes, local reveals and shaped Arabic overlays. Live Arabic readability remains G4j.
- [x] E5 Derived edit timeline preserves canonical speech timing and invents no acoustic punches.
- [x] E6 Review contact sheets/report include prompts, reasons, references and rejections.
- [x] E7 Real temporary FFmpeg checks: frame count, static fidelity, overlays and valid encoding.

## F. Durable production (depends on E receipts)
- [x] F1 SQLite resource ledger with fenced claims, attempts, heartbeats and reclaim after expiry; stale publication is blocked. Durable per-stage scheduling is still F7.
- [x] F2 Browser/clipboard/audio/encoder leases; bounded expiry and release.
- [x] F3 Content-based invalidation, selective retries and preserved accepted outputs.
- [x] F4 Validate complete generation before atomic activation; reconcile interrupted publication.
- [x] F5 Crash/restart, stale worker, corrupted cache, missing output and competing claims tests.
- [x] F7 Durable per-stage job scheduling, crash reconciliation and bounded circuit breakers, beyond shared resource leases.
- [x] F6 Prior reliability backlog: exact run targeting, owned-process cleanup, propagated persistence errors, bounded subprocess reads and physical chapter offsets.

## G. Rollout and closeout
- [x] G1 Full unit suite, workspace lint, CI-equivalent checks and exercise linter; record outcomes.
- [x] G2 DOX pass: update root/child ownership and GEMINI current rules.
- [x] G3 CLI usage, migration, rollback and adaptive opt-in documentation.
- [ ] G4 Three contrasting 60-90 second pilots using selected channel profiles (live validation).
- [ ] G5 User reviews relevance/progression/continuity/readability/motion before full episodes.
  - Snoozer partial: user editorial approval received after the arrow revision and final preview. Professor and Soldier reviews remain open.
- [ ] G6 Full-episode validation following pilot acceptance.

### G4 pilot execution ledger

- [x] G4a Save and validate channel profiles for Professor Yashrah, Soldier's Sledger and Snoozer Anime. Professor retains Achird; the other two preserve source narration for these pilots.
- [x] G4b Select published-upload caption excerpts and record source URL, language, 60–90 second bounds and hashes in fresh run folders: Professor 0–69.08 seconds/161 words, Soldier 0–69.4 seconds/161 words, Snoozer 19.9–89.72 seconds/190 words. No historical run changed.
- [x] G4c Run channel-bound analysis before any rewrite or translation; all three version-2 `episode_brief.json` files exist and match the saved profile/raw text. Professor and Soldier are factual with external verification questions; Snoozer is fictional with empty evidence needs and explicit continuity anchors.
- [x] G4d Install `pytesseract` in the project venv, extract a hash-verified Tesseract engine to ignored `.runtime`, add official Arabic data and verify a real bilingual OCR probe. Add the package prerequisite and explicit `eng+ara` adaptive gates.
- [x] G4e Add and test a source-preserved audio import that binds local owner media, excerpt boundaries, original script and WAV bytes; TTS cannot replace accepted source audio.
- [ ] G4f Receive local owner media, import the three matching narration excerpts and inspect the resulting WAVs against the selected captions.
  - Snoozer complete: matched the owner-provided Hokkaido Gals master and Arabic source PDF. Imported 13.12–84.56 seconds as a hash-bound 71.44-second mono 48 kHz PCM WAV without modifying the master.
  - Professor partial: matched an archived Schulte-challenge `full_episode_voice.wav` to the selected script, then imported a separate 0–76.55-second cut, ending after the last spoken word. Source SHA-256 `967f539225482772a7f4c7e9571023c293d33ad9871ba10114841e8fe858b203`; imported WAV SHA-256 `7a89334ef0c8023d0a0f464810c6df18887688be37631fd2f4f45e0af9a92fa0`. The 0–69.08-second published-caption pilot remains unchanged. CapCut edits mean this archived pipeline voice track is not proven identical to the published narration. Soldier's selected Ardennes media remains unmatched.
- [ ] G4g Transcribe all three imported WAVs, verify canonical timing and correct caption/ASR errors without changing spoken audio.
  - Snoozer complete: Faster-Whisper plus spelling correction produced 235 canonical words, 19 spans and 2,144 frames; the final span matches the selected ending and timeline/audio drift is 40 ms.
  - Professor partial: Faster-Whisper aligned the owner-archived 76.55-second cut to four canonical spans and 2,296 frames; final speech ends at 76.52 seconds, within 30 ms of audio end. ASR made some lexical errors, so the primed transcript and canonical timing need editorial word-level review before claiming G4g complete. Soldier remains open.
- [ ] G4h Generate and editorially inspect three shot plans for factual caution, idiom meaning, visual progression, consistency and crop choice.
  - Snoozer complete: rejected a 6-shot/71-second plan for dull pacing, a 15-shot plan with empty entity IDs, and a 19-shot plan that literalized popsicle and organ-to-ice-cream jokes. The accepted 16-shot/2,144-frame plan has purposeful cuts, eight deliberate reuses, selective motion, explicit entity continuity and no literalized idioms. Professor and Soldier remain open.
  - Professor editorial gate: the archived roadmap relied on repeated white-isolation layouts, HOST/USER tokens, glowing brains and neon icons. Reject a new plan that repeats that grammar. The 1–36 Schulte grid, numerals, timer, focus marker and Arabic text must be drawn locally with deterministic positions; Flow stills should supply distinct human-context compositions or backgrounds. Do not imply that this exercise doubles processing speed or proves a clinical benefit. The archived voice excerpt is pre-CapCut pipeline narration, so compare aesthetics and timing without claiming published-video identity.
- [ ] G4i Generate technically accepted stills in Flow with real bilingual OCR and verify exact reference attachment/recovery where edits require it.
  - Snoozer complete: eight 1,376x768 Flow stills passed the bilingual OCR gate. One Minami frame with generated Japanese signage was rejected and replaced. Signed-URL refresh and an empty reloaded Flow project were both exercised; the engine restored the exact receipt-bound accepted PNG and verified one attached ingredient before continuing the reference chain. Professor and Soldier remain open.
- [ ] G4j Render three previews, inspect mobile-sized frames, Arabic shaping, local overlays, motion restraint, pacing and continuity; record rejects/revisions.
  - Snoozer technically complete: rendered 2,144 frames at 1,920x1,080/30 fps with 71.44-second source narration and 27 ms container/audio difference. Review rejected the first arrow placement because it crossed Shiki's torso; the rerender starts at his gesture and points into the road. The Arabic duration label is shaped and readable, the mobile frame preserves both subjects, and no black-frame interval was detected. User editorial review remains G4k.
- [ ] G4k Obtain user editorial review before approving any pilot master; keep G5/G6 open until separately completed.
  - Snoozer complete: the user approved the reviewed preview on 2026-09-22. The approval receipt binds the current plan, eight asset hashes and preview hash; the matching master is active with `editorial_status: approved`. Professor and Soldier remain open.

## Partial items and next work

| Item | Implemented | Remaining acceptance |
|---|---|---|
| C7 | Adaptive shot planner replaces legacy roadmap; Flow and thumbnail prompts consume the resolved brief. Thumbnails use content-bound accepted-image receipts and preserve legacy behavior for legacy runs. | Live visual quality, optional local thumbnail typography and editorial selection remain G4/G5. |
| D6 | Multi-span hold, multiple shots in one span, pagination, references and exact frame boundaries tested. | Live idiom and close-up interpretation on real narration. |
| E2 | Live Flow attachment survives signed-URL refresh, verifies the provider media identity and counts one canonical prompt chip. When Flow reloads without provider cards, it re-uploads only the receipt-bound content-addressed accepted PNG and verifies one attached ingredient. | Cross-account restoration remains deliberately blocked until account ownership can be proven. |
| E3 | Bounded focal coordinates/zoom, even dimensions, maximum 2x source enlargement. The renderer now uses accepted source dimensions and the planned focal point for aspect cropping; a real FFmpeg off-center subject frame is verified. Review reports expose focal coordinates. | Confirm the model chose the actual subject point on generated images during pilot review; add a semantic or manual correction mechanism if it did not. |
| E4 | Explicit holds, pushes, pulls and focal-safe pans, local label/arrow/highlight timing; ASS Arabic encoding. Zoomless/no-travel motion is rejected. | Visual Arabic shaping/font/margins and local overlay motion/readability on pilot frames. |
| F2 | Shared browser leases now cover adaptive and legacy browser entrypoints, clipboard writes use their own short lease, and both renderer paths use the encoder lease. Audacity entrypoints share one lease, refuse unrelated open sessions and terminate only processes they launched. Browser rotation records the exact CDP listener PID and refuses unregistered or replacement processes. | Complete. Adaptive TTS deliberately stops instead of rotating accounts because its CDP session remains user-owned. |
| F3 | Stage recipes now drive dependency-aware invalidation in the same run. Mutable downstream pointers and receipts move into `.adaptive_history/`; content-addressed accepted images, immutable renders and reusable caches remain available. Interrupted invalidation reconciles from its journal before another stage runs. | Complete. |
| F4 | Asset, writing, source-audio, thumbnail, preview and master publication now journal their complete content-bound activation intent. Recovery validates lineage and bytes before activating an orphan, while prior accepted pointers survive interrupted replacement. | Complete. |
| F5 | Competing claims, lease expiry, stale publication, corrupt caches, missing output, publication failure and real process death are covered. Restart reconciliation finishes an interrupted archive without losing immutable accepted output. | Complete. |
| F7 | Every adaptive CLI stage has a run-bound recipe over its actual files, selected profile/media bounds, effective planner/Flow model and render configuration. Unchanged success skips only after output validation; missing/corrupt output repairs automatically; content-bound existing outputs can be registered without repeating work. Changed recipes reset attempt lineage, expired workers are reclaimed with a higher fence, stale publication is blocked, and three failures open a circuit with explicit `--force-retry` recovery. Stage and distinct device leases nest and jointly fence publication. | Extend the durable scheduler to legacy entrypoints only when those tools are migrated into explicit adaptive runs. |
| F6 | Exact run targeting, adaptive supervisor isolation, bounded FFmpeg stderr pumping, strict bounded Audacity exchanges and exact physical chapter offsets are enforced. Legacy Audacity now follows the same lease and owned-process rules. Browser cleanup preserves user tabs, and CDP process cleanup requires the registered listener PID. | Complete. |
| G4–G6 | Three real channel profiles, caption excerpts and analyzed briefs are ready. Snoozer has imported source narration, a canonical timeline, an accepted 16-shot plan, eight accepted Flow assets and a user-approved 71.47-second master; rejected plans, signage and overlay placement are preserved as evidence. Professor has a separate 76.55-second owner-archived narration cut and canonical timeline; its published-caption pilot is preserved. | Professor plan/visuals/preview and editorial comparison, Soldier matching media and pilot, then full episodes. Professor Yashrah remains assigned to Achird for future synthesis. The archived voice track is not proven identical to the CapCut-edited published upload. |

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
- Adaptive Audacity pipe deadline slice: adaptive command writes and reads now have a bounded exchange time and a 1 MiB response cap, while legacy protocol behavior stays compatible. **604 unit tests** passed, plus workspace Ruff, production-package mypy (13 files), exercise structural lint and the focused Audacity integration tests. No live Audacity process was launched.
- Three-channel pilot preparation: the three public uploads above yielded existing-language captions; `youtube_runs/adaptive-pilot-*` stores final 161/161/190-word source excerpts and profile-bound analyses. A required claim-basis contract separates factual verification from fictional continuity: Professor and Soldier retain explicit fact-check questions, while Snoozer has empty evidence needs, four source continuity anchors and separately tagged figurative phrases. Each live analysis required at most one bounded retry when the Gemini model selector did not hydrate. YouTube audio download returned HTTP 403; owner-archived Professor voice was subsequently found, while Soldier's selected Ardennes media remains unmatched. Project-local Tesseract 5.4 reported `eng`, `ara`, `osd`; a real bilingual probe detected English and Arabic bitmap text.
- Pilot-preparation closeout: **608 unit tests** passed, workspace Ruff passed, production-package mypy passed for 14 source files, exercise structural lint passed for 35 files/35 links, and `git diff --check` passed. The episode brief contract is version 2 because claim basis and continuity anchors are required fields; the three ignored pilot briefs were migrated and revalidated. Source-audio activation is written only after WAV and preserved text bytes verify.
- Snoozer owner-media checkpoint: matched the Hokkaido Gals master to its Arabic source PDF, imported 13.12–84.56 seconds, and produced a 71.44-second source-bound WAV plus a 235-word/19-span/2,144-frame canonical timeline. Live editorial inspection rejected three generated plans before Flow: 6 shots were too sparse; 15 shots omitted continuity entities and invented frost transformations; 19 shots gamed entity declarations and literalized popsicle/organs jokes. Local hardening added clean-chat isolation, exact Gemini model labels, bounded transport retries, tolerant single-JSON decoding, process-over-dotenv precedence and shot-plan v2 editorial gates. Full closeout passed **622 unit tests**, workspace Ruff, production-package mypy for 14 files, exercise structural lint for 35 files/35 links, and `git diff --check`.
- Snoozer visual-pilot checkpoint: Flow produced eight accepted 1,376x768 stills and one preserved signage rejection. Live reference chains survived signed-URL refresh and provider-card loss by restoring the exact accepted PNG. The 16-shot preview renders 2,144 H.264 High/yuv420p frames at 1,920x1,080/30 fps with a 71.44-second mono 48 kHz AAC source track; container/audio difference is 27 ms and black-frame detection reported no interval. A first arrow placement was rejected and rerendered clear of both characters. Closeout passed **625 unit tests**, workspace Ruff, production-package mypy for 14 files, exercise structural lint for 35 files/35 links, and focused live-artifact inspection. The user approved the final preview on 2026-09-22; its exact lineage is activated as an immutable master.
- Publication-recovery slice: accepted-image journaling recovers complete content-bound orphans and refuses missing bytes; preview/master journaling preserves the prior pointer across activation failure and then activates the verified encoded orphan without rerunning FFmpeg. Focused real-image and FFmpeg crash injection passed before the full **627-test** unit gate; workspace Ruff, production-package mypy, exercise structural lint and `git diff --check` passed.
- Durable-stage scheduler slice: all adaptive CLI stages now use run-bound SQLite recipes over effective content/model/render inputs. Tests cover unchanged skips, missing-output repair, content-bound output adoption, report provenance, recipe invalidation, nested stage/device fencing, expired-worker reclaim, stale-worker rejection, three-failure circuits and force retry. A live approved-Snoozer render registered its existing verified master without FFmpeg, and the next invocation skipped. Full closeout passed **635 unit tests**, workspace Ruff, production-package mypy for 14 files, exercise structural lint for 35 files/35 links and `git diff --check`.
- F2–F6 reliability closeout: browser, clipboard, Audacity and encoder entrypoints share fenced leases; browser/Audacity cleanup is limited to proven owned processes; final FFmpeg stderr reads are bounded; changed stage recipes archive mutable downstream activations and preserve immutable accepted bytes; writing, source-audio and thumbnail publications recover from content-bound journals. Crash injection includes real child-process death and restart reconciliation. Full closeout passed **651 unit tests**; workspace Ruff, production-package mypy, exercise structural lint and `git diff --check` are the required PR gates.
- PR #21 CI follow-up: the Windows runner's FFmpeg 9 rejected deprecated `-filter_complex_script` in the real render test. Both render paths now use `-/filter_complex`, with the same file-backed graph. The local 651-test suite and the subsequent Windows CI lint/unit job passed on commit `eae1434`.
- Professor local-narration checkpoint: the owner archive's Schulte-challenge WAV was matched to the prepared script without modifying historical files. A separate ignored pilot run imports 0–76.55 seconds, source-hash-bound and ending in the pause after the last spoken word. Faster-Whisper produced four canonical spans and 2,296 frames; timeline/audio endpoint difference is 30 ms. The original published-caption selection remains 0–69.08 seconds and untouched. The user reports CapCut edits on many Professor uploads, so the archived WAV is not asserted to be identical to the published narration. An actual recipe recut exposed a scheduler defect: stage adoption used the completion result from before invalidation. The CLI now revalidates completion after archiving; a regression test covers the source-audio recut. The archived storyboard documents the repeated white-background mascot/neon-grid language that the new shot plan must avoid. **652 unit tests**, workspace Ruff, production-package mypy (15 files) and `git diff --check` passed. Live planner invocation is awaiting authorization to send this script and brief to Gemini.
