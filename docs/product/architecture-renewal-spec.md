Status note — 2026-10-26: [#31](https://github.com/Snoozer10/local-youtube-automation/issues/31) remains the renewal parent. #36 guidance and #23/#24–#30 compilation are integrated; PR #53 delivered the navigation batch, while #37 stays open. #32–#35 policy decisions are closed. See the existing [roadmap reconciliation](architecture-renewal-plan.md#reconciliation--2026-10-26) for remaining #37–#50 work, native dependencies and uncovered Track A lifecycle requirements. This local status amendment does not publish a new spec or alter the tracker’s historical parent body.

## Problem Statement

Project changes are difficult to make safely because guidance, workflow rules, skills, error knowledge, and documentation have unclear or conflicting ownership. Cleanup is risky: local runtime state and other generated or historical material may contain resumable production state and evidence, while static searches alone cannot prove that code or assets are unused.

The multi-channel feature exposed another gap. The project needs a reliable way to study a reference channel and create reusable Channel DNA without confusing observed traits with owner preferences or episode-specific decisions. Evidence requirements, profile versioning, activation behavior, and integration with existing pipeline contracts need a clear specification.

## Solution

Improve the existing local Windows Python application in reviewable phases. First reconcile project guidance and documentation ownership, then improve error records and skill discovery, and classify cleanup candidates before changing or removing anything. Preserve production state, evidence, existing stage contracts, and operator controls.

Then use a bounded Channel DNA workflow as the first feature-level architecture test. A named REA evidence-collection adapter is required for the agreed pilot, paired with appropriate transcript, video/frame, audio, and semantic analysis. The reference study preserves observations and uncertainty. A derived production profile applies owner preferences and validated requirements. Valid profiles apply automatically to new episodes; existing and running episodes remain pinned unless explicitly migrated. Incomplete studies are retained with actionable gaps.

## User Stories

1. As a project maintainer, I want one concise shared guidance contract, so that agents can find authoritative project-wide rules quickly.
2. As an agent using a specific tool platform, I want platform guidance limited to its actual differences, so that it does not conflict with shared project rules.
3. As a maintainer changing guidance ownership, I want an atomic authority migration, so that old and new rules do not compete during transition.
4. As a contributor, I want a clear documentation index, so that I can find the product, architecture, workflow, and session records relevant to my task.
5. As a maintainer, I want existing product documentation and architecture decisions reconciled, so that the project does not accumulate competing root documents.
6. As an agent working in a stable domain, I want scoped instructions near that domain, so that local constraints are easy to find and maintained by the right owner.
7. As a maintainer, I want child instruction manifests created only for durable boundaries, so that instruction hierarchy stays useful instead of growing mechanically.
8. As an agent diagnosing a recurring error, I want a concise searchable error index and consistent case records, so that I can find prior evidence and fixes.
9. As a maintainer, I want error cases grouped into a small number of failure domains when useful, so that the knowledge base can grow without a folder for every format or symptom.
10. As an agent recording an error, I want each case to link to preserved raw evidence and distinguish verified facts from hypotheses, so that later work can reproduce the diagnosis.
11. As an agent, I want error records to identify the closest applicable instructions, so that local debugging rules remain clear.
12. As an agent looking for a skill, I want a canonical source and verified platform discovery paths, so that I can invoke the maintained skill reliably.
13. As a maintainer, I want skill copies checked against bindings and dependencies before archiving, so that active workflows are not silently broken.
14. As a maintainer, I want actual skill discovery checked in fresh sessions, so that configuration claims reflect what agents can use.
15. As an operator, I want local runtime state classified by purpose, ownership, retention, and resumability, so that cleanup preserves useful production state.
16. As a maintainer, I want suspected dead code and assets checked against callers, dynamic loading, packaging, and runtime references, so that deletion decisions have evidence.
17. As an operator, I want obsolete production records retained or archived under an explicit policy, so that cleanup does not destroy audit evidence or recovery inputs.
18. As a maintainer, I want cleanup changes made in small reviewable batches with rollback evidence, so that regressions can be traced and reversed.
19. As a contributor, I want the existing Python package structure retained while boundaries improve where evidence identifies coupling, so that architectural work addresses real change friction.
20. As a maintainer, I want new workspace tooling considered only when independently built applications or packages justify it, so that the project does not adopt a monorepo build system without a need.
21. As an operator managing multiple channels, I want to start a reference-channel study from a channel URL and a bounded representative sample, so that the study reflects more than one video.
22. As an operator, I want a local-evidence path when remote sampling is unavailable, so that I can supply transcripts or media examples directly.
23. As an operator, I want the workflow to use a named REA evidence-collection adapter, so that REA’s supported observations can contribute evidence without being mistaken for a Channel DNA analyzer.
24. As an operator, I want transcript evidence used for narrative claims, sampled frames or clips for visual and motion claims, and audio evidence for sound-treatment claims, so that each conclusion rests on suitable material.
25. As an operator, I want observations linked to source examples or timestamps when available, so that I can inspect why a trait was recorded.
26. As an operator, I want reasoning, uncertainty and unknown traits recorded explicitly, so that missing evidence does not become invented channel behavior; no invented numerical confidence score substitutes for evidence.
27. As an operator, I want the reference study to preserve observed traits separately from my production profile, so that my preferences do not rewrite the source analysis.
28. As an operator, I want my explicit language, voice, brand preferences, and constraints applied to the derived production profile, so that production reflects my choices.
29. As an operator, I want the production profile to cover supported narrative, pacing, composition, motion, audio, title, and thumbnail traits, so that channel guidance can inform the whole workflow.
30. As an operator, I want a new immutable profile revision identity for each profile revision, so that content revisions remain distinguishable even when they share the same schema format version.
31. As an operator, I want the episode snapshot to pin both the profile revision identity and its content digest, so that the exact profile used by an episode can be verified later.
32. As an operator, I want mandatory profile fields and evidence validated before automatic activation, so that new episodes do not use unsupported or incomplete guidance.
33. As an operator, I want incomplete studies preserved with actionable evidence gaps, so that I can resume research without losing collected material.
34. As an operator, I want unsupported optional traits to stay unknown and local media analysis to avoid unnecessary provider work, so that the system neither invents traits nor creates avoidable external work.
35. As an operator, I want a validated inferred profile to apply automatically to new episodes, so that routine study does not require a separate approval gate.
36. As an operator, I want existing and running episodes pinned to their original profile revision, so that profile changes do not invalidate their plans, assets, scripts, or approvals.
37. As an operator, I want migration of existing episodes to a new profile revision to be explicit, so that production state cannot change silently.
38. As an operator, I want episode-specific visual strategy kept separate from stable Channel DNA, so that each episode can have its own hook, beat map, visual modes, and motion choices.
39. As an operator, I want the workflow to reuse existing jobs, recipes, checkpoints, invalidation rules, and publication controls, so that Channel DNA fits the current pipeline contracts.
40. As an operator, I want each affected stage’s inputs, outputs, owner, idempotency, retry, invalidation, and recovery behavior recorded, so that I can understand and resume interrupted work.
41. As an operator, I want incomplete evidence, failed stages, and resumable work to remain inspectable, so that I can recover from interrupted local runs.
42. As an operator, I want a successful bounded live Windows REA integration test before Channel DNA implementation is considered complete, so that the adapter is proven in the target environment.
43. As a maintainer, I want baseline measures captured before scoped changes and compared afterward, so that improvements can be assessed without inventing targets.
44. As an operator, I want provider, browser, editorial, preview, and publication gates preserved, so that architecture changes do not bypass existing controls.
45. As a maintainer, I want research and delegation proportional to uncertainty and risk, so that unfamiliar or consequential choices receive evidence without burdening straightforward local changes.
46. As an operator, I want the application to remain local to Windows for one operator managing multiple channels, so that the design matches current deployment needs.

## Implementation Decisions

- Work in bounded batches, using the existing native dependency graph rather than treating this list as a serial gate. Shared authority is integrated; remaining documentation, error knowledge, skill discovery, safe classification, profile pins and local study work may proceed independently where ownership permits.
- Reconcile the audit and migration plan with current repository state before execution. The audit is a historical snapshot, not current proof.
- Establish one shared guidance authority and platform-specific adapters. Complete any authority switch atomically after migrating applicable rules and checking task routing.
- Keep domain rules near the domain they govern. Add scoped instructions only for stable ownership boundaries.
- Use a shallow error-knowledge structure with a searchable index, consistent case records, and preserved source evidence.
- Establish canonical skill sources and verify actual discovery, bindings, and dependencies before archiving copies.
- Classify local runtime state, code, assets, and documents before deletion. Record evidence, retention needs, and rollback paths for removal candidates.
- Retain the current Python application and improve boundaries based on demonstrated change friction. Do not introduce Turborepo or a new monorepo build system without independently built applications or packages that justify it.
- Use REA as the named evidence-collection adapter for capabilities supported by its documented behavior. Pair it with separate media and semantic analysis for traits REA does not establish.
- Define the reference study as a record of observations and supporting evidence. Derive the production profile from that study plus explicit owner settings; owner settings affect the derived profile and never rewrite reference observations.
- Distinguish immutable profile revision identity from schema format version. Pin both the revision identity and content digest into each episode snapshot, reusing existing snapshot and rebind behavior.
- Implement and persist the settled [sample policy #34](https://github.com/Snoozer10/local-youtube-automation/issues/34#issuecomment-6393651666) and [mandatory-evidence/activation contract #35](https://github.com/Snoozer10/local-youtube-automation/issues/35#issuecomment-6393849575), including pass/partial/fail cases. #33 selects REA passive page observation as the pilot candidate; successful live Windows collection is still required separately.
- Validate mandatory profile content and evidence before automatic activation. Preserve incomplete studies and actionable gaps; leave unsupported optional traits unknown. Use local media analysis where suitable to avoid unnecessary provider work.
- Apply valid inferred profiles automatically to new episodes. Existing and running episodes retain their original profile revision unless explicitly migrated.
- Keep stable Channel DNA separate from each episode’s content-specific visual strategy.
- Map stage contracts onto existing jobs, recipes, checkpoints, invalidation, and publication controls. Record stage inputs, outputs, owner, idempotency, retry, invalidation, and recovery contracts using existing mechanisms; add no universal workflow framework.
- Before scoped changes, capture relevant baseline measures such as task routing, documentation link validity, skill discovery, stage recovery behavior, and bounded workflow outcomes. Compare afterward without setting unsupported improvement targets.
- Keep the application local to Windows and single-operator use.
- Respect current architecture decisions and ongoing work. The unified Video Compilation Engine and related issue scope remain under their existing decisions and issues; do not duplicate or redefine them here.

## Testing Decisions

- Prefer tests at the highest existing public boundary that proves user-visible behavior: profile validation and activation through episode-brief compilation.
- Good tests assert observable results and preserved invariants, not internal helper calls or module layout.
- Use deterministic evidence fixtures and fake REA and media adapters for repeatable offline tests.
- Cover valid profile activation for new episodes, partial-study retention without activation, owner settings in the derived profile, preservation of reference observations, revision and digest pinning, and existing or running episode pinning.
- Cover episode-specific strategy compilation and verify that profile updates do not silently alter already materialized episode work.
- Cover missing mandatory provenance, mismatched profile digests, interrupted studies, and recovery. These cases must preserve evidence and must not activate an incomplete profile.
- Exercise error records, routing, skill discovery, cleanup classifications, and stage contracts with focused checks for links, ownership, references, and retention.
- Before Channel DNA implementation is considered complete, run a bounded live Windows REA evidence-collection test. Before the run, define the selected source and supported capability, maximum duration, sample and attempt bounds, and allowed origins.
- The live test must record the REA and runtime identity, preserve sanitized source-bound outputs and hashes, consume real REA evidence in a study, and validate meaningful output for the selected capability. Version/help output, mocked output, or a successful launch alone do not satisfy the gate. Failures preserve evidence and do not permit a completion claim.
- Do not require provider runs for every optional media modality. Keep unsupported optional traits unknown, while missing mandatory evidence prevents activation.
- Reuse existing production profile, brief compilation, pinning, invalidation, and publication-control tests as prior art. Do not duplicate the unified Video Compilation Engine test scope.

## Out of Scope

- Rewriting the application or changing its primary language or deployment model.
- Introducing hosted multi-user services.
- Adopting Turborepo or another workspace build system without an independently built application or package that needs it.
- Duplicating or reworking the already integrated compilation scope in #23 and #24–#30 without a separately accepted change. Reuse ADR 0006, current source contracts and the compilation closeout.
- Treating REA as a built-in YouTube, audio, visual, or Channel DNA semantic analyzer.
- Automatically migrating existing or running episodes to a new profile revision.
- Inventing missing evidence or requiring a routine human approval gate for otherwise valid inferred profiles.
- Deleting runtime state, evidence, code, assets, documentation, or skill copies based solely on age, location, or static search results.
- Expanding the work into unrelated production features or changing provider, editorial, preview, or publication gates.

## Further Notes

- The user’s primary success measure is safer, faster feature changes through fewer regressions, clearer ownership, and faster diagnosis.
- Reconcile current guidance, task routing, and post-audit changes before implementation. Do not rely on historical audit counts as current measurements.
- Sample eligibility/bounds and mandatory fields/evidence are settled by #34/#35. Local studies follow those contracts; live Windows REA feasibility/usefulness remains #45 after #43, not a blocker on the local study.
- A live Windows REA test is a required completion gate for the Channel DNA implementation. Publishing this specification does not run REA, install dependencies, or authorize provider actions.
- The external modernization report and playbook informed the audit, but their historical branch and test claims are not current verification evidence.
- Profile activation is automatic only after required fields and evidence validate. Partial studies remain available for completion and do not activate.
- Compilation [#23](https://github.com/Snoozer10/local-youtube-automation/issues/23) and #24–#30 are CLOSED and integrated through PR #52; #36 guidance is CLOSED through PR #51. Reconcile current interfaces and ownership before further changes. Existing preservation, provider, editorial and publication controls remain in force. Track A’s accepted lifecycle policy is recorded in the roadmap crosswalk; its proposed mechanisms are not silently added to #40/#41 or this feature’s acceptance.
