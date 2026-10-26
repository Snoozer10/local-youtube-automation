# Architecture Renewal Interview

Status: SETTLED THROUGH Q23 for the architecture audit and plan. Future Channel DNA implementation remains pending its explicit pilot prerequisites; this record does not authorize code, cleanup, provider calls, or installation.

## Task and outcome

- Task ID: architecture-renewal-interview.
- Primary outcome: safer, faster feature changes, measured by fewer regressions, clearer ownership, and faster diagnosis.
- Change strategy: repair incrementally. A rewrite or stack change needs evidence that a named subsystem cannot be repaired economically.
- Concrete pain case: adding multi-channel mode so a supplied channel could be studied and turned into a reusable, advanced Channel DNA profile. Q22 settles REA as a capability-matched evidence-collection adapter; primary-source research is complete. Windows/runtime feasibility and the actual value of collected evidence remain future pilot proofs.

## Decisions from the interview

- Reusable channel profile: accepted as versioned and distinct from the plan for one episode.
- Profile contents: distinguish observed evidence, inferred traits, and owner preferences.
- Evidence input: use a bounded sample of representative videos from the channel URL; owner-provided local examples may be included.
- Profile use: apply inferred profiles automatically. The user rejected requiring human approval before a profile is used.
- Profile revision scope: a new profile applies to new episodes only. Existing and running episodes stay pinned unless explicitly migrated.
- Change sequence: consolidate guidance and document ownership first, then use the Channel DNA workflow to improve code boundaries.
- Disposables: classify and verify each item before action; preserve evidence and resumable state. Define .runtime retention rules and verify references from code, assets, and docs before archive or deletion.
- Shared instructions: one concise AGENTS.md contract and routing layer; GEMINI.md and CLAUDE.md hold only platform-specific adapters; domain-specific rules remain local; HANDOFF.md holds session state.
- Error knowledge: use local error-domain AGENTS/index files and individual cases with a consistent template and raw-evidence references. Add only shallow domains when needed; do not impose a deep format taxonomy.
- Skills: establish canonical skill sources with verified platform-specific discovery/configuration. Archive duplicate or unused skills only after checking active bindings and dependencies.
- Architecture (Q13): retain the current Python architecture and improve module boundaries. Consider a monorepo only if independently built applications or packages emerge.
- Documentation (Q14): reconcile existing product docs and ADRs through one navigation index, with root policy, local mechanisms, executable checks, and historical records.
- First deliverable (Q15): a reviewable audit and migration plan, not cleanup implementation. The reviewable audit and migration plan exists at docs/product/architecture-renewal-plan.md.
- No ADR is required now; lifecycle design remains planned, and no migration implementation has been adopted.
- Research and delegation (Q16): scale investigation and delegation to uncertainty, risk, cost, and expected value; preserve required research, ownership, verification, and authorization controls instead of applying blanket rules.
- Stage contracts (Q17): map checklist fields to existing durable jobs, recipes, checkpoints, and publication controls; add an abstraction only for a demonstrated gap.
- Advanced Channel DNA (Q18): cover script structure, pacing, visual composition and motion, audio treatment, titles, and thumbnails. Tie traits to examples and timestamps, and record uncertainty.
- Reference-channel study (Q19): preserve evidence-backed observations and inferences about a reference channel separately from the target production profile. Owner language, voice, and brand preferences govern the derived production profile; they never rewrite reference observations. Q22 settles REA as an evidence-collection adapter where documented capability fits; remaining proof is about Windows/runtime feasibility and evidence value, not its selected role.
- Evidence modalities (Q20): use evidence appropriate to each modality; mark traits unknown when the source or modality cannot support a claim.
- Operating target (Q21): local Windows production with one operator managing multiple channels; hosted multi-user operation is out of scope.
- REA role (Q22): use REA as a named evidence-collection adapter where its documented capabilities fit, with separate transcript, video/frame, audio, and semantic analysis components as needed. Keep the Python architecture; Node is an optional tool dependency, not a stack migration.
- Profile activation (Q23): automatically activate a new profile for new episodes only after its mandatory fields and evidence are validated, preserving explicit owner settings. Optional unsupported traits remain unknown. If mandatory evidence is missing, save a partial study with actionable gaps and do not invent values; there is no routine human profile-approval gate. Existing/running episodes stay pinned unless explicitly migrated.

## External proposal review for the audit

- Reviewed the archived assessment report (SHA-256 7369e08a2b8f5057274578d43092743be2ad7d0439a1bb5793af3ba6946ae3b4) and playbook (SHA-256 1e72f8b517a64b23d58f3ae8bd75e5182a6478d47b0639125b2ecd8060fe7407). Exact bytes remain under .runtime/architecture_renewal_audit_20261023; originals were not edited.
- Accepted direction: incremental modular Python, owner-scoped guidance, classify before pruning, and one bounded Channel DNA pilot.
- Modified: treat M01–M16 as a reference menu, not 16 mandatory phases; map stage fields onto existing job/recipe/checkpoint/publication controls; add abstractions only for proven gaps. Use an existing task/HANDOFF owner, not parallel status registers. Keep error records minimal with optional richer metadata; add domain manifests only when rules differ.
- Deferred: cleanup, retention/deletion, package or stack changes, provider runs, and detailed migration until evidence and acceptance are complete.
- Naming: docs/index.md versus docs/README.md is unresolved naming, not an architectural decision. A separate architecture.md is optional only if it uniquely owns component/data-flow reference content extracted from existing guidance.
- Snapshot caution: proposals describe feature branch/HEAD 738ee77; the current repository is master at c774383. Their test counts are historical claims, not current validation. Do not reopen repaired packaging or quota-recovery findings without new evidence.

## Verified repository evidence
- Root AGENTS.md was 36,101 bytes in the initial inventory snapshot; it is 36,465 bytes after the coordinator added the renewal-preference pointer and glossary ownership. INVENTORY.json remains the historical snapshot and was not rewritten.

- AGENTS.md is 36,101 bytes; GEMINI.md is 47,171 bytes. Project guidance says GEMINI.md is current where it differs from older AGENTS.md.
- tools/AGENTS.md exists and owns QA utilities and manual diagnostics.
- docs/product/product.md exists (3,098 bytes). It describes a broad autonomous pipeline and a numbered phase map, while current GEMINI.md describes an opt-in adaptive channel workflow with a content-bound episode visual strategy. Reconcile its currentness before treating the product document as authoritative; do not create another PRODUCT.md meanwhile.
- docs/error-solving/understood-errors.md is 335 lines and 63,366 bytes. Its growth motivates a future retrieval and ownership review; the interview selected shallow local error domains, manifests/indexes, and evidence-linked cases, but authorizes no file migration.
- docs/sessions/HANDOFF.md points to .runtime/codex_release_451_20261023/ and other receipt directories for release and merge evidence. .runtime therefore contains referenced operational records; inventory and reference checks must determine dispositions before any archival or deletion.
- Root GEMINI.md names the episode visual strategy as source-specific and distinct from the saved channel profile. Coordinator code readback: Channel in src/youtube_automation/production/contracts.py:54 has schema versions 1–3; do not equate that schema version with immutable profile revision history. The Channel/profile contract in contracts.py:217–238 carries the channel and profile_sha256. ensure_brief in briefs.py:293–366 snapshots the profile hash, compares a supplied channel fingerprint, and rejects changed inputs when downstream artifacts exist. Preserve these guards when designing profile lifecycle behavior. compile_episode_visual_strategy in briefs.py:250–290 takes a Channel and episode inputs and produces an EpisodeVisualStrategy without changing channel identity. A bounded search found no reverse-engineering path; that is not proof none exists.
- Existing vocabulary in root CONTEXT.md mainly covers legacy timeline/image-generation terms. Preserve it during this interview; do not silently redefine its terms.

## Design direction (not implementation authorization)

- Keep the existing Python stack and repair incrementally. No monorepo, Turborepo, package split, runtime replacement, or project-wide rewrite is selected.
- No cleanup is authorized yet: do not delete .runtime, code, assets, documents, skills, agent instructions, or error records based on this interview.
- Apply new profile revisions only to new episodes. Keep existing and running episodes pinned unless explicitly migrated.
- Consolidate guidance and document ownership first, then use the bounded Channel DNA workflow to improve code boundaries.
- Build a disposition inventory before cleanup. Verify runtime references and preserve evidence and resumable state; retention and archive rules still need concrete classification.
- Use one concise shared AGENTS.md contract and routing layer, with thin platform adapters in GEMINI.md and CLAUDE.md, local domain rules, and HANDOFF.md for session state.
- Organize error guidance around shallow domains, local manifests/indexes, and individual evidence-linked cases with a shared template. Grow domains only when actual retrieval needs justify them; do not add a deep format taxonomy.
- Bind canonical skill sources to verified platform-specific discovery/configuration. Archive duplicates or unused skills only after checking bindings and dependencies.
- These are selected design directions only. They do not authorize edits, cleanup, archival, or implementation. No ADR is required now; revisit only if the audit identifies a consequential, hard-to-reverse trade-off with real alternatives.

## Prerequisites for a future Channel DNA pilot
- Set a bounded, representative sample count and video-selection rule; these are not chosen by this audit.
- Define the mandatory profile-field schema, evidence binding, validation rules, and activation behavior before implementation.
- Demonstrate the selected REA release/runtime on the target Windows setup, including browser ownership, lease, and origin constraints, and measure whether its web evidence plus suitable media evidence is useful on the chosen sample. Source research is complete but is not a Windows or evidence-value proof.
- Use specified local channel/video inputs and obtain any required access or provider grants through a separate authorized task.
- Add isolated multi-channel and episode-pinning checks; preserve partial studies and actionable evidence gaps when required evidence is absent.

## Research receipt — 2026-10-23 UTC

- [Turborepo documentation](https://turborepo.dev/docs): describes Turborepo as a JavaScript/TypeScript monorepo build system with task scheduling and caching. This establishes its stated target, not fit for this Python project; no adoption decision follows.
- [Diátaxis: How to use Diátaxis](https://diataxis.fr/how-to-use-diataxis/): recommends iterative improvements and using the framework as a guide, and warns against creating empty documentation structures. It supports incremental documentation repair, not a mandate to restructure this repository into empty categories.
- [REA repository](https://github.com/morluto/rea), checked read-only on 2026-10-23 UTC: its overview describes an MCP for reverse engineering applications, websites, and binaries, with evidence and limitations. Q22 selects it as a capability-matched evidence-collection adapter, not as a built-in channel-video semantic analyzer. No installed dependency or release has been selected and no installation or live run occurred; source blob SHAs are pinned in REA_RESEARCH.json.
- Completed primary-source receipt .runtime/architecture_renewal_audit_20261023/REA_RESEARCH.json records README, package metadata, browser-observation.md, and pinned source blob SHAs. Reviewed package rea-agents 6.7.0 declares Node ^22.19.0 || ^24.11.0 || >=26.0.0; browser observation documents passive CDP evidence such as DOM, scripts, network data, and screenshots, not built-in channel-video semantic analysis. A selected Windows/runtime path and useful evidence yield still require bounded future proofs.

## Resume

The architecture audit and migration plan is now reviewable; implementation remains pending. Any later Channel DNA pilot must first resolve the prerequisites above in a separately scoped task. No code, cleanup, installation, provider action, or migration is authorized by this interview record.
