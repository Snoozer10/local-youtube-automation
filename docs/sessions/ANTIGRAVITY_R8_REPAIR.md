# Antigravity 2.0 — controlled R8 repair delegation

Copy this entire document into your user-owned Antigravity 2.0 session. This is one temporary delegation; the user starts/stops that session and returns its results to Codex for independent review.

## Task Capsule: professor-r8-local-repair

- **Worker**: Antigravity 2.0, acting as a delegated executor.
- **Workspace**: `C:/Users/Snoozer/Downloads/Antigravity/Youtube Automation 2/buckup/Version 4 before deepseek implementation plan/image_generation`
- **Branch / baseline HEAD**: `codex/adaptive-multi-channel-visual-engine` / `41d02eb`.
- **Goal**: Repair five rejected local graphic shots and the timer boundary, then return a reviewable working-tree diff and current rendered evidence.
- **Authority**: Local implementation, offline verification, diagnostic rendering and documentation only. Do not commit, stage, push, merge, switch branches, reset, stash or discard existing work. Codex owns the subsequent review.
- **Exclude**: H9/H10, Soldier, full episodes, TTS/audio changes, channel/profile changes, deployment/publication and unrelated refactors.
- **Provider boundary**: Do not open or operate pipeline Gemini, Flow, AI Studio or other provider services; do not send API/SDK requests or spend image-generation budget. No new provider critic is authorized here. Your own Antigravity reasoning session is permitted. Do not use Astra. Stop and return a blocker if local work cannot satisfy the scope.

## 1. Bootstrap and stop gates

1. Read `docs/sessions/HANDOFF.md`, this brief, root `AGENTS.md`, and `GEMINI.md` (current guidance wins where older guidance differs). Read every applicable child contract before editing: production, tests and tasks if touched. Check whether any additional contract exists along the target paths.
2. Capture initial Git status, `git log -n 5 --oneline`, `git diff --stat`, and the existing untracked files. This dirty tree contains prior work, including required untracked production modules/tests; do not treat it as disposable or omit those dependencies. Before editing each permitted file, save its exact-byte preimage and hash in the new attempt archive. Return your diff against those preimages as well as the overall Git diff; initially untracked files are not automatically your work.
3. Before any mutation, verify the fingerprints and byte hashes below against disk. Use the project `fingerprint` function for canonical plan fingerprints and SHA-256 of exact file bytes for byte hashes; they are different checks. Stop on drift or missing evidence. Never update expected hashes merely to pass a guard.
4. Use LeanCTX plain `ctx_shell` commands (without nested `rtk`), QMD precision slices for docs, Serena for symbols/surgical code edits, LCO for targeted context, and Codebase-Memory only for targeted `src/` call graphs. Do not auto-index the full repository. If a required tool is unavailable, report it rather than weakening the contract.
5. At two consecutive command/test failures, stop, explain both failures and request user direction. No third blind retry. Preserve failed outputs and receipts. Use a small number of workers only for independent bounded tasks; no worker may commit or overwrite another worker's changes.

## 2. Exact starting evidence

Run root: `youtube_runs/adaptive-pilot-professor-yashrah-local-narration/`.

| Artifact | Required baseline |
| --- | --- |
| `cue_repair_v13/candidate.json`, canonical raw AND typed fingerprints | `ed974d5e61e8e8eb929f5f04c87831305b5acc66e2810377c61978d995a07b9c` |
| `visual_inspection_ed974d5e61e8_r8/manifest.json`, file-byte SHA-256 | `0f4e2619bfc6022034c7aea4ef99672498fb5f53c299f119398710ea15095c4e` |
| Active `shot_plan.json`, canonical RAW fingerprint | `c307f6ce9289a3b3abb82a24160c139b2aceb8ee99ce067df95301fbdadacb13` |
| Active `shot_plan.json`, file-byte SHA-256 | `144e1aaba1774e860f336975ba89b12f3c773bf5eb68df9a402d016e994e6e2d` |
| Active original, current typed fingerprint (diagnostic only) | `d089197100db175a51ce78ab6b70cc14e6f5a546d247e87e18fe65de932bd411` |
| Archived `cue_repair_v13/history/r8_from_91baa7b66edf/candidate_r7.json`, file-byte SHA-256 | `1c644f7c0af78ccf4245d197618c3fe78196adae5cad92a8d4d5acc439aeca82` |
| Current failed timer proof `visual_inspection_ed974d5e61e8_r8/shot_21_15.png`, file-byte SHA-256 | `be616d7f043974fefeb5023597983e9333ebf0633abd402220bc3b7922a6cc96` |

- R8 manifest: renderer8, 21 ordered rows, 83 verified proof files, no missing shots; diagnostic and editorial-review-required flags are true.
- Saved state is `r8_proofs_awaiting_fresh_review`. No current visual audit, preview approval or publication is authorized.
- All 21 accepted base assets are preserved. Capture their paths, hashes, recipe/reference identities and dimensions, plus narration/timeline/brief hashes, as a before/after inventory.
- Original raw/typed difference is known: 22 geometry values across 11 `rule_reveal` overlays normalize x=.25→.09 and width=.5→.82. Preserve the original bytes; do not “repair” this by rewriting it.
- Prior R7 history and older `resume_feedback.json` are historical evidence, not approval for this candidate. Preserve them.
- Known-green baseline: 973 unit tests; 20 production mypy files; workspace Ruff; six-file syntax compilation; exercise lint; drills 36 passed/1 skipped. This is historical evidence to reverify after changes, not proof of visual acceptance.

## 3. Bounded implementation

You may edit `src/youtube_automation/production/render.py`, `pictograms.py`, `shots.py`, and `graphic_cues.py` only where needed for these repairs; targeted production tests/fixtures; local proof helpers; and a new archived/candidate repair attempt under this run. Owning-doc edits may only describe implemented contracts, version changes and verified evidence. Broader changes require returning a concrete blocker.

Acceptance policy is immutable for this delegation: do not edit `tasks/professor-visual-playbook.md`, prior human feedback, channel policy, score thresholds, budget limits or approval rules. Do not weaken tests/validators or rewrite expected baselines to make a failing result pass. Any necessary `GEMINI.md` or owning `AGENTS.md` update is limited to factual implementation/version documentation; existing acceptance constraints remain binding.

### A. Timer boundary — implement and verify first

- Start is global frame2254; shot21 starts2165, so start is local89. At30fps, global2284 is local119, exactly one second later.
- Current `timer_segments` already selects00:39 at local119. The proof helper correctly uses `select=eq(n,119)`.
- Fault: `render.py:_ass_time` rounds local119 to397 centiseconds (3.97s), later than that frame's PTS (3.9667s), so the saved frame still shows00:40.
- Evaluate the bounded fix: timer-only ASS segment begin/end quantization using integer floor `frame * 100 // fps`; leave generic overlay timestamp behavior unchanged. Verify supported frame rates and prevent gaps, overlaps or an early tick.
- Add a meaningful regression covering serialization into ASS timestamps, not merely `timer_segments` arithmetic. Verify actual FFmpeg pixels at start−1/start/start+1 and one-second−1/exact/+1. The one-second exact sample must show00:39; the frame before it must still show00:40.
- Preserve spoken countdown/“ابدأ” boundaries. Update renderer lineage/cache invalidation according to the current contract when output semantics change; do not disguise changed output as the old render recipe.

### B. Five graphics — preserve source meaning

| Shot | Exact ID | Required meaning / defect |
| --- | --- | --- |
| 2 | `p0_beat_2_curiosity` | Introduces a series of mental exercises. Replace premature “اختبار بعد اختبار” with source-bound exercise wording. |
| 4 | `p0_beat_3_promise__continuation` | Rejects meditation/breathing in favor of the narrated mental exercises; current document/list repeats shot2. |
| 6 | `p1_b2_fun_plus_intelligence` | Enjoyment plus mental challenge; current generic composition repeats earlier graphics. |
| 8 | `p1_b4_testing_confidence` | Invites testing the viewer's confidence together; use a distinct, relevant visual treatment. |
| 9 | `p1_b5_elevating_capacity` | Asks whether capacity can be raised; retain uncertainty, never portray proven before/after efficacy. |

- Read exact canonical narration and `tasks/professor-visual-playbook.md`. Before editing, draft five short rows: narration, proposed visual object/action, caption, layout/motion, and why each advances the sequence. Self-review them against the playbook.
- Different captions on the same generic document/list/pointer layout are insufficient. Build source-relevant local objects/compositions with deliberate progression and readable Arabic; comply with the existing visual palette, pictogram allowlist/count and repetition contracts. Any needed allowlist extension requires source implementation, tests and a DOX update.
- Do not invent brain mechanisms, arbitrary desk activity, new factual claims, new exercises, unsupported transformations or decorative telemetry.
- Candidate changes are limited to `overlays`, `viewer_takeaway` and `semantic_link` on these five shots. Preserve every shot ID/order, frame range, span IDs, narration excerpt, visible state, local composition mode, camera, asset ID/recipe, character IDs and reference dependencies.
- Accepted shots1/3/5/7/10–20 must retain their content. Renderer fixes may legitimately change their pixels; verify those effects rather than silently accepting them.
- Preserve shot7's corrected self-assessment, shot10's answer-free readiness grid and the immutable Schulte 6×6 numbers1–36 through shots11–21. No answer highlighting, changed numbers, early fixation/clock, or altered timing.

## 4. Archival, rendering and verification

- Archive exact R8 candidate/state/manifest/proofs and relevant helper/source version hashes before mutation. Keep the failed timer proof and existing R7 history immutable. Use a new repair-attempt record and output directory; never overwrite rejected evidence.
- Do not rerun `.runtime/repair_professor_cues.py prepare` or the old one-shot portrait repair. Do not rerun `.runtime/resume_professor_local_repair.py --apply-r8`: it expects the historical R7 parent and would not resume this R8 attempt. Inspect existing helper contracts before reusing them.
- Preserve default-field serialization compatibility: default full layout and null icon/clock fields must not alter legacy fingerprints; meaningful preview/icon/clock fields must remain serialized.
- Canonically rebind cue data before validation. Validate cue-only changes separately from content changes, preserve strict guards, and derive changed cue IDs from `after.shot_id`, not a stale loop variable.
- Validate the revised candidate and all asset receipts/bytes; confirm raw and typed fingerprints agree. Keep root `shot_plan.json`, active preview/master pointers, approval records, narration, timeline and user `runtime_state.json` unchanged.
- Render complete current evidence for all21 ordered shots into a new directory. Bind the manifest to the new candidate fingerprint and renderer/helper versions; verify every proof's exact bytes. Current evidence cannot be declared valid merely by copying/relabeling old proofs.
- Inspect every rendered shot against its narration, progression, continuity, readability and attractiveness. Include all countdown phases and timer samples; old R8 shot21_2–10 were uninspected. Duplicate-byte samples may share an inspection only when their hashes prove equality.
- Save a fresh local score table (all four dimensions1–5; acceptance requires all≥4), explicit accept/reject reasons, sample coverage, plan/renderer/manifest hashes and unresolved defects. Label it a local Antigravity review; do not fabricate Gemini/provider receipts or visual approval. Codex and human review remain pending.
- The prior `native_review.md` write failed twice with OS error3 despite an existing directory. Do not blindly retry that operation. Choose and document a diagnosed alternative local output path; preserve any partial file and put the fresh report in the new attempt directory.

Run these offline checks with terse output; keep exact commands, exit codes and summaries:

1. `python -m pytest -q --tb=short tests/unit/test_production_graphic_objects.py tests/unit/test_production_graphic_cues.py tests/unit/test_production_render.py tests/unit/test_semantic_failure_replay.py`.
2. Full unit suite once after the final edits: `python -m pytest tests/unit -q --tb=short`.
3. `python -m ruff check .`.
4. Production mypy from `src/`, with tool environment `MYPYPATH=.`: `python -m mypy --explicit-package-bases --namespace-packages --follow-imports=silent --no-incremental youtube_automation/production`.
5. `python tools/lint_exercises.py`; run the existing drill command if required by the applicable contract.
6. Syntax-check changed runtime helpers, replay relevant failure fixtures, and `git diff --check`. No repeated broad suites unless new edits/failures justify them.

## 5. Return to Codex; then stop

Write `docs/sessions/ANTIGRAVITY_R8_RESULT.md` and return its absolute path plus the following concise summary to the user:

- Final Git status and an inventory separating your changed paths from the preserved starting dirty tree; include preimage paths/hashes, your delta against them, new source/untracked dependencies and the overall patch/structural diff.
- New candidate fingerprint, renderer/cue/compiler versions, manifest byte hash, proof hashes, archive paths and before/after preservation checks.
- Exact tests/commands/exit codes; timer boundary regression and pixel results.
- All21-shot score table and coverage, remaining defects/blockers and any incomplete checks. Do not claim zero defects from green tests or artistic acceptance from schema validity.
- DOX changes; refresh HANDOFF/CONTINUITY from verified evidence. Keep HANDOFF under400 tokens and remove its stale claim that the missing old `native_review.md` exists.
- Clearly state: no commits/push/merge, provider spending, active-plan activation, approval or publication.

When the packet is saved, stop implementation and wait for the user. Do not start another pilot or broad cleanup. Codex will inspect your diff, independently verify the relevant gates and pixels, and decide the next bounded work only after the user returns your completion report.
