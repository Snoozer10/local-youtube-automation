# Project task skill setup — 16 October 2026

## Outcome
The user's simplified policy replaces the canceled task activation controller: keep relevant skills installed, archive unrelated project copies, and invoke named skills explicitly for each task.

- Canonical inventory: [root skill-lock.json](../../skill-lock.json).
- Invocation map: [BRANCH_TASK_SKILLS.md](../../tasks/BRANCH_TASK_SKILLS.md).
- Upstream installer provenance: [skills-lock.json](../../skills-lock.json). Its directory hashes have a different meaning from the curated lock's SKILL.md hashes.
- Evidence: [.runtime/codex_task_skills_20261015T225441Z/](../../.runtime/codex_task_skills_20261015T225441Z/).

## Installed and mapped
Two project-only copies were fetched with skills CLI 1.7.2: systematic-debugging and verification-before-completion, from obra/superpowers. Twenty-two suitable existing skills were reused. All 38 branch tasks and 14 workflow findings have explicit bindings to 24 selected skills; this is coverage of guidance, not proof that task acceptance has passed.

The installer used --ignore-scripts, explicit project scope, --agent codex --copy, and disabled telemetry. Source review and installation receipts are retained. No installed helper scripts were executed. Active SKILL.md files are pinned; supporting scripts/assets require their own review and pins before execution.

## Archived
Twenty project skill folders, containing 24 SKILL.md files and 289 regular files (4,087,787 bytes), were moved to [.agents/skill-archive/20261016/](../../.agents/skill-archive/20261016/). All 289 file hashes matched before/after movement; original source directories are absent. ARCHIVE_PLAN.json preserves the planned state; finalized root-lock rows now say archived. Restoration requires a deliberate reviewed change.

Folders: algorithmic-art, brand-guidelines, docx, pptx, xlsx, frontend-design, frontend-ui-engineering, slack-gif-creator, web-artifacts-builder, webapp-testing, playwright-automation-fill-in-form, ai-file-organizer, file-organizer, photo-slideshow, skill-creator, setup-matt-pocock-skills, setup-ts-deep-modules, obsidian-skills, hyperframes-video-composition, writing-beats.

## Invocation and limits
1. Read the task's scope and acceptance in the master.
2. Follow its task-skill link, announce selected skills, and read only their needed guidance.
3. Apply current user/project scope, two-strike brake, ownership and provider accounting before generic examples.
4. Verify the actual result; the coordinator alone updates shared status and evidence.

No automatic activation/deactivation mechanism remains. Current Codex 0.160.0 project exclusions did not suppress advertised skills in the isolated prompt-input check; TOML parsing is not enforcement proof. Global skill files and global settings are unchanged. Filesystem changes do not hot-unload this chat's advertised catalog, and global copies may still appear. Do not run bulk updates that silently restore archived packs.

The prototype controller and its tests/register are preserved under abandoned_activation_controller/ in the evidence directory, with failed/intermediate test logs. They are historical experiments, not accepted tooling. No native controller probes or model sessions were run.

## Verification
SIMPLE_SETUP_VERIFICATION.json records PASS: 110 active SKILL.md pins, 24 selected hashes, all 289 archive file hashes, 52 task bindings/anchors, and 274 local links. Master remains 38 tasks/six checked; its checkbox lines and root Pane block match preimages. Controller source/test/register are absent from active .codex. Independent review returned GO with one stale planned-to-archived correction, now applied.

No branch source/test changes, full suite, live Audacity, provider requests, Git commits or branch changes were performed in this setup. A4 remains gated; full software verification and conditional promotion remain open. Prior accepted narration and Professor ca8 acceptance are unaffected by these document/skill-only changes.

## Resume
Continue master F2 with systematic-debugging, test-guard and verification-before-completion; add the declared test-driven-development dependency when implementing a fix. Resolve checkpoint reliability using a concrete new hypothesis rather than repeating spent attempts.

## Evidence index
- INSTALLATION_RECEIPT.json — discovery/install provenance.
- CANDIDATE_FIT_REVIEW.json — suitability decisions.
- ARCHIVE_PLAN.json / ARCHIVE_RECEIPT.json — planned moves and exact file preservation.
- PLAN_CHANGE_RECEIPT.json — user simplification and canceled controller.
- ROOT_LOCK_FINAL_RECEIPT.json — finalized archive state and root-lock hash.
- SIMPLE_SETUP_VERIFICATION.json / FINAL_VERIFICATION_V2.json — accepted mechanical validation; FINAL_VERIFICATION.json retains the rejected case-sensitive assertion.
- FINAL_SEAL.json — final evidence manifest seal after logs close.

Final validation: FINAL_VERIFICATION_V2.json records PASS after correcting a case-sensitive filename assertion in the validator; the failed first receipt remains unchanged. Fresh QMD lexical lookup finds the exact task map; 205 unique hashes still need embeddings, so semantic freshness is not claimed. Latest observed weekly usage:50% under the60% ceiling. CONTINUITY intentionally unchanged: HANDOFF/master own this current cursor. The shaped doctor archive is not evidence of configuration enforcement.
