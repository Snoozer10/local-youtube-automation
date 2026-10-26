# Spec #23 compilation repair - 26 October 2026

## Disposition

The seven distinct defects from the earlier audit are repaired locally. Additional review guards reject input/output aliases, nonzero or gapped timelines, unsupported targets and 29.97 fps for a declared 30 fps target. This is a repair result, not a declaration that all of Spec #23 is complete.

Parent #23 remains open. Story 16 still requires an atomic JSON verification receipt for every final compiled artifact; direct compilation currently returns CompilationResult and clip receipts. That requirement was not implemented or waived in this pass. Tickets #25-#29 remain open pending integration and the explicit remaining disposition. No push, PR, release, provider, GUI or production episode run was performed.

The local commit includes Antigravity's previously uncommitted compilation delivery and the reviewed repairs. Unrelated dirty work is excluded. See Git history for the commit and the repair evidence CLOSEOUT.json for its exact identity.

## Repairs

| Boundary | Result |
|---|---|
| Audio and timeline | Validate finite canonical audio duration against contiguous spans beginning at frame 0; independently validate encoded audio/video/container durations. Removed silent shortest-stream truncation. |
| Output safety | Reject resolved and hard-link aliases of narration, image and subtitle inputs. Verify pending output before atomic replacement under the publication fence; retain prior output and rejected candidates. |
| Target | Check decoded dimensions, FPS with numerical conversion tolerance, frame count, yuv420p/tv and required audio. QSV upload surfaces remain nv12. |
| Encoder ownership | Compilation and standalone detection acquire or verify/reuse the existing fenced resource claim; stale or foreign-domain claims fail closed. Publication transactions do not span FFmpeg. |
| Fallback and resume | Retain hardware evidence and isolate CPU generations. A validated production override and execution validator can resume matching CPU work across equivalent rendition profiles. Mismatched recipe, target, evidence or provenance cannot satisfy reuse. |
| Subtitles | Copy external ASS bytes unchanged; apply episode-global timestamps within the shared filtergraph, then restore local timestamps. Hash subtitle contents. The legacy adapter prefers external ASS over duplicate automatic dialogue; explicit public layers remain supported. |
| Approval lineage | The renderer fingerprint includes the new engine, filtergraph, subtitle, Ken Burns, journal, runner and schema dependencies along with existing encoder and production dependencies. Rendering changes invalidate current recipe/approval identity. |

## Verification

- Full command: venv/Scripts/python.exe -m pytest tests/ -q --tb=short -x
- Result: **2,101 passed, 9 skipped**, no failures.
- venv/Scripts/python.exe -m mypy --strict src/: passed, 77 source files.
- venv/Scripts/python.exe -m ruff check .: passed.
- venv/Scripts/python.exe -m build --no-isolation --sdist --wheel: passed; wheel/sdist version 4.5.1. Existing setuptools license metadata deprecation warnings remain.
- The final packet compared 609 source, test, fixture, configuration and documentation inputs before/after execution: no drift.
- Focused evidence includes 71 core cases, 48 subtitle/CLI/journal cases, public production cache/corruption/orphan cases, and renderer lineage cases. Earlier overlapping checks are not added together as a new suite count.

## Native evidence and review

The bounded synthetic CPU proofs used isolated resource databases and disposable media. They established two-second narration preservation, 60 frames at 320x180/30 fps, decoded yuv420p/tv, subtitle visibility on both sides of a one-second cut, unchanged clip reuse and subtitle-content invalidation. Coordinator inspection confirmed readable CHANGED CAPTION at 0.8 and 1.2 seconds.

The later two-request cache canary injected hardware failure before any GPU subprocess. The equivalent master reused both CPU clips and ran only final assembly; preview/master hashes matched. Actual GPU readiness and production/editorial acceptance were not tested.

Independent Standards and Spec reviews cleared the initial frozen repair after their findings were fixed. A subsequent focused integration check exposed a cache-resume regression introduced by isolation. The executor corrected it; the coordinator reviewed the bounded candidate/provenance checks and verified public and native regressions before the final full packet.

One native parent wrapper returned a null OS exit-code property. Its passed child assertions, explicit child exit receipt, command results and completed process observation are preserved separately; the null property was not relabelled as OS-observed zero. The final full gate parent captured subprocess exit code 0.

## Evidence and session controls

Evidence root: .runtime/spec23_repair_20261026T035651Z/

- BASELINE.json and preimages/: original dirty delivery and exact pre-task bytes.
- IMPLEMENTATION_FREEZE_VERIFIED.json: final repaired source/test pins before full verification.
- verification-final/RESULT.json: final commands, return codes, metrics, hashes and no-drift result.
- engine/, subtitles/, lineage/: focused red/green results, byte reconstruction and fixture corrections.
- review-standards/, review-spec/: independent review findings and corrected boundary proofs.
- native/, native-final/, native-cache/: synthetic fixtures, decoded frames and native results.
- COORDINATOR_CACHE_REVIEW.json and COORDINATOR_VISUAL_READBACK.json: final delta and pixel readback.
- dox/: owning-contract archives and reconstruction receipts.
- GITHUB_REPAIR_UPDATES.json: final ticket comment readbacks after publication.
- CLOSEOUT.json: commit, final paths and disposition.

The first final focused packet stopped on a dishonest 4s timeline/3s fake audio fixture. Other test fixtures used decoded nv12 or selected a retained hardware graph as the active CPU graph. Those fixtures were corrected without relaxing production checks. The discovered cache-resume regression was fixed rather than weakening the no-reencode assertion.

Two implementation workers ended with harness HTTP 429 errors after saving their work. The coordinator verified the saved results and completed local checks without further worker dispatches. The supported account display still allowed ordinary usage; no per-worker quota was inferred.

Root AGENTS.md and tests/AGENTS.md remain unchanged because routing and the verification framework are unchanged. The source and production owning contracts were updated. The earlier audit report and raw receipts remain historical evidence. QMD was left unchanged under the prior direction; current files were read directly.
