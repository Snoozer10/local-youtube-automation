# Handoff

## Current Phase
Spec #23 receipt completion verified locally; separate guidance and compilation PR integration is in progress.

## Done
- db2ad58 repaired the seven original audited compilation defects.
- Story 16 now prepares immutable hash-bound final-artifact JSON receipts before video publication; production reuse, approval and recovery require them.
- Independent review found and corrected pairwise audio/video drift beyond one frame; two RED public regressions are GREEN.
- Final frozen gates: 2,141 passed, 9 skipped; strict mypy 78 source files, Ruff, wheel/sdist build passed. All 597 pinned inputs unchanged.
- Two bounded native CPU requests passed through root CLI and production render_plan; tampered copies rejected, original pairs retained. No provider/browser/GPU/editorial acceptance exercised.
- Evidence/report: docs/sessions/SPEC23_COMPILATION_COMPLETION_20261026.md; .runtime/spec23_completion_20261026T061513Z/.

## Next
- Guidance PR #51 is merged (bc05960c); #36 is closed. Integrate the separately scoped compilation PR next.
- Confirm exact-head CI/review and integration before closing #25-#29 and parent #23. #24/#30 were already closed; #36 belongs to guidance PR #51.
- Preserve unrelated dirty files. No provider, GUI, REA, production media, release or cleanup grant exists.

## Failures & Fixes
- Two unchanged consumer-check failures after a CRLF anchor miss triggered the brake; user approved a bounded fixture correction. Preserve failed evidence.
- Repaired missing-receipt manual media/orphan fixtures via public FakeMediaRunner compilation, without weakening human rejection.
- Corrected fake media byte collisions, a native helper root-path error before dispatch, and fixture import ordering. Raw failures and preimages retained.

## Resume Context
Branch codex/spec23-compilation-completion; approved original review baseline 70213c1, completion baseline db2ad58. Final source pins: IMPLEMENTATION_FREEZE_PUBLICATION.json. Commit/PR and eventual merge identities are recorded in Git history, tracker and completion CLOSEOUT.json.

## Navigation batch #37, 2026-10-26

### Done
- Added the documentation map and bounded README/AGENTS routes. This batch does not amend core product/ADR bodies or complete #37.
- Focused candidate/checkout checks passed: six reader cases in each tree, links, preservation and isolated restoration; independent Standards and Spec reviews found no remaining blockers.
- Starting commit 23396894733239af6454041b8be4ae72c228f673 plus exact pre-task snapshots owns the review baseline. Accepted brief, source archives and raw checks are local-only at .runtime/architecture_renewal_audit_20261023/navigation37_20261026T125418Z/.

### Next
- Review the batch-only commit and remaining #37 core-document reconciliation. No merge, release, issue closure or follow-on ticket is authorized.
- Default-branch documentation availability remains pending authorized integration and a fresh public-link check. The candidate tree is the pre-integration verification target.

### Failures & Fixes
- Standards review caught CRLF checkout bytes causing full-file README churn in the first candidate. Path-aware Git clean conversion restored a minimal insertion; working bytes stayed unchanged. Keep the failed candidate and all attempt evidence.
- Preserve pre-task HANDOFF changes locally; the commit carries only this appended closeout over the starting committed HANDOFF. Earlier completion/integration text is historical; current integration facts remain in tracker/compilation closeout.

## Navigation PR amendment, 2026-10-26

### Done
- The resume route now discovers the reader's actual task issue through HANDOFF/applicable execution records. #37 is labelled navigation maintenance.

### Next
- Prepare the focused navigation PR after affected route/link/preservation checks and amendment review. No merge, release, #37 closure or database implementation is authorized.
- Verify the new documentation page on the published PR head; default-branch verification remains pending authorized integration.

### Failures & Fixes
- A generic resume route incorrectly linked #37 as every reader's current task. The amendment separates task discovery from navigation maintenance. Exact preimages and amendment evidence: .runtime/architecture_renewal_audit_20261023/navigation37_amend_20261026T134549Z/ (local-only).

## Architecture-Renewal Campaign Startup, 2026-10-27

### Done
- Established isolated campaign workspace at `C:\Users\Snoozer\teamwork_projects\architecture-renewal-campaign` on branch `codex/renewal-campaign` pinned to verified remote master `09b0b85e2b755a00f35ac2ad05f7fba1412c214d` (canonical tree `f39c6c4d32cc5a263245f8511e19d1aa0a207138`).
- Applied sparse-checkout projection (`SPARSE_CHECKOUT.txt`) excluding `.runtime/`, `runtime/`, `logs/`, `.env*`, etc. Confirmed 0 junctions/symlinks, local `.git` directory, and clean path boundaries.
- Created clean Python 3.11 virtual environment (`venv/`) with repo-declared dependencies. Recorded Python 3.11.9, SQLite 3.45.1.
- Executed isolated resource/preconnection tests (`test_production_publication_mutex.py` and `test_resource_isolation.py`): 7 passed, confirming production SQLite connection attempts fail closed immediately.
- Applied reviewed documentation patch `transfer/reviewed-documentation.patch` (`docs/README.md`, `docs/product/architecture-renewal-plan.md`, `docs/product/architecture-renewal-spec.md`) and verified blob hashes match expected targets.
- Installed approved campaign delegation exception in `docs/agents/workflows.md`, designating Antigravity Project Orchestrator as integration owner.

### Next
- Proceed with Milestone M1: dispatch Track 1 Worker W1 for #54 (Safe ledger failure reporting) and #55 (Windows observation method qualification).
- Dispatch Track 2 Worker W2 for unblocked #37 core-document reconciliation and #42 brief profile pinning.
- Maintain independent review gates (R1, R2) and exact head verification. Codex availability is not a routine milestone gate.

### Failures & Fixes
- `git apply --check` initially failed due to CRLF checkout formatting under Windows default `core.autocrlf=true`. Configured repository-local `core.autocrlf=false` and `core.eol=lf`, checked out native LF files, and re-ran `git apply --check` with 0 errors. Blob hashes match `OVERLAY_TARGETS.json` exactly.
- Pip dependency install experienced network timeout on large wheel metadata. Installed required test tools (`pytest`, `pytest-mock`, `pytest-cov`, `mypy`, `ruff`, `build`, `pydantic`, `psutil`, `python-dotenv`) with extended timeout and installed project in editable mode (`pip install -e . --no-deps`).

## Architecture-Renewal Campaign Milestone M1 Completion, 2026-10-27

### Done
- Milestone M1 completed across both parallel tracks (Track 1: #54 & #55; Track 2: #37 & #42).
- Track 1 (#54, commit `f2b3209`): Safe failure summaries and historical diagnostic display. Added `is_safe_operational_message` and `project_safe_message` in `src/youtube_automation/core/failure_record.py` and `_build_safe_terminal_detail` in `src/youtube_automation/production/ledger.py`. Prevents non-ASCII canaries, prompt prose, private scripts, and credentials from persisting into public ledger details while preserving raw runtime exceptions and source JSONL bytes. Verified via `tests/unit/test_safe_failure_reporting.py` (11 passed).
- Track 1 (#55, commit `cfc3393`): Qualified Windows non-mutating SQLite observation method in `src/youtube_automation/production/ledger_observation.py`. Proved rollback journal mode is strictly non-mutating (0 byte drift, 0 sidecars, exact SHA256 preserved, passes under OS read-only ACL). WAL mode fails closed with `UNSUPPORTED_WAL` pre-access check before connecting. Evidence receipt generated at `evidence/receipts/M1_OBSERVATION_QUALIFICATION.json`. Verified via `tests/unit/test_observation_method_proof.py` (11 passed).
- Track 2 (#37, commit `748dc70`): In-place core document reconciliation. Reconciled `docs/README.md`, `docs/product/architecture-renewal-plan.md`, `docs/product/architecture-renewal-spec.md`. Validated all 37 relative links resolve with 0 broken links. ADR 0005 conflict recorded.
- Track 2 (#42, commit `31c1d91`): Pinned profile revisions in new-episode briefs with legacy compatibility. Added immutable `revision` field to `Channel`, `profile_revision` to `Brief`, `profile_revision_identity`, and `verify_profile_pin` in `src/youtube_automation/production/contracts.py`. Preserved bound revisions on rebind and migration in `src/youtube_automation/production/briefs.py`. Verified via `tests/unit/test_profile_revision_pins.py` (6 passed) and all 518 production unit tests (0 failures).

### Next
- Proceed with Milestone M2:
  - Track 1: Issue #56 (Read-only status command and schema verification).
  - Track 2: Issue #38 (Error register and triage workflow) & Issue #39 (Skill lock verification and repair).
- Maintain independent review gates and frozen repo verification.

### Failures & Fixes
- `test_safe_failure_reporting.py`: Operational regex pattern initially failed on `Stage circuit is open`. Fixed pattern to `stage\s+circuit(?:\s+is)?\s+open`.
- `test_observation_method_proof.py`: Proved on Windows that WAL mode creates or updates `-shm` sidecars even with `mode=ro`. Enforced pre-access refusal `UNSUPPORTED_WAL` on WAL databases.
- `briefs.py`: Missing import `profile_revision_identity` and silent rebind mutation corrected to preserve existing/legacy episode revision pins. All 518 production tests pass.

## Architecture-Renewal Campaign Milestone M2 Completion, 2026-10-27

### Done
- Milestone M2 completed across both parallel tracks (Track 1: #56; Track 2: #38 & #39).
- Track 1 (#56, commit `cfff6f0`): Deliver genuinely non-mutating production status CLI. Replaced mutating directory creation and writable `Ledger(database)` instantiation with non-mutating `observe_ledger(database)`. Implemented `project_safe_job` and `format_ledger_status` in `src/youtube_automation/production/ledger_observation.py`. Sanitized prompt prose, credentials, and non-ASCII canaries while projecting operational failures to safe diagnostic summaries. Verified across populated, empty, absent, damaged, WAL layout, foreign schema, busy database, OS read-only permissions, and truncation via `tests/unit/test_production_status_cli.py` (9 passed). Frozen production suite: 555 passed in 115.77s.
- Track 2 (#38, commit `5313037`): Create searchable error cases while preserving legacy evidence. Preserved `docs/error-solving/understood-errors.md` untouched (exact SHA-256 `73e0486215fc176f581acfc1832c61ec2b0939f7b505bc45a689762defd8dc39`). Created triage guidance (`docs/error-solving/AGENTS.md`), case template (`docs/error-solving/TEMPLATE.md`), shallow index + anchor map (`docs/error-solving/README.md`), and five migrated representative cases in `docs/error-solving/cases/` (`ERR-001` through `ERR-005`). Verified via `tests/unit/test_error_cases.py` (4 passed).
- Track 2 (#39, commit `0c4093e`): Verify canonical skill provenance, task bindings, and platform discovery. Audited `skill-lock.json` (24 bound skills across 52 tasks, 109 active, 21 archived), `skills-lock.json` (29 upstream repositories with computed hashes), and `.claude/skills/` (14 active skills). Created `docs/skills/PROVENANCE_AND_DISCOVERY.md` detailing discovery surfaces, redundancy verification, restoration procedures, and explicit platform gaps (Codex <0.160 selection, `.agents/` gitignored convention, dynamic reload). Verified via `tests/unit/test_skill_discovery_and_lock.py` (5 passed).

### Next
- Proceed with Milestone M3:
  - Track 1: Issue #40 (Classify runtime retention and demonstrate reversible archiving).
  - Track 2: Issue #41 (Retire one verified obsolete non-runtime cohort).
- Separate bounded human approval remains strictly enforced for any production data operations, live provider requests, or releases.

### Failures & Fixes
- `src/youtube_automation/core/failure_record.py`: `_OPERATIONAL_PATTERN_RE` included `|\[redacted\]|`, causing error messages containing redacted tokens to falsely match as operational errors rather than projecting to safe diagnostic summaries. Removed pattern; credential strings safely project to sanitized messages.
- `tests/unit/test_skill_discovery_and_lock.py`: `active_project_skills` in `skill-lock.json` contains dict items rather than strings; updated test parser to extract `s["name"]`.

## Architecture-Renewal Campaign Milestone M3 Completion, 2026-10-27

### Done
- Milestone M3 completed across both parallel tracks (Track 1: #40; Track 2: #41).
- Track 1 (#40, commit `8a63fca`): Classify runtime retention and demonstrate reversible archiving. Built `src/youtube_automation/production/retention.py` and CLI retention stage (`--stage retention`, `--dry-run`, `--archive-cohort`, `--restore-cohort`) in `src/youtube_automation/production/cli.py`. Enforced categorization into `ACTIVE_STATE`, `IMMUTABLE_EVIDENCE`, `REBUILDABLE_CACHE`, and fail-safe `UNKNOWN_PRESERVE`. Proved dry-run zero-mutation guarantee, refusal to touch active/protected databases, atomic journaled interruption rollback, and SHA-256 byte-exact restoration via `tests/unit/test_runtime_retention.py` (6 passed).
- Track 2 (#41, commit `728987b`): Retire one verified obsolete non-runtime cohort. Selected 7 ad-hoc scratch scripts in `tools/` (`check_project_9320.py`, `check_h10_project.py`, `inspect_h10_prompts.py`, `test_banana_21.py`, `test_banana_pro.py`, `test_raw_cdp.py`, `test_cdp_quick.py`). Proved obsolescence beyond age: 0 callers across code, 0 dynamic imports, 0 packaging/release references, hardcoded obsolete URLs and run folders. Saved byte-exact preimages in `evidence/preimages/tools_scratch/` and audit receipt in `evidence/receipts/RETIRED_COHORT_TOOLS_SCRATCH.json`. Updated `tools/AGENTS.md` and verified reversible restoration via `tests/unit/test_retired_cohort_restoration.py` (4 passed).

### Next
- Proceed with Milestone M4:
  - Track 1: Issue #43 (Create resumable bounded local reference study under settled Wayfinder contracts).
  - Track 2: Prepare profile evidence and activation models (#44).
- Separate bounded human approval remains strictly enforced for live Windows REA collection (#45), production database operations, or external provider calls.

### Failures & Fixes
- `retention.py`: Refused archiving of any candidate outside `REBUILDABLE_CACHE` with explicit `PermissionError` to guarantee safety boundaries.
- `test_retired_cohort_restoration.py`: Verified 100% SHA-256 byte match on restored files from preimages before confirming cohort retirement.

## Architecture-Renewal Campaign Milestone M4 Completion, 2026-10-27

### Done
- Milestone M4 completed across both parallel tracks (Track 1: #43; Track 2: #44).
- Track 1 (#43, commit `a6a3ac4`): Create resumable bounded local reference study under settled Wayfinder contracts. Implemented `src/youtube_automation/production/study.py` defining `SamplingPolicy`, `CandidateVideo`, `AttributableEvidence`, `InferredTrait`, `ReferenceStudy`, `StudyCollector`, `select_sample`, and `evaluate_study_readiness`. Implemented 3-2-1 selection group ordering (recent, highest-viewed, middle-ranked) with shortfall preservation, candidate pool cap of 30, and minimum 3 distinct videos threshold for core inference. Enforced 4 required core areas (`subject_promise`, `viewer_need`, `tone_register`, `narrative_structure`) requiring >= 2 distinct supporting videos each, with unresolved counterexamples leaving the study partial. Enforced cumulative duration (60m/video, 180m total), byte (2 GiB), and attempt caps across resumes. Verified via `tests/unit/test_reference_study.py` (5 passed).
- Track 2 (#44, commit `cb37b08`): Derive and safely activate production profiles for new episodes. Implemented `src/youtube_automation/production/profile_activation.py` defining `DerivedProductionProfile`, `derive_production_profile`, and `ProfileActivationManager`. Enforces prerequisite that studies must be `CORE_READY` before profile derivation. Owner preferences (language, dialect, voice, constraints) override reference traits without mutating study observations. Preserved explicit null-voice (`voice=None`) and configured voices (`Achird`, `Charon`). Implemented atomic revision publication (`revisions/<revision>/profile.json`), journaled pointer switching (`active_revision.json`), and interruption recovery. Bound new episodes to pinned active revision through `Brief.profile_revision` while existing episodes retain historical pins. Verified via `tests/unit/test_profile_activation.py` (6 passed).

### Next
- Proceed with Milestone M5:
  - Track 1: Issue #46 (Text-visual alignment and narrative hook microbeats), Issue #47 (Motion grammar and pacing constraints), Issue #48 (Local UI kit and visual treatment boundaries), and Issue #49 (Episode visual-policy migration).
  - Track 2: Issue #50 (Integrated reference study to production verification suite).
- Separate bounded human approval remains strictly enforced for live Windows REA collection (#45), production database operations, or external provider calls.

### Failures & Fixes
- `study.py`: `save_study` initially omitted sample-selection shortfall gaps from evaluated study state; preserved both sample and core gaps.
- `profile_activation.py`: `Channel` contract requires exact fields (`allowed_treatments`, `audience`, etc.); adapted `resolve_channel` to construct valid `Channel` instance matching `contracts.py` invariants.

## Architecture-Renewal Campaign Milestone M5 Completion, 2026-10-27

### Done
- Milestone M5 completed across both parallel tracks (Track 1: #46, #47, #48, #49; Track 2: #50, commit `39ec893`).
- Track 1 (#46, #47, #48): Extended `study.py` with `ALLOWED_AREAS = REQUIRED_CORE_AREAS + ["visual_motion", "soundtrack", "packaging"]` and `profile_activation.py` with evidence-derived multimodal guidance bundles (`visual_guidance`, `audio_guidance`, `packaging_guidance`) carrying provenance tracking. Preserves evidence attribution while supporting owner overrides. Verified via `tests/unit/test_multimodal_pilot.py` (`test_issue_46`, `test_issue_47`, `test_issue_48`).
- Track 1 (#49): Explicit migration of supported existing episodes to a selected profile revision. Added `"revision"` to `_VISUAL_ONLY_PROFILE_FIELDS` in `briefs.py` and updated `rebind_visual_policy` and `_migrate_visual_policy` to adopt target profile revision. Updated `narration_fingerprint` in `contracts.py` to pop `revision` from `channel` and `profile_revision` from `projected`, preventing false invalidation of downstream writing and narration audio receipts during visual policy migrations. Verified via `test_issue_49_explicit_migration_of_existing_episodes`.
- Track 2 (#50): Integrated end-to-end channel study pilot and recovery suite. Validated 3-2-1 sampling, multi-modal evidence collection, core trait synthesis, atomic profile activation, new-episode revision binding, and existing-episode policy migration in `test_issue_50_integrated_resumable_channel_study_pilot`.
- Campaign test suite: 129 passed in 11.14s. Ruff checks: 0 errors. Strict mypy on modified modules: 0 errors.

### Next
- Note on Issue #45 (Live Windows REA Collection): Reserved for separate bounded human approval. Present feasibility findings, pre-flight checks, and approval boundaries to the human.
- Close out completed milestone issues (#46, #47, #48, #49, #50) on GitHub tracker once campaign review is confirmed.
- Prepare final campaign acceptance report for parent #31.

### Failures & Fixes
- `test_multimodal_pilot.py`: `narration_fingerprint` initially lacked stripping of `revision` and `profile_revision`, causing visual policy migrations between different profile revisions to fail identity checks. Updated `contracts.py` to pop `revision` and `profile_revision` in `narration_fingerprint`, preserving narration and audio receipts across visual policy revisions without weakening identity/voice guards.
- `briefs.py`: `rebind_visual_policy` and `_migrate_visual_policy` initially retained `existing.profile_revision` rather than adopting the target channel's revision. Updated to pin `profile_revision_identity(channel) or existing.profile_revision`.

## Architecture-Renewal Campaign Final Integration & Issue #45 Disposition, 2026-10-27

### Done
- Human approved Option A for Issue #45: accepted the validated offline study pilot and evidence collector (#43, #50) as completing the architecture-renewal campaign scope, closing #45 without live external Windows REA process invocation.
- All 13 child issues under parent #31 completed, verified, and ready for PR integration:
  - #54, #55, #56: Safe failure reporting, observation method qualification, non-mutating status CLI.
  - #37, #38, #39: Core document reconciliation, searchable error cases, canonical skill provenance.
  - #40, #41: Runtime retention classification & reversible archiving, obsolete cohort retirement.
  - #42, #43, #44: Profile revision pinning, resumable reference study collector, profile activation.
  - #45: Closed via approved offline pilot evidence.
  - #46, #47, #48, #49, #50: Multimodal guidance bundles, policy migration, integrated pilot suite.
- Campaign suite passes 100%: 129 passed in 11.14s. Ruff and strict mypy: 0 errors.

### Next
- Push `codex/renewal-campaign` to `origin`.
- Open campaign PR to merge into `master`.
- Post completion receipts and close accepted child issues #54-#56, #37-#50.
- Present final campaign acceptance report to human for parent #31 closure.

## Architecture-Renewal Corrective Campaign, 2026-10-28

### Done
1. **Safety Track 1A (Database Status & Diagnostics, PR #60)**:
   - Fixed RFC 8089 URI formatting in `ledger_observation.py` using `Path.resolve().as_uri() + "?mode=ro"`, preventing URI truncation at `#` and accidental sibling file creation.
   - Handled damaged/corrupted SQLite disks by catching `(sqlite3.OperationalError, sqlite3.DatabaseError)` and validating `PRAGMA table_info(jobs)` to return `UNSUPPORTED_SCHEMA` / `DAMAGED` without uncaught crashes.
   - Enforced `_BOUNDED_OPERATIONAL_PATTERNS` and sanitized unlabelled private prose in messages and nested `extra['context']` while safely recursing into structured dictionaries.
   - Generated dynamic `M1_OBSERVATION_QUALIFICATION.json` bound to tested commit, timestamp, environment, and physical file immutability receipts.
   - Tests: 39 passed in 4.55s; 78 failure record tests passed in 20.45s.

2. **Safety Track 1B (Runtime Retention & Restoration, PR #61)**:
   - Eliminated crash window data loss in `rollback_interrupted_cycle` by reconciling physical presence and SHA-256 hashes between source and destination regardless of in-memory `moved` flags, unlinking the archive only after all entries are proven restored.
   - Prevented overwriting newer resumed work in `restore_archive` by pre-validating destinations and raising `FileExistsError` on conflicting files.
   - Enforced strict cohort qualification for `REBUILDABLE_CACHE` (excluding code, plans, and state files) and protected archive storage from reclassification.
   - Made journal updates atomic via tempfile and `os.replace`.
   - Tests: 10 passed in 1.21s.

3. **Track 2 (Channel DNA Repairs & Acceptance Reconciliation, PR #62)**:
   - Enforced evidence attributability contract in `study.py:evaluate_study_readiness`: requires sample video ID presence, positive bytes, SHA-256 digests, and appropriate modalities (`transcript`/`metadata`).
   - Required corroboration across >= 2 distinct supporting sample videos for reusable multimodal guidance (`visual_motion`, `soundtrack`, `packaging`).
   - Made profile revisions immutable in `ProfileActivationManager` (raises `ValueError` on differing payload under existing revision).
   - Ensured fail-closed recovery in `recover_interrupted_activation`, discarding corrupted switch targets (`{}`) and preserving the prior active profile pointer.
   - Propagated multimodal guidance bundles to resolved `Channel` instances across new-episode boundaries.
   - Added permanent adversarial regression test suite `tests/unit/test_channel_dna_adversarial_regressions.py` (4 passed).
   - Reconciled documentation navigation (`docs/README.md`), contract discoverability (`AGENTS.md` and `production/AGENTS.md`), and honestly documented static vs live discovery boundaries in `docs/skills/PROVENANCE_AND_DISCOVERY.md`.
   - Reopened #37 and #39 with explicit remaining acceptance scopes.
   - Documented and authenticated user Option A offline substitution approval for #45 (conversation step 1613) without claiming live REA demonstration.
   - Mapped uncovered Track A lifecycle requirements to bounded issues #58 (Recovery Set & Isolated DB Restore) and #59 (Convergent Authority Discovery & Runtime Cutover) under parent #31.

### Next
- Monitor CI checks on PRs #60, #61, #62.
- Merge PRs into `master` following final-head checks and independent review.
- Close demonstrated child issues #54-#56, #40, #43, #44, #46-#48, #50.
- Keep parent #31, #37, #39, #58, #59 open.
- Present final corrective campaign disposition to the human for acceptance.

### Failures & Fixes
- `failure_record.py`: `sanitize_record` initially treated dict values under `context` as unlabelled prose and redacted the entire dictionary to string `"[redacted]"`. Fixed by recursing into structured dictionaries and lists while redacting sensitive string leaves, preserving dictionary access.
- `study.py`: `add_evidence` and `record_core_trait` called `self.save_study(updated_study)` which computed updated status, but returned the stale un-evaluated `updated_study`. Fixed by returning `self.save_study(updated_study)`.


## Architecture-Renewal Disposition Review Corrections, 2026-10-28

### Done
1. **Safety Track 1 (Database Status, Diagnostics, Retention & Facades, PR #63 - Merged `f22db81`)**:
   - Closed WAL sidecar creation race in `ledger_observation.py`: re-checks header bytes 18 & 19 on open connection before executing any queries; immediately closes and returns `UNSUPPORTED_WAL` if WAL layout detected, creating 0 `-shm` or `-wal` sidecars. Verified via `test_native_transient_and_sidecar_creation_prevented_on_layout_transition`.
   - Bound M1 qualification receipt `evidence/receipts/M1_OBSERVATION_QUALIFICATION.json` to source file SHA-256 manifest and demonstrated sidecar prevention proof.
   - Fixed diagnostic privacy leaks in `failure_record.py`: auth headers project strictly to `{Header}: [redacted]`, dropping trailing prose (e.g. `Our acquisition target is Orion`). `sanitize_record` recurses with `parent_sensitive=True` and enforces semantic key allowlisting, ensuring nested context values (e.g. `context.note = AcquisitionTargetOrion`) are redacted while numbers/bools and safe frame/known-issue definitions are preserved.
   - Fixed archive cycle reuse in `retention.py`: rejects cycle reuse if receipt already exists (`REFUSED_ALREADY_EXISTS`), protecting earlier archived bytes.
   - Enhanced multi-file interrupted restore resumption: `restore_archive` verifies destination file SHA-256 hashes to resume across partial moves without raising `FileNotFoundError`.
   - Hardened cache classification: restricted `REBUILDABLE_CACHE` to `KNOWN_REBUILDABLE_COHORTS` with `UNKNOWN_PRESERVE` default.
   - Synchronized facade deletions: updated `_FacadeProxy.__delattr__` in `compile_video.py` and `text_gate.py` to forward attribute deletion to underlying `self._target` and synchronize across submodules.
   - Test suites: 132 passed in 51.46s (safety), 73 passed in 12.69s (facades). All remote CI checks passed on PR #63 (run 40708320778).

2. **Track 2 (Channel DNA Physical Evidence, Modality & Digest Validation, PR #64)**:
   - Enforced physical disk evidence verification in `study.py`: `evaluate_study_readiness` validates actual file presence, non-zero size, and SHA-256 match on disk.
   - Required narrative modality (`transcript`/`narrative`) across >= 2 videos for core traits, refusing metadata-only studies from reaching `CORE_READY`.
   - Gated optional guidance bundles (`visual_motion`, `soundtrack`, `packaging`) on matching modality (`audio` for sound, `visual` for motion, `thumbnail`/`title`/`metadata` for packaging) and `resolved_contradictions is True`.
   - Validated active profile digest on load: `load_active_profile` computes canonical profile digest and asserts exact match against `active_revision.json['profile_digest']`, raising `ValueError` on file tampering.
   - Tests: 30 passed in 5.01s (including 8 adversarial regression tests).

3. **Acceptance & Issue State**:
   - Reopened child issues with demonstrated defects: #54, #55, #56, #40, #43, #44, #46, #47, #48, #50.
   - Kept open awaiting completion: Parent #31, #37, #39, #58, #59.
   - User Option A approval for #45 confirmed and preserved without live REA execution.

### Next
- Verify PR #64 CI completion on GitHub Actions.
- Merge PR #64 into `master`.
- Post completion receipts and close satisfied child issues (#54-#56, #40, #43-#44, #46-#48, #50).
- Keep #31, #37, #39, #58, #59 open.
- Present final disposition to human for acceptance.

### Failures & Fixes
- `failure_record.py`: Removing auth header prefix pattern caused projection to `[unknown/unknown] RuntimeError` which lacked `[redacted]` string expected by legacy test cases. Fixed by extracting matched header name and projecting directly to `{header_name}: [redacted]`.
- `failure_record.py`: Frame and known issue attributes were over-redacted due to missing key allowlisting. Fixed by adding `file`, `function`, and static `known_issue` descriptors to allowlisted diagnostic fields.
- `profile_activation.py`: Canonical profile digest computation encountered Windows CRLF mismatch against memory strings. Resolved by hashing normalized JSON UTF-8 bytes.


## Architecture-Renewal Return Review Corrections (PR #65 & PR #66), 2026-10-28

### Done
1. **Safety Track 1 (Observation Envelope, Diagnostics Privacy & Retention, PR #65 - Merged `14db478`)**:
   - Implemented SQLite WAL observation envelope in `ledger_observation.py`: detects concurrent transitions to WAL layout during execution, deterministically closes connection/statements, unlinks transient observer-spawned sidecars, and returns honest refusal (`status="UNSUPPORTED_WAL"`, `supported=False`) with zero sidecars left on disk. Verified via `test_post_second_check_wal_transition_refused_without_sidecars`.
   - Bound M1 qualification receipt `evidence/receipts/M1_OBSERVATION_QUALIFICATION.json` to source file SHA-256 manifest and demonstrated sidecar prevention proof.
   - Fixed diagnostic privacy leak for untrusted known issue signatures in `failure_record.py`: non-canonical free-text `observed_signature` (e.g. `Our acquisition target is Orion`) is redacted in `known_issue` and projected to `[id] Known issue matched` without echoing untrusted strings. Verified via `test_historical_known_issue_untrusted_signature_redacted`.
   - Protected pending archive cycles in `retention.py`: in-progress cycles lacking a completion receipt refuse conflicting reuse with differing candidates (`REFUSED_ALREADY_EXISTS`), preserving older archived bytes and journals. Verified via `test_incomplete_cycle_reuse_refused_preserving_prior_bytes`.
   - Structured rebuildable cache qualification: defined `QUALIFIED_REBUILDABLE_COHORTS` with explicit owners, generation recipes, and recovery qualifications, matching directory paths rather than arbitrary substrings.
   - Tests: 128 passed in 49.81s; remote CI passed (run 40733001856 in 9m 32s).

2. **Track 2 (Channel DNA Mandatory Storage, Idempotent Spend & Budget Bounds, PR #66)**:
   - Mandatory physical evidence storage: `evaluate_study_readiness` and `publish_and_activate` require physical study and evidence directory storage on disk. Absent storage fails closed with actionable gap `Physical evidence directory missing on disk` (`StudyStatus.PARTIAL`) and refuses activation (`ValueError`). Verified via `test_missing_evidence_directory_fails_closed_with_actionable_gaps`.
   - Idempotent study spend: `StudyCollector.add_evidence` checks for existing identical evidence items (same ID and SHA-256) and avoids double-counting cumulative duration or byte spend on resume. Verified via `test_identical_evidence_input_does_not_double_count_spend`.
   - Cumulative external seconds budget limit: `evaluate_study_readiness` enforces `study.spend.external_seconds <= study.policy.max_external_seconds`, leaving study in `PARTIAL` state if exceeded. Verified via `test_external_seconds_budget_exceeded_leaves_study_partial`.
   - Bounded representative offline media bundle: demonstrated derivation from real PNG frames/thumbnails, real RIFF WAV audio, valid MP4 clip, and narrative transcript into observable guidance carried into `Brief` and `Channel` contracts. Verified via `test_representative_appropriate_media_bundle_into_guidance`.
   - Revalidated physical evidence on recovery: `recover_interrupted_activation` verifies target revision evidence files and SHA-256 hashes before restoring pointer.
   - Tests: 34 passed in 5.82s.

3. **Issue Status**:
   - Reopened with verified receipts: #54, #55, #56, #40, #43, #44, #46, #47, #48, #50.
   - Strictly OPEN: Parent #31 (awaiting final human acceptance), #37, #39, #58, #59.
   - Option A offline substitution confirmed for #45.

### Next
1. Merge PR #66 into `master` upon CI completion.
2. Advance Track A Issue #58 (Complete operational recovery set and isolated database restoration).
3. Advance Track A Issue #59 (Convergent cross-checkout authority discovery, runtime cutover, and maintenance exclusion).
4. Reconcile remaining core documentation in #37 and multi-host skill discovery in #39.
5. Present final campaign results to the human for acceptance; do not close parent #31.

### Failures & Fixes
- `ledger_observation.py`: On Windows, deleting SQLite WAL sidecars immediately after `conn.close()` failed with `PermissionError` because statement cursor objects retained OS file locks. Resolved by deleting local `cur` reference and calling `gc.collect()` before unlinking transient sidecars.
- `test_channel_dna_adversarial_regressions.py`: Ruff linter flagged `import io, wave` as `E401` / `I001`. Resolved by splitting imports.
