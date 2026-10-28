# Project documentation map

This page routes readers to current project owners. The map is navigation only. Binding rules remain in the applicable contracts; issue state and evidence receipts establish task progress. Historical plans and reports do not override current contracts.

## Start here

| Reader question | Route | Owner and status |
|---|---|---|
| How do I run legacy or adaptive production? | [Project README](../README.md), its existing quick start and commands; [adaptive staged workflow](../tasks/adaptive-visual-usage.md). | README is the project front door. The task guide is operational and dated; follow its current gates and verify status before production use. |
| Which rules govern a Python or wrapper change? | [Shared project contract](../AGENTS.md) → [engineering routes](agents/workflows.md) → [source ownership](../src/youtube_automation/AGENTS.md) → the nearest domain contract. For production, use [production contract](../src/youtube_automation/production/AGENTS.md). | Root owns shared rules; scoped contracts own their subtree. The root facades have documented CLI and monkeypatch compatibility obligations. |
| What is implemented architecture and what is proposed renewal? | [Current compilation decision, ADR 0006](adr/0006-unified-video-compilation-engine.md); [renewal plan](product/architecture-renewal-plan.md); [renewal issue #31](https://github.com/Snoozer10/local-youtube-automation/issues/31). | ADR 0006 records integrated compilation. The plan’s dated audit is historical; its [2026-10-26 reconciliation](product/architecture-renewal-plan.md#reconciliation--2026-10-26) identifies integrated work, remaining tickets and accepted policy separately from proposals. The 2026-10-26 reconciliation is committed to the integration tree. |
| Where are timeline and span terms defined? | [Shared glossary](../GLOSSARY.md) → [transition vocabulary](../CONTEXT.md). | GLOSSARY owns current shared terms. CONTEXT remains for synchronization terms not yet migrated. ADR 0005 refers to audio_chain, which the current CONTEXT does not define. |
| Where do I resume work without repeating attempts? | Read [HANDOFF](sessions/HANDOFF.md) and the [applicable branch execution record](../tasks/BRANCH_COMPLETION_MASTER.md) to identify your actual current task issue. Refresh that issue's scope and status, then follow its named receipt or attempt. | HANDOFF is the resume cursor; the branch record owns execution order where applicable; the tracker owns task completion. [Navigation maintenance #37](https://github.com/Snoozer10/local-youtube-automation/issues/37) maintains this map. |
| What may be archived? | [Runtime retention issue #40](https://github.com/Snoozer10/local-youtube-automation/issues/40) and the [shared preservation contract](../AGENTS.md). | #40 owns runtime retention classification and reversible archiving. Unknown, referenced, rejected, resumable and recovery-bound material remains preserved. A disposition is not permission to move, archive or delete. |

For diagnosis, use [engineering workflows](agents/workflows.md) and the [error register](error-solving/understood-errors.md); old case advice needs current-contract verification. Task skill selection belongs to [branch task bindings](../tasks/BRANCH_TASK_SKILLS.md), with provenance in [skill-lock.json](../skill-lock.json). Both prompt trees and root launchers remain supported distribution surfaces.

## Document status and disposition

Keep, update and archive describe the document's disposition. They do not authorize a filesystem action. Deferred execution is stated separately. No archive candidate is approved by this map.

| Document or material | Disposition | Status, owner and deferred work |
|---|---|---|
| Root and scoped AGENTS.md contracts; docs/agents/workflows.md | Keep | Current binding or operational guidance. Update only through the owning contract workflow. |
| GLOSSARY.md and CONTEXT.md | Keep | Current glossary plus a documented transition vocabulary. Term-by-term migration is deferred; preserve existing paths and consumers. |
| [Product overview](product/product.md) | Update | Product documentation, under the root owner. Its completed-run section is historical evidence, not current production status; an in-place amendment is deferred. |
| [Renewal plan](product/architecture-renewal-plan.md) and [specification](product/architecture-renewal-spec.md) | Keep | Renewal coordinator. The renewal plan and specification distinguish integrated guidance/compilation/navigation from remaining work and settled decisions; the original audit stays dated. |
| [Project workflow](Project-workflow.md) | Update | Root-owned workflow record with historical run/test results and positive .docs/ evidence references. In-place status amendments are deferred. |
| [ADR 0005](adr/0005-audio-dsp-contract.md) | Keep | Source/audio decision owner. Operational clauses amended on 2026-10-28 (recovery data preservation, Windows pipe framing, channel voice/null-voice gating). Decision history preserved. |
| [ADR 0006](adr/0006-unified-video-compilation-engine.md) and [compilation closeout](sessions/SPEC23_COMPILATION_COMPLETION_20261026.md) | Keep | Source/video and root session owners. Compilation is integrated; closeout measurements are dated evidence, not live or editorial approval. Referenced .runtime receipts are local evidence, not bundled public files. |
| Track A and Track B decision packages | Keep | Local-only planning evidence at docs/sessions/ARCHITECTURE_TRACK_A_DECISIONS.md and docs/sessions/ARCHITECTURE_TRACK_B_DECISIONS.md. These files are untracked in the current checkout and are not public routes. Track A accepts policy boundaries; its implementation mechanisms remain proposals. Neither package is required to follow the public routes. |
| Closed Channel DNA decision map and decisions | Keep | Verified published resolutions: [map #32](https://github.com/Snoozer10/local-youtube-automation/issues/32), [REA #33](https://github.com/Snoozer10/local-youtube-automation/issues/33), [sample #34 resolution](https://github.com/Snoozer10/local-youtube-automation/issues/34#issuecomment-6393651666), [profile evidence #35 resolution](https://github.com/Snoozer10/local-youtube-automation/issues/35#issuecomment-6393849575). Live Windows REA qualification remains future implementation work. |
| .docs/ reports and session attempts | Keep | Supporting historical evidence. Follow its documented consumers; old measurements do not establish current behavior. |
| Suspected runtime caches, scratch files, legacy code or assets | Keep | No cohort is classified obsolete by age or search count here. Classification and any later archive/retirement execution belong to #40 or #41 after their evidence gates. |

## Conflicts to read carefully

ADR 0005 contained operational directions that conflicted with current contracts. These clauses were formally amended in-place on 2026-10-28 to preserve recovery data, require Windows command + CRLF + NUL pipe framing, and recognize channel-specific voices including null-voice TTS gating. Follow the current [root contract](../AGENTS.md), [source contract](../src/youtube_automation/AGENTS.md), [production contract](../src/youtube_automation/production/AGENTS.md) and [channel policy](../channels/AGENTS.md) for operations. The missing audio_chain glossary term remains an explicit unresolved documentation gap, not a reason to invent or silently migrate the term.

Issue #31 retains its historical publication body. The locally amended renewal plan/specification now route to the current reconciliation; their retained audit findings are dated. Shared guidance and compilation are integrated. Accepted REA capability, sample and evidence decisions are published in issues #32–#35. Track A/B remain local-only sources, not published decision links.

## Preservation and execution

Disposition does not itself change files. Runtime retention and any code retirement require their own reference, ownership, recovery and acceptance checks. #40 is the runtime retention task; [#41](https://github.com/Snoozer10/local-youtube-automation/issues/41) is for one proven obsolete non-runtime cohort. Track A's SQLite coordination/recovery implementation is not part of either task by implication and remains integration work under #31.

This map is maintained under navigation issue #37. PR #53 integrated the initial map and resume route; its default-branch URL was verified after merge. This map is maintained under navigation issue #37. PR #53 integrated the initial map and resume route; subsequent updates are committed and verified against the integration branch.
