# Antigravity backlog campaign entrypoint

Prepared 2026-11-01. This is the durable resume route for the Antigravity backlog campaign; it is an operating guide, not a live-run grant.

## Campaign control surfaces

- Campaign issue and current coordination record: [GitHub issue #78](https://github.com/Snoozer10/local-youtube-automation/issues/78). Read the latest issue and linked PR before acting; do not trust an old local snapshot.
- Initial queue: [S01 owner credential disposition #79](https://github.com/Snoozer10/local-youtube-automation/issues/79), [S02 first source slice #80](https://github.com/Snoozer10/local-youtube-automation/issues/80), [E02 offline CI-selection follow-up #81](https://github.com/Snoozer10/local-youtube-automation/issues/81). Refresh their actual states before claiming work.
- Inventory and critique: [REMAINING_WORK.md](REMAINING_WORK.md). It lists remaining required work, verification gaps, optional polish, dependencies and deferred scope.
- Existing A–F acceptance and resume order: [BRANCH_COMPLETION_MASTER.md](BRANCH_COMPLETION_MASTER.md). This remains authoritative for its existing task states and acceptance; do not flip its checks from a campaign comment.
- Branch, isolation, ownership, commit/PR and coordination agreement: [ANTIGRAVITY_BACKLOG_WORKFLOW.md](../docs/sessions/ANTIGRAVITY_BACKLOG_WORKFLOW.md).
- Per-task live side effects and grants: [ANTIGRAVITY_BACKLOG_LIVE_RUNS.md](../docs/sessions/ANTIGRAVITY_BACKLOG_LIVE_RUNS.md).
- Lane-local resume checkpoint: `C:\Users\Snoozer\teamwork_projects\architecture-renewal-intake\backlog-20261101\HANDOFF.md`. It is a cursor and evidence index only; canonical task status remains in the master/issue.

The setup PR branch is currently `docs/backlog-campaign-setup-20261101`, based on `ecc90972b4476596ca1c12756b3c7e4cddda9a45`. The branch is a setup snapshot, not a statement that setup is already merged or the sandbox is ready. Before starting, verify the latest setup PR and merged SHA in issue #78, then verify the sandbox clone has fetched that reviewed baseline. Never use this file's snapshot in place of live Git status.

## Required resume sequence

On every start, resume, continuation, or session after a gap:

1. Read current `AGENTS.md` and every applicable subtree contract for the task, then the workflow, inventory, canonical task master, issue #78 and this guide. Read the task's scoped skills and prior linked receipts; use the existing task/WF packs in BRANCH_TASK_SKILLS.md and declare the chosen binding in the capsule.
2. Inspect fresh GitHub issue/PR state and fresh local state: checkout path, branch, `HEAD`, `git status`, upstream/base SHA, active PR, owned paths, and any overlapping Codex reservation. Preserve dirty or ignored data; do not clean/reset to make the tree look ready.
3. Read the lane checkpoint. Reconcile its task, branch and receipt pins with the live checkout and issue. Record failures, interrupted processes, cost/quota, and any in-flight or uncertain action. If the checkpoint is missing or contradicts live evidence, stop the affected task and recover facts before continuing.
4. Check each task's dependencies and canonical status. Claim one bounded ready slice at a time; record its owner, allowed paths, base SHA, acceptance and evidence location in issue #78 before editing. Optional/deferred work needs an explicit disposition. The owner's current request is for Antigravity to complete the remaining inventory; the older full-episode deferral in the canonical master conflicts with that broader request. Surface and record the scope reconciliation before claiming D1/G6 or downstream work. This intent does not authorize provider/media execution.
5. Before costly or live steps, prepare the offline run card in the live-run guide and obtain the owner's exact per-task allowance. No standing live allowance exists. Do not probe a provider, browser, GUI, account or production runtime while preparing or waiting for the grant.
6. Check upstream changes at task claim, safe long-task checkpoints (target at least every 15 minutes), after interface notices, before live/costly stages, and before ready-for-review. Consume only safe, understood changes; do not auto-pull into a dirty tree or change code under an active run.
7. Execute only within the accepted task capsule. Antigravity may commit scoped changes, push its task branch and open/update a draft PR when the campaign grant is active. No direct `master` push, self-merge, release, or publication. Codex is final reviewer and sole merge owner for this campaign.
8. Return evidence and update the issue/checkpoint. Canonical task status changes only after the documented acceptance evidence exists; preserve incomplete/blocked/deferred states honestly.

The sandbox audit found no authority override/config: its default database would be checkout-local. Live shared-resource readiness is therefore unqualified, even after offline tests pass. Follow the live protocol to qualify the actual shared authority/profile/process under a task grant; do not create a replacement database to evade a lease. The initial metadata audit also found faster-whisper absent; transcription work must establish its actual dependency readiness before execution.

## Pause and resume

Pause means stop starting new work that can cause side effects; preserve the working tree and exact evidence; track in-flight jobs; reconcile or safely await external requests before deciding whether they spent allowance; and release only resources that the agent owns and can safely release. Do not abruptly kill a process or close an app when that could erase evidence or leave an external request's outcome unknown. Mark the task paused in the checkpoint and issue, with resume preconditions.

Resume by verifying current task/branch/HEAD, upstream changes, process ownership, issue/PR, checkpoint receipts, grants and cumulative counters. A paused task does not reset counters or extend an expired grant. Reconcile an unknown prior send before any retry. If code, inputs, model/runtime, configuration, action, account/profile or acceptance pin has changed, reassess the grant's validity against its written conditions; re-ask only when the change is material under those conditions. No grant is inferred from a previous task or session.

## One-line prompts

- **Start Antigravity:** “Read tasks/ANTIGRAVITY_CAMPAIGN.md and the checkpoint; verify setup, claim the next ready task, and begin within its scope.”
- **Pause Antigravity:** “Pause safely; stop new actions, preserve in-flight work and counters, and save the exact resume checkpoint.”
- **Resume Antigravity:** “Read the campaign entrypoint and checkpoint, reconcile Git/upstream/grants/uncertain outcomes, then resume the recorded task.”
- **Continue Antigravity:** “Continue the current campaign task from its checkpoint within recorded ownership and remaining allowance.”
- **New Antigravity session:** “Read tasks/ANTIGRAVITY_CAMPAIGN.md; reconstruct campaign state from issue #78 and the private checkpoint before acting.”
- **New Codex session:** “Context: Antigravity owns backlog #78; this chat handles new work and final review, with separate branches and per-task live approvals.”

## Closeout

Before the campaign is called complete, reconcile every inventory row to evidence, explicit disposition or named owner action; verify required C/D acceptance against the canonical master; inspect exact merged heads and post-merge gates; and list remaining owner decisions. A successful test suite, a closed issue, or an agent's summary alone does not establish complete product acceptance.
