Current QA-only closeout (19 October 2026): software gates passed; production pending. Grant99/95/4. HANDOFF and QA_ONLY_CLOSEOUT_20261019.md own current status; prior notices below are historical.

# Draft status

Refresh this description after the current Audacity and Soldier migration source packages pass renewed QA. Adoption is complete; current production artifact and release gates remain open. This retained draft does not establish merge readiness. Use [master](../../tasks/BRANCH_COMPLETION_MASTER.md) and [HANDOFF](HANDOFF.md) for current evidence and the 90/87/3 quota envelope. No new commit/push/merge occurred.

# PR Release Description: Adaptive Multi-Channel Visual Engine

## Overview

This branch adds an opt-in adaptive production path for saved channels and content-bound episode plans. It separates channel identity from episode strategy, validates narration-bound shot plans, preserves asset and stage lineage, and adds explicit review and publication gates. It includes fail-closed voice-direction, owned-pipe, publication-lock, and renderer-evidence contracts.

## Current verification

The last complete F2 run passed 1,848 tests in 195.09 seconds on the frozen pre-adoption tree, with Ruff, mypy, exercise lint, and the exact-receipt artifact CLI passing. A later run failed at 1,516 passed/1 failed/331 not reached because a fixture mocked the old helper; the fixture was repaired before the 1,848-pass run. The current source seal received an independent review with no blocking finding, and final frozen-tree QA is now running; no result is claimed yet. Clean-export PEP 517 wheel and sdist checks are planned and not yet run. The PR CI workflow lacks those build steps; the release workflow includes package builds.

## Acceptance and evidence boundaries

- A4's one-Help probe succeeded; A5's owner-selected discard completed. Neither action is repeated. Protected inputs verified 14/14.
- Soldier/H10 polished WAVs are owner-accepted. Their exact-byte adoption has not run. Read-only preflight found all four timeline-shim bodies and sidecars missing in each target run; the source validator rejects them before staging or invalidation. Staged Soldier/H10 export proofs now pass with the unchanged plan fingerprint and valid production plans; the bounded runner remains in preparation. See the conditional [audio adoption amendment](../../.runtime/codex_return_audit_20261018T191230Z/canonical_audio_adoption/LOCAL_AUDIO_ACTION_AMENDMENT_MISSING_SHIMS_DRAFT.md). No preview, critic, approval, or master state transfers through adoption.
- C3's saved v2 plan passes schema, lineage, and policy checks; the v3-only editorial validator does not invalidate that v2 plan. After accepted-polish adoption, visual progression requires migration to current v3 editorial policy and a fresh critic bound to current rendered-overlay evidence. C4 evidence is offline structural/hash review only.
- The complete revised D1 script is owner-approved/materialized at SHA-256 `d01ceed4aafe239ca132b106e8849b537117501415873bcd452b9e90926eef18` (8,676 bytes/837 words). No fresh narration exists; acoustic review, timing, and executable-plan lineage remain open.
- E4 live direction generation is explicitly approved only as a post-merge roadmap item. This does not defer the other pilot or Professor acceptance gates. F5's nonblocking historical limitation disposition is accepted; named pins and the historical independent review remain incomplete/unverified.
- Full F1 remains open. The 1,848-test report is pre-adoption evidence, not current-tree acceptance. Existing draft PR #21 is open at committed head `41d02eb`; its October 2 CI and CodeRabbit results do not cover current dirty changes. Working edits are uncommitted/unpushed; no duplicate PR or merge is claimed.

## Remaining release gates

Complete final exact-tree QA and clean-export package builds, review the bounded audio runner, execute only after its separate root GO, complete required previews/pilots and D1 derivatives, refresh and read back QMD, update existing PR #21, then obtain current-head review and CI. The current Codex usage envelope is 80% ceiling/78% detailed stop/2% closeout reserve; the latest supported snapshot was 60% at 2026-10-18 22:51:52 UTC. This usage policy is separate from provider/action grants. Merge remains a separate user decision.
