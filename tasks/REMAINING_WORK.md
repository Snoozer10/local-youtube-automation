# Remaining project work

Audit date: **2026-11-01, Asia/Riyadh**. Baseline: `master` at `ecc90972b4476596ca1c12756b3c7e4cddda9a45`, after [PR #77](https://github.com/Snoozer10/local-youtube-automation/pull/77).

**The engineering repair integration is complete. The product is not fully accepted.** The immediate concerns are a credential recorded in a tracked security report, conflicting current-status documents, incomplete automated gate coverage, and unfinished pilot acceptance. The full Professor episode remains explicitly deferred by the owner.

This is the readable inventory of remaining work and missing proof. [BRANCH_COMPLETION_MASTER.md](BRANCH_COMPLETION_MASTER.md) continues to own the existing A–F task states and acceptance criteria. Its dated dashboard needs reconciliation. The [documentation map](../docs/README.md) owns navigation, GitHub owns issue state, and exact receipts own execution evidence. IDs below organize this audit; they do not reopen closed issues or replace those authorities.

Execution/resume entrypoint: [ANTIGRAVITY_CAMPAIGN.md](ANTIGRAVITY_CAMPAIGN.md). Backlog campaign [#78](https://github.com/Snoozer10/local-youtube-automation/issues/78) and initial jobs #79–#81 were created after the inventory audit; refresh their current state rather than treating the earlier empty-tracker snapshot below as current.

## How to read this inventory

| Label | Meaning |
| --- | --- |
| **Confirmed** | A gap is visible in current files or refreshed records. This may be a documentation or test gap rather than a runtime defect. |
| **Open / Partial** | An existing acceptance task is unfinished at its recorded scope. |
| **Verify** | Evidence is missing or insufficient. Investigate before proposing a fix. |
| **Blocked** | A named dependency or exact-artifact acceptance must be satisfied first. |
| **Deferred** | The owner deferred this scope; listing it does not reactivate it. |
| **Recurring** | Required again when a relevant input, environment, output or release changes. |
| **Optional** | A candidate improvement, outside the current completion gate unless selected. |

Priorities: **P0** address exposure first; **P1** before the affected production/release milestone; **P2** planned maintenance; **P3** optional improvement. They are recommendations, not a new authorization to run providers, change credentials, publish, delete data or rewrite Git history.

Every row has a completion condition. A row closes only with scoped evidence or an explicit owner decision that removes it from required scope. Do not use a percentage to represent completion.

## What is already complete

- PR #77 is merged at `ecc9097`. Legacy timestamps, portable cleanup scanning, immutable profile retries, qualification-test isolation, typed authority boundaries and clean-checkout incident navigation were integrated. Do not repeat those repairs without a new reproducer.
- The retained integration closeout records **2,362 passed / 9 skipped** locally, strict mypy success in **84 checked files**, workspace Ruff success, and a wheel/sdist build. Native Python **3.10.20** focused checks recorded **115 passed / 1 deselected**; the excluded test explicitly requires a Python 3.11 qualification environment. These are dated receipts, not tests rerun for this document.
- Exact PR-head CI recorded **2,334 passed / 2 skipped**. CodeRabbit was **skipped**; independent local review was performed. Do not describe the skipped service as a completed review.
- At the original inventory audit, before campaign setup, live GitHub queries returned **no open issues and no open PRs**. The closed-issue query includes architecture parent #31, discovery #39 and the renewal/compilation children. Their old open-state prose is not a reason to reopen them.
- Accepted Soldier/H10 audio adoption, C1's exact Professor preview acceptance, and Snoozer C5/C6 qualification retain their recorded scope. Preserve accepted narration and media; rerun only an affected gate.
- Channel profiles already exist. Snoozer's `voice: null` is an intentional synthesis block, not a missing voice configuration to fix.

Evidence: [PR #77](https://github.com/Snoozer10/local-youtube-automation/pull/77), its [successful CI run](https://github.com/Snoozer10/local-youtube-automation/actions/runs/41338491243), and the local closeout `.runtime/repo_review_integration_20261101/integration/CLOSEOUT.json`.

## Recommended order

1. **S01–S02:** privately resolve the exposed credential's status and remove the value from current tracked documentation. Inventory history/artifact exposure without spreading the value.
2. **R01–R03:** reconcile current records and choose the next milestone. Keep deferred G6 work visibly deferred. Turn selected work into small tracked jobs rather than reopening completed campaigns.
3. **E02 → E01, E03, U05–U06:** align CI and release checks with the actual supported product and offline test boundary.
4. **P01 → P02–P05:** close Professor delivery using the intended accepted candidate and existing narration. Reuse unchanged approval; request review only for a changed artifact or missing provenance.
5. **P06–P12 → P14:** close Soldier/H10 review and delivery gaps, reconcile spend, then close the combined pilot matrix.
6. **D01–D08:** resume the full episode only after the owner's explicit scope decision, C7 prerequisites and any required bounded grants.
7. Select optional polish only where it improves an observed problem. Large rewrites and new tooling are not prerequisites.

Security/docs and offline CI work can proceed independently. Media stages sharing a run, accepted outputs, encoder or provider allowance must be coordinated by one owner.

## 1. Security and privacy

Owner: maintainer for repository changes; credential owner for private account actions. Never put credential values in a task, review comment, fixture or receipt.

| ID | Priority / state | Remaining job and completion condition | Evidence / dependency |
| --- | --- | --- | --- |
| **S01** | P0 · Verify | Establish whether the credential recorded in the historical report was revoked. If potentially usable, the owner revokes/rotates it privately and verifies the intended integration. Record only a sanitized disposition and date. | A distinct token-shaped value remains in tracked `docs/security_analysis/secret_audit_report.md:43`; the July report labels it active. Current validity is unknown. No live credential test was made. |
| **S02** | P0 · Confirmed | Redact the value from the current report and inspect related current tracked text for accidental repetition. Preserve security history in a safe, access-controlled form; public evidence uses redacted content. Done when a value-free scan confirms the owned changes no longer contain the reported value. | Same report, lines 29–57; `docs/security_analysis/threat_model.md:13`. README/remediation examples must be distinguished from the distinct report value. |
| **S03** | P1 · Verify | Assess Git history, remote visibility and previously published artifacts for the exposed value. Record affected surfaces and an owner-approved response. History rewriting, if warranted, is a separate coordinated action with recovery and collaborator guidance. | Depends on S01–S02. The checked integration sdist contains no security-analysis documents; that does not prove all historical artifacts safe. |
| **S04** | P1 · Confirmed | Add a proportionate secret-scanning gate covering service tokens and documentation. Verify a sanitized positive case is rejected and ordinary examples are handled deliberately; use reviewed exclusions, not a blanket ignore of reports. | `.pre-commit-config.yaml:26-27` covers private keys/AWS credentials; `.github/workflows/ci.yml` has no general token scan. |
| **S05** | P1 · Confirmed | Correct SECURITY guidance: replace the placeholder reporting contact with a verified route, preserve Audacity recovery data, describe actual FFmpeg file-backed arguments, and accurately describe Telegram credential transmission. Align the threat/remediation documents with current controls and date their remaining claims. | `SECURITY.md:28,58,76,83,98-99`; current source contract takes precedence. The historical remediation review date has passed. |
| **S06** | P2 · Verify | Run a bounded dependency/security review against the actual installed and distributable dependency sets. Triage findings for reachability and supported Windows/Python versions; pin or upgrade only with affected regressions and a recorded rationale. | `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`. No fresh vulnerability audit was run here; this is not a claim of a known dependency vulnerability. |

## 2. Status records, evidence and documentation

Owner: coordinator/documentation maintainer. The short current pointers added with this audit do not reconcile every historical paragraph.

| ID | Priority / state | Remaining job and completion condition | Evidence / dependency |
| --- | --- | --- | --- |
| **R01** | P1 · Confirmed | Reconcile active dashboard/resume claims with merged PR #77 and closed renewal issues. Label retained snapshots by date; remove current-sounding contradictions without rewriting receipt history. Done when the master, adaptive checklist/usage, renewal plan/spec and handoff route readers to the same current state. | Master still leads with PR #21; adaptive checklist leads with PR #22 open; renewal plan contains both closed-child updates and older open/unimplemented claims. The audit adds pointers only. |
| **R02** | P1 · Confirmed | Classify broken evidence pointers as present, archived/recoverable, external-only or missing. Correct unsupported current claims and document recovery routes. A cited path must not imply the file is available in a fresh checkout. | The exact D1 approved-script and D3 validator paths cited by the master are absent here. See D01. Local C2–C7 receipts are present and hash-checked; this does not validate their acceptance claims. |
| **R03** | P2 · Partial setup | Select the next milestone and register its finite jobs in the existing tracker with acceptance/dependencies and links to this inventory. Keep C/D states in the canonical master; do not clone all historical checkboxes into new issues. | The inventory audit found no open tracker jobs despite unfinished C/D work. Subsequent setup created campaign #78 and initial jobs #79–#81; register further selected jobs as they are claimed. Inventory creation itself did not create issues. |
| **R04** | P2 · Confirmed | Finish or deliberately bound QMD embedding maintenance, verify retrieval of changed documents, and record the pending count. Review orphan-vector maintenance separately before cleanup. Lexical retrieval remains the working fallback. | Audit-start QMD status: 483 documents, 143 pending embeddings. Update output also reported orphan chunks; no cleanup was performed. An index backlog is not an application runtime defect. |
| **R05** | P2 · Verify | Audit current reader routes and command examples against clean-checkout files and source. Separate portable public documentation from local `.runtime` evidence links and owner-machine paths. Correct only current guidance; retain dated forensic records. | `docs/README.md`, `README.md`, `docs/Project-workflow.md`, task usage guides. The missing incident directory was repaired in PR #77; do not repeat that fix. |
| **R06** | P3 · Optional | Complete term-by-term migration from CONTEXT to GLOSSARY where a real conflicting definition remains. Preserve consumers and provide redirects; do not rename concepts solely for consistency. | `docs/README.md:12,25,38`, `GLOSSARY.md`, `CONTEXT.md`. The audio-chain meaning is already reconciled in the map. |
| **R07** | P2 · Recurring | Maintain this view after milestones: update the canonical task/issue first, link exact evidence, then refresh the inventory and handoff. Record passed, failed, deferred and not-applicable distinctly. | `tasks/AGENTS.md`; master operating rules. Do not let this document become another stale authority. |

## 3. Engineering, tests and operational proof

Owner: engineering maintainer, with independent review for source/gate changes. No new runtime logic defect is asserted solely because a check is missing.

| ID | Priority / state | Remaining job and completion condition | Evidence / dependency |
| --- | --- | --- | --- |
| **E01** | P1 · Confirmed | Enforce the documented offline gates in CI: workspace lint, full strict source typing, approved offline test selection, and wheel/sdist build. Keep intentional live tests opt-in. Done when the exact PR head runs those checks and the workflow cannot silently narrow their scope. | CI currently runs `ruff check tests/unit` and `pytest tests/unit` on Python 3.11; `docs/agents/workflows.md:42-44` names broader gates. Depends on E02's test classification. |
| **E02** | P1 · Confirmed | Map the full-suite versus CI collection delta by node ID, including parametrization and skip reason. Include deterministic integration/e2e cases in regular CI; document actual live cases and their separate procedure. | Retained results: local 2,362/9 versus CI 2,334/2. `tests/integration/test_run_singlepass.py` uses fake subprocesses; `tests/integration/test_e2e_pipeline.py` contains offline/local cases. Counts alone do not prove failures. |
| **E03** | P1 · Verify | Resolve the supported-runtime promise: add an appropriate native Python 3.10 compatibility lane or explicitly amend support with owner approval. Keep the Python 3.11 SQLite qualification test distinct; document exact exclusions and platform requirements. | `pyproject.toml:11,152-153` advertises/targets 3.10; CI tests 3.11 only. PR #77 native 3.10 proof is focused, not a full compatibility matrix. |
| **E04** | P2 · Confirmed test gap | Isolate the legacy exact-payload trust-anchor regression: make the target inactive and remove competing anchors so the test proves the intended one alone. Preserve positive/negative timestamp/tamper cases. | `tests/unit/test_profile_activation.py:299-332` leaves the published target active; the integration reviewer recorded this as nonblocking. This is missing regression precision, not a demonstrated activation bug. |
| **E05** | P2 · Confirmed | Align pre-commit and authoritative CI/local quality scopes and versions. Prove hooks check the intended source tree; document which command is authoritative. Avoid automatic broad formatting as part of alignment. | `.pre-commit-config.yaml` pins Ruff 0.1.0/mypy 1.5.1 and applies its own args; `pyproject.toml` and the workflow define other scopes. Resolve differences with evidence. |
| **E06** | P2 · Recurring | Keep installed-artifact tests for prompt resources, configuration defaults, facades and conditional dependencies. For affected packaging changes, test an isolated installed wheel/sdist rather than relying on imports from the checkout. | Existing package/resource proof is complete for the PR #77 source. Revalidation is triggered by package/resource changes, not by this inventory. |
| **E07** | P2 · Verify | Document a reproducible supported Windows development setup: interpreter, dependencies, FFmpeg/Audacity/browser prerequisites and optional features. Compare fresh installation with the declared manifests and record dependency drift. | Manifests use version ranges; CI installs additional system/browser dependencies. Do not force one global lock strategy or upgrade all packages without an observed need. |
| **E08** | P2 · Verify | Maintain a skip/xfail inventory with reason, owner, offline substitute and explicit live acceptance path. Resolve accidental coverage holes; keep intentionally gated native/browser tests honest. | `tests/conftest.py` gates `live_browser`; production-source narration tests also use skip conditions. Nine skips in one retained run are not nine defects. |
| **E09** | P1 before live work · Recurring | Requalify the specific browser/Audacity/encoder path before using it after environment drift: owned profile/process/window, listener/lease identity, exact model/voice, bounded attempts and stop condition. Record zero-send failures and uncertain outcomes. | Master A4/A5/E4 are completed at historical scope. Offline mocks, installed versions and past handshake receipts do not establish current readiness. No live check was authorized by this audit. |
| **E10** | P1 before maintenance · Recurring | Before changing authority/runtime/schema or restoring state, verify the current recovery closure, isolated restore, concurrency exclusion and stale-generation refusal for the actual affected environment. Preserve damaged originals and journals. | Track A #54–#56, #58 and #59 are closed with qualification receipts. Requalify when inputs/runtime change; do not reopen their implementation just because ongoing operational discipline remains necessary. |
| **E11** | P2 · Verify | Review the existing resilience matrix against maintained sanitized replay cases and public boundaries. Add only a missing demonstrated failure class: result-before-resend, unknown-screen refusal, durable retry caps, error identity or ownership drift. | Master `Original resilience promises` matrix and `tests/fixtures/semantic_failures/`. E5's prior disposition remains closed; this is a targeted coverage review, not a new framework. |
| **E12** | P3 · Optional | Capture a small baseline for routing/diagnosis time and a representative compile/resume workload before claiming architecture/performance improvement. Record environment and artifacts; optimize only a measured bottleneck. | Renewal plan `Purpose and success measures` states baselines are not measured. No speed or reliability improvement percentage is supported. |
| **E13** | P3 · Optional | Reduce a large/coupled module only when the next real change demonstrates friction. Map public seams and callers, choose one extraction, preserve facade compatibility and regression behavior. | Current package has 85 tracked Python files. File size or complexity alone does not justify a subsystem rewrite. |
| **E14** | P1 before direction production · Verify | Reconcile current execution receipts for automated model-generated voice direction. The generation stage already exists; if its required production proof is absent, qualify one separately authorized candidate with current input/model/transport bindings and bounded retries. Preserve accepted Soldier/H10 audio and imported-audio/null-voice refusal. | Canonical E4 retains a Phase 2 post-merge roadmap; `src/youtube_automation/production/cli.py:528-565` and `src/youtube_automation/production/direction_stage.py:341-420` implement the stage. Offline `accept-direction` is not proof of automated generation. Readiness E09 is necessary for a live qualification but does not itself satisfy it. |

## 4. Finish the pilots

Owner: production coordinator for evidence/lineage; human owner for exact-artifact editorial acceptance. Existing task IDs in the right column remain canonical. Use the accepted narration and preserve rejected candidates.

| ID | Priority / state | Remaining job and completion condition | Canonical scope / dependency |
| --- | --- | --- | --- |
| **P01** | P1 · Verify first | Identify the intended Professor run, preview hash and current recipe. Reconcile the master's accepted `ca8e6c98…` candidate with the different `15ec1c7d…` preview described by the usage guide. Record which artifact the next task uses. Never transfer approval between them. | C1/C2; master lines 173–187 versus usage guide line 9. Reuse C1 acceptance if its exact subject is unchanged and its dependency contract still holds. |
| **P02** | P1 · Partial | Close Professor's current recipe/plan/critic/reference/OCR/every-shot audit and repair the stale scorecard/approval binding through the supported boundary. Change only the failed dependency. | C2; depends on P01. A changed preview requires fresh full review; an unchanged accepted preview does not need approval requested again merely because this audit exists. |
| **P03** | P1 · Open | Complete Professor thumbnail and metadata review, with correct source/brand/claim relation and readable small-size text. Seal the selected artifact and review. | C2; depends on the selected candidate and applicable packaging contract. Thumbnail/master were deferred in the delivery receipt. |
| **P04** | P1 · Blocked | Perform guarded local Professor master activation when the dependencies pass and the separate activation scope is authorized. Record atomic publication and rollback/recovery evidence. | C2; P02–P03 and exact approval. Local activation is distinct from public upload. |
| **P05** | P1 · Blocked | Execute a real controlled restart/reuse check: select the same approved plan/assets/audio/master without unnecessary generation, preserving allowance and receipts. Record what actually ran. | C2; P04. Saved stage checks or matching hashes alone are not restart execution. |
| **P06** | P1 · Partial | Review every encoded Soldier Samar shot for factual/naval accuracy, narration match, source caution, reference continuity, bilingual OCR, progression and mobile readability. Repair only failed shots/dependencies. | C3; accepted audio/timing retained; preserve every spoken word and the approved ≤91-second cap. E09 applies if a live step becomes necessary. |
| **P07** | P1 · Verify / Open | Establish valid human-approval provenance for the exact Samar preview, or obtain it if absent. Record complete viewing, the seven scores and any rejection/revision. An `Owner` label is insufficient proof by itself. | C3; P06. The ledger records technically aligned media, not complete current human acceptance. |
| **P08** | P1 · Blocked | Complete Samar thumbnail/metadata, guarded activation and actual restart reuse with current hashes. Split these into small execution jobs when selected; do not infer publication or new provider allowance. | C3; P07 plus P12 accounting. Preserve the 18 accepted assets where unchanged. |
| **P09** | P1 · Partial | Review every encoded H10 dog-cue shot and all actual image/overlay text against the spoken cues. Verify current recipe, continuity, pacing and OCR; repair only observed failures. | C4; 15 technically aligned assets/proofs are recorded. The earlier stale-plan claim was retracted; do not repair the raw-dictionary/model digest difference. |
| **P10** | P1 · Verify / Open | Resolve exact H10 preview human provenance and record complete editorial acceptance or rejection. Changed outputs require fresh review and downstream binding. | C4; P09. Preserve accepted H10 narration and timing. |
| **P11** | P1 · Blocked | Complete H10 thumbnail/metadata, guarded local activation and actual restart reuse as separate small jobs with receipts. | C4; P10 plus P12. Saved `True` stage checks are insufficient. |
| **P12** | P1 before spending · Verify | Reconcile cumulative pilot generation/retry accounting, resets and uncertain attempts. Establish actual spent/remaining bounds before any new send. Preserve unknown totals as unknown until evidenced. | Master dashboard records H10=17/Samar=18 saved spend but unresolved cumulative history. Prior grants do not reset on resume. This audit authorizes no sends. |
| **P13** | P2 · Deferred / Decision | Decide whether a Snoozer thumbnail is required for the selected delivery scope. If required, create/review only that packaging artifact; otherwise record an explicit not-applicable/deferred disposition in C7. | C5/C6 are already qualified at their scope. The run has acceptance/master records but no thumbnail-named artifact was found. Do not rerender accepted media or enable TTS. |
| **P14** | P1 · Blocked | Close the criterion-by-criterion combined pilot matrix: Professor, Soldier and Snoozer under current recipes; H10 as the separate topic-adaptability test. Each criterion needs current proof, explicit not-applicable or a visible blocker. | C7 / G4 / G5 / H10. Depends on required P01–P13 outcomes. All three contrasting pilots must meet the agreed acceptance; no approval transfers across outputs. |

### Editorial review and polish for each affected preview

These are acceptance dimensions for P02/P06/P09 and the full episode, not new reasons to regenerate an unchanged accepted artifact.

- **Story and claims:** every visible beat matches its exact narration; scientific/historical/animal-behavior claims have appropriate caution and sources. Distinguish observed behavior from illustration or inference.
- **Hook and progression:** the opening presents a specific problem, curiosity turn and promise. Each later beat adds information, action or consequence. Holds, repeated layouts and generic scenes need a purpose.
- **Visual appeal:** purposeful composition, cast/reference consistency, camera/crop variety and restrained motion. Inspect motion in the encoded video, not only contact sheets.
- **Text and localization:** Arabic shaping, dialect/copy fidelity, bilingual OCR, text collisions, subtitle timing and contrast. Check phone-size readability, including approximately 480-pixel review views where required.
- **Audio:** intelligibility, chapter joins, clipping/loudness and synchronization in the actual preview. Preserve accepted words, voice and timing unless a separately accepted repair requires a change.
- **Technical quality:** complete frame/duration coverage, actual codecs/dimensions/color/audio properties, beginning/middle/end and every-shot inspection, plus current recipe/input hashes.
- **Human review:** semantic match, hook, attractiveness, progression, continuity, readability and motion scores bound to the exact preview. Required minima are gates; a 5/5 judgment is the owner's, not a test result.
- **Packaging:** title/thumbnail promise matches the video, text is readable at small size, metadata is correct and the exact chosen image is reviewed. Publishing requires its own scope.

Sources: [adaptive visual plan](adaptive-visual-plan.md), [Professor playbook](professor-visual-playbook.md), [channel contract](../channels/AGENTS.md), [production contract](../src/youtube_automation/production/AGENTS.md).

## 5. Full Professor episode: deferred, not completed

**D1 production remains DEFERRED BY USER.** This inventory does not restart it. The old full source is historically recorded as 509.418625 seconds with SHA-256 `967f539225482772a7f4c7e9571023c293d33ad9871ba10114841e8fe858b203`; it is not the short pilot and does not validate revised narration.

| ID | Priority if resumed / state | Remaining job and completion condition | Dependency / canonical task |
| --- | --- | --- | --- |
| **D01** | P1 · Deferred / missing inputs | Recover and verify the exact approved full script, its approval/materialization receipts and any required source audio from retained archives or the owner. Record original hashes and availability. Do not reconstruct approved text from summaries. | D1; the master's exact approved-script and D3-validator paths are absent here, as is the checked full-audio path. Absence here does not prove deletion everywhere. |
| **D02** | P1 · Deferred | Under a new applicable narration grant, create the approved complete narration if that remains the selected scope. Review all audio for fidelity, script correspondence and claims; keep source/script/audio lineage explicit. | D1, D01 and owner request. Preserve the approved script; old audio approval does not transfer. |
| **D03** | P1 · Blocked | Build the full run and canonical timing from the reviewed narration; cover every spoken word and all frames without gaps/overlap, preserving source bytes and import lineage. | D2; requires D1 and C7. Old technical timing is historical. |
| **D04** | P1 · Blocked | Create a current schema-valid, narration-bound full-episode plan and independent critic. Review claim coverage, hook, visual palette and exact semantic intervals before generating assets. | D3; D02–D03. The retained 70-shot roadmap is a draft. The master's 1,761-error count is historical; its cited validator receipt is absent and was not rerun here. |
| **D05** | P1 · Blocked | Produce only the plan's required assets under a separately bounded allowance; verify reference chains, dimensions, OCR and every rendered shot. Derive the budget from the reviewed plan. | D4; D04, current live readiness if needed and explicit provider scope. Old estimates are not authorization. |
| **D06** | P1 · Blocked | Render and technically review the full preview, all narration/frames/subtitles, audio/video sync and complete shot coverage. Seal the review package. | D5; D05. Reuse valid assets; preserve failed candidates. |
| **D07** | P1 · Blocked | Obtain human acceptance of the complete exact full-episode preview. Resolve or explicitly reject every material finding and bind scores/review to its hash. | D6; D06. Pilot approval is insufficient. |
| **D08** | P1 · Blocked | Complete the full-episode thumbnail, metadata, authorized local master activation and actual restart reuse; preserve publication/recovery receipts. | D7; D07. External uploading is separate and is not required by the historical branch-completion definition. |

## 6. Usability, packaging and release

Owner: maintainer/release coordinator. Packaging verification may run locally; publishing a release or video remains a separately selected action.

| ID | Priority / state | Remaining job and completion condition | Evidence / dependency |
| --- | --- | --- | --- |
| **U01** | P2 · Confirmed | Replace overstated README claims with the supported staged workflow: existing subscriptions, quotas, local prerequisites, human preview review and actual automation limits. Keep setup and capabilities accurate. | `README.md:3,5,21,45`: fully autonomous/zero-bill wording conflicts with the review gate and subscription caveat. |
| **U02** | P2 · Verify | Walk a fresh contributor through offline setup, one channel choice, safe help/inspection and a deterministic sample. Record missing prerequisites and fix only verified documentation/launcher defects. | `README.md`, `setup.ps1`, `setup.bat`, `run.bat`, usage guide. Do not invoke real account/profile/provider steps as an incidental setup test. |
| **U03** | P2 · Verify | Review operator-facing help and failure messages for actionable next steps, current paths, recoverable state and clear unavailable/unsafe status. Check a small set of actual failure cases and avoid exposing private payloads. | Root facades and production CLI/status/diagnostics. Existing non-mutating status implementation is complete; improve only observed usability gaps. |
| **U04** | P2 · Recurring | Before the next release, write change notes covering renewal and PR #77 repairs with actual limitations. Align package/GEMINI/changelog versions and distinguish unreleased changes from published tags. | Current metadata is 4.5.1; CHANGELOG's latest dated release is 2026-10-23. This audit does not choose the next version or rewrite a published tag. |
| **U05** | P1 before release · Confirmed | Harden and verify the actual Windows ZIP: missing required config/setup/docs must fail; assert no credentials/operational state/media/cache payload; unpack to an isolated location and smoke-test imports, prompts, saved profiles and documented launch paths. | `.github/workflows/release.yml:89-120` conditionally copies some required files and checks only package/prompt/profile presence. PR #77 verified wheel/sdist, not this ZIP. |
| **U06** | P1 before release · Confirmed | Make tag/manual release publication consume successful required quality gates for the exact revision, or run equivalent gates in the release workflow. Preserve artifacts/hashes and stop publication on a failed prerequisite. | Release workflow builds/publishes without its own test/typing/lint jobs. E01–E03 and U05 define relevant coverage; avoid redundant expensive jobs when a reliable exact-revision dependency suffices. |
| **U07** | P2 · Future action | When a release is selected, review notes, exact revision, checksums and install verification; then publish only the authorized tag/assets and verify downloadable results. For video distribution, separately review exact master, thumbnail, metadata, source attribution/rights and destination. | Depends on selected release or distribution scope. Neither public video posting nor a new software release is triggered by this backlog. |
| **U08** | P3 · Optional | Decide whether preserved repair branches are still useful. If retiring them, verify merged ancestry and recovery first; preserve unrelated `.serena/project.yml` work and all evidence. | Current local branches include `master`, `fix/repo-review-20261101` and `codex/repo-review-repairs`; one worktree. Old “only master remains” text is stale. No cleanup ran. |

## 7. Optional future improvements

These items are visible possibilities, not missing promises in the current accepted engineering scope.

| ID | Priority / state | Candidate and selection condition | Done if selected |
| --- | --- | --- | --- |
| **O01** | P3 · Optional | Improve operator visibility of cumulative allowance, uncertain sends and run dependencies if P12 demonstrates an actual usability gap. | One existing CLI/report surface shows receipt-backed facts and unknowns without becoming a second ledger or resetting counters. |
| **O02** | P3 · Optional | Improve the preview-review packet if current reviews are difficult to perform. | A compact packet links exact preview, storyboard, shot/cue times, scorecard and reject history; human review remains authoritative. |
| **O03** | P3 · Optional | Add a contrasting channel/topic stress test after C7 if current acceptance exposes a generalization gap. | A bounded offline/authorized case proves the selected missing behavior; no automatic expansion to every channel or a whole new campaign. |
| **O04** | P3 · Deferred capability | Implement/prove live Windows REA only if the owner selects it as future scope. | Current supported capability, source/origin/time/sample bounds and meaningful source-bound output are proved. #45's accepted Option A offline substitution stays closed. |
| **O05** | P3 · Unselected | Revisit DeepSeek/provider migration only if a current requirement justifies it. Old folder names and historical security proposals do not authorize it. | Separate accepted spec, privacy/cost boundary, compatibility proof and bounded execution plan. |

Automatic backup scheduling, a new runtime directory tree, a universal workflow engine, an always-on service, a monorepo system, bulk skill installs and wholesale renderer replacement are **not** current completion requirements. Propose one only for a measured problem and an accepted scope.

## What “complete” should mean

| Completion level | Remaining acceptance |
| --- | --- |
| **Integrated engineering repairs** | Complete for PR #77's frozen scope. Future defects reopen affected checks only. |
| **Maintained engineering baseline** | Resolve S01–S05, reconcile R01–R03, align the selected CI/runtime/package gates, and disposition evidence gaps. Investigation rows may close with evidence that no change is needed. |
| **Pilot-ready product** | C2–C4 and C7 pass their exact-artifact criteria; C1/C5/C6 retain valid scope; accounting, full review, local activation and restart reuse are evidenced wherever required. |
| **Full original product delivery** | D1–D7 pass, or the owner explicitly revises the completion scope. Deferral is visible but does not mean delivered. The historical master explicitly includes C7 and D1–D7 in its full completion definition. |
| **Release-ready distribution** | Exact-revision gates, installed package/Windows ZIP proof, accurate notes and credential-safe artifacts; publication remains a selected action. |
| **Ongoing maintenance** | Relevant environment changes trigger requalification; new failures get bounded reproduction and sanitized replay evidence. Optional polish does not hold completion open forever. |

## Critical assessment

1. **The current weakness is proof and coordination, not a need for another architecture rewrite.** Closed implementation tickets coexist with unfinished editorial work and missing operational evidence. A new framework would not supply those approvals.
2. **Current-looking historical prose is an execution risk.** The same roadmap can describe a lifecycle as unimplemented, list it closed, then recommend work already merged. A short authoritative update plus clearly dated history is more useful than another long append-only status narrative.
3. **Green CI currently proves less than the written contract.** Strong local receipts helped PR #77, but manual diligence should not be the only place strict typing, full offline selection and packaging happen.
4. **Security documentation has become part of the exposure.** A report describing a secret must not preserve that value in normal tracked text. Revocation evidence and redacted diagnostics matter more than adding another checklist.
5. **Technical media proof is being asked to carry editorial conclusions it cannot establish.** Hashes, probes, model labels and saved stage checks do not prove complete viewing, engaging pacing, human provenance or a successful restart.
6. **Recoverability is narrower than a link to an archive.** Missing approved-script/validator paths must be recovered and verified before reuse. This audit did not establish that those inputs are lost globally or that all historical archives are complete.
7. **Keep the next milestone small.** After the security and gate work, finish one pilot's complete delivery. Avoid reopening accepted narration, every historical finding, and all optional feature ideas at once.

## Audit coverage, evidence and limits

- Baseline census: **809 tracked files**, including **85 Python files under src**, **149 Python files under tests**, and **312 Markdown files**. These are file counts, not test coverage or a claim that every line was inspected.
- Reviewed: root/task contracts and workflow; canonical task and feature ledgers; product renewal plan/spec and documentation map; CI/release/manifests/pre-commit; security guidance; focused activation tests; channel/pilot records; current evidence-path existence and selected receipt hashes. Three independent read-only audits covered product, engineering and records.
- Refreshed remote issue/PR searches and PR #77 metadata through the connected GitHub tool. Results are stored locally under `.runtime/remaining_work_audit_20261101/remote_*.json`. No issues, PRs, settings or releases were changed.
- A value-free, bounded scan of current tracked text found the distinct report credential-shaped value. It did not contact Telegram, inspect private environment values, scan every binary/history object or establish token validity. Findings contain locations/counts only.
- Presence/hash checks confirm six C2–C7 JSON receipts exist. Their contents/labels do not independently prove full editorial acceptance. The three checked D1/D3/full-audio paths are absent in this checkout; external owner directories and archives were not exhaustively searched.
- Intentionally unchanged: root/source/production/channel/tests/tools contracts because runtime behavior and ownership did not change; renewal/security/feature records because this inventory identifies their follow-up work without rewriting historical decisions or marking acceptance complete. Only task ownership/navigation and the current handoff cursor were updated.
- No full test suite/build was rerun for this documentation-only change. The prior results above were read from the completed integration closeout. Focused document/link/ownership checks for this change are recorded in the audit's local verification receipt.
- QMD lexical indexes were refreshed; semantic retrieval was not relied on while embeddings were pending. This file is a dated audit, not a guarantee that undiscovered defects do not exist.
- No providers, browser automation, Audacity, media generation, activation, cleanup, credential service, Git history rewrite or publication was invoked. The only preexisting local edit, `.serena/project.yml`, is preserved.

Key source routes: [canonical master](BRANCH_COMPLETION_MASTER.md), [feature checklist](adaptive-visual-tasks.md), [staged usage](adaptive-visual-usage.md), [renewal plan](../docs/product/architecture-renewal-plan.md), [renewal spec](../docs/product/architecture-renewal-spec.md), [engineering workflows](../docs/agents/workflows.md), [CI](../.github/workflows/ci.yml), [release workflow](../.github/workflows/release.yml), [security guidance](../SECURITY.md).
