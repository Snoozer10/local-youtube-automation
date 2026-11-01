# Parallel backlog and feature workflow

Prepared 2026-11-01 for the owner's requested arrangement: Antigravity owns backlog delivery; the owner and Codex develop new ideas; Codex reviews Antigravity's final work.

**Campaign operating agreement:** the owner requested setup of backlog campaign [#78](https://github.com/Snoozer10/local-youtube-automation/issues/78). Read [the durable entrypoint](../../tasks/ANTIGRAVITY_CAMPAIGN.md) for current setup, lifecycle prompts and per-task live policy. The owner starts the external Antigravity session; setup does not dispatch it. This is a new scoped campaign, not an expansion of the completed architecture campaign.

## Decision

Use separate checkouts, short task branches and rolling PR review into `master`. Antigravity can own the whole backlog without keeping the entire backlog on one long-lived branch. Codex reviews each delivery slice and later performs a campaign-wide closeout.

Branches isolate source revisions. They do not isolate databases, browser accounts/profiles, providers, physical encoders, accepted media or shared caches. Git also does not send uncommitted edits from one checkout into the other.

## Pre-setup snapshot (historical)

The table records the inspected state before bootstrap. Current checkout/setup readiness comes from fresh Git state, issue #78 and the private checkpoint, not this retained snapshot.

| Surface | Observed state | Use |
| --- | --- | --- |
| Primary `image_generation` checkout | `master` at `ecc90972b4476596ca1c12756b3c7e4cddda9a45`; backlog/navigation documentation is uncommitted; unrelated `.serena/project.yml` is also modified. | Preserve production inputs and unrelated edits. Publish the reviewed backlog/setup documentation before expecting another clone to fetch it. |
| `C:\Users\Snoozer\teamwork_projects\architecture-renewal-campaign` | Independent clone, local `.git`, tracked working tree clean, branch `master` at `531da67a8f977d6b750b45f4eb477186997aabc3`; nine commits behind the primary checkout. Sparse checkout enabled. | Reuse as Antigravity's clone hub after inventory and a reviewed fast-forward. Do not discard ignored/untracked evidence or reset it. |
| Sandbox `venv\Scripts\python.exe` | Launches Python 3.11.9 with its own prefix; linked SQLite 3.45.1. No database connection was made by this inspection. | Reuse after checking dependencies, editable-install target/import origin and current isolation regressions. This check alone does not qualify the runtime for production. |
| `C:\Users\Snoozer\teamwork_projects\architecture-renewal-intake` | Existing intake directory with campaign notes/evidence and generated-data directories. | Keep past material. Give new transfers a unique campaign/task directory and a manifest; do not replace the old intake. |

The old `WORKSPACE_ROLES.md` documents are dated inputs. They contain stale clean-tree, environment and production-path assumptions; do not execute their examples or inherit their old merge authority blindly. Sparse checkout is a projection, not a security boundary, and the sandbox now has local `.runtime`, logs and run directories whose provenance must be checked before reuse.

## Campaign roles and permissions

| Actor | Responsibility | Limit |
| --- | --- | --- |
| Owner | Product decisions, human video acceptance, private credential/account actions and any required bounded live scope. | No agent invents human provenance or treats a scorecard as an owner decision. |
| Antigravity coordinator | Triage every inventory row; implement required work; verify evidence; coordinate its workers; commit/push owned task branches; open/update draft PRs; fix review findings. | No direct push to `master`, self-merge, tag/release/public upload, history rewrite, unrelated cleanup or unbounded provider work. |
| Antigravity workers | Bounded implementation, tests, investigation or review in assigned files/worktrees. | Return diffs/receipts to their coordinator; no independent commit/push or cross-lane status edits. |
| Codex | Cross-lane coordination, new-feature planning/development with the owner, final review of Antigravity PRs, integration decisions and authorized merges. | Review actual code/evidence, not the delegate's summary. A changed candidate invalidates the affected review. |

The campaign's scoped coordinator grant permits Antigravity commits, owned branch pushes and draft PRs in its own lane, overriding only the default scratch-only/no-commit restriction for this campaign. The owner selected exact per-task live allowances: prepare each live run offline, then ask for its concrete scope/caps/time/stop conditions. No standing live allowance exists. The old #31 exception permitting Antigravity merges belongs to that completed campaign; do not carry it into this one. Codex remains the merge owner here.

Antigravity owns delivery/disposition of the **entire inventory**, including investigations and decision queues. Required jobs can close with verified delivery; investigation jobs can close with evidence that no fix is needed. Optional/deferred items need an explicit disposition rather than automatic implementation. The historical full-episode deferral must be reconciled with the owner's current completion scope before starting that lane; live narration/generation still needs a concrete allowance. Human acceptance and private credential actions remain owner steps, not fabricated agent completions.

## Branch and workspace layout

```text
origin/master                 reviewed, integrated project
  +-- ag/s04-secret-scanning   one Antigravity delivery slice
  +-- ag/e02-ci-selection      another slice only if ownership is disjoint
  +-- codex/<feature-name>     the owner's new feature with Codex
```

Keep a campaign tracking issue/checklist, not a mandatory campaign code branch. Each task branches from current reviewed `origin/master`. Dependent work may wait for its prerequisite PR; use a clearly declared stacked PR only when waiting would block useful independent work.

Use the existing sandbox clone for Antigravity's task checkout. Add separate worktrees under `teamwork_projects` only for truly parallel writers. Do not create sandbox worktrees from the production checkout or share a writable virtual environment between competing dependency changes. Source and tests must import from the task checkout, not accidentally from the clone hub or primary installation.

Codex uses its own feature branch/checkout. If the primary production tree must stay pinned during a run, use an additional development checkout rather than switching the code underneath that run. Preserve the current Serena edit; do not stash/reset it merely to obtain a clean status.

## Avoid source and semantic conflicts

1. Reserve ownership for the **active task**, not all files Antigravity might ever touch across 62 rows. Record task ID, actor, owned paths, important interfaces/callers, base SHA and current PR in the task issue.
2. Start with one Antigravity implementation slice and one Codex feature. Increase Antigravity parallel writers only when packages and shared resources are demonstrably disjoint.
3. Before Codex starts a feature, check Antigravity's active ownership. Before Antigravity claims its next package, check Codex's reservation. One coordinator resolves overlapping claims; both actors must not assume a comment is an atomic lock.
4. If both need the same module/contract, sequence that work: agree the shared interface, land the prerequisite change, synchronize, then resume. Changes to different files can still conflict through a schema, API, prompt, config or accepted-media recipe.
5. The task author owns conflict resolution on their branch. Do not accept every side, weaken guards or use a whole-file overwrite to make the merge pass. Rerun affected consumer checks after resolution.
6. Shared documentation is also owned. Antigravity proposes backlog/status corrections in its PR; Codex integrates canonical cross-lane state. Each lane keeps task-specific receipts/handoffs until that merge.

## How each agent notices the other's changes

There is no continuous built-in awareness between these independent sessions. Use GitHub issues/PRs as the shared durable communication surface. Local intake is a transport for hash-bound private artifacts, not a second task tracker. Do not rely on another agent reading a local dirty file.

While an agent is active, require a synchronization check:

- before claiming a task;
- at safe checkpoints during a long task, with a target of at least every 15 minutes;
- after an explicit integration/interface-change notice;
- before a costly/live stage;
- before marking a PR ready and again before integration.

At a safe checkpoint, fetch `origin`, compare the task's recorded base SHA with `origin/master`, and inspect upstream changes to owned paths **and dependencies**. Fetching does not overwrite working files. Commit a verified checkpoint or preserve uncommitted work before integrating upstream changes. Do not auto-pull into a dirty tree or update source/dependencies in the middle of a render/provider attempt.

For published task branches, prefer merging `origin/master` into the task branch at a checkpoint, then testing and pushing normally. Do not rewrite a shared branch or force-push as routine synchronization. After any sync, refresh the base/input pins and invalidate only the affected tests, recipes, approvals or downstream outputs.

A merge/interface notice should contain: task/PR, merged SHA, changed interfaces/paths, downstream impact, required revalidation and the next ownership boundary. The active agent acknowledges the SHA it consumed. If it is not running, it reads queued updates on resume; a prompt is not an always-on watcher.

A real notification monitor can be added later if polling is insufficient. It should notify on meaningful changes and block on unresolved overlap, not silently merge code or repeatedly post unchanged status. No monitor was configured here.

## Per-task execution, commit and PR contract

Antigravity's task capsule contains: task ID; owner/role; goal and acceptance; owned paths and protected inputs; exact cwd/interpreter/base SHA; dependencies; side-effect limits; checks; result/receipt location; stop conditions.

Recommended loop:

1. Claim a ready slice and refresh the base/ownership. Read applicable contracts and bound skills.
2. Preserve protected bytes and exact preimages. Implement the narrow change and its meaningful regression proof.
3. Run focused checks, inspect the complete owned diff and secret exposure, then commit one coherent passing increment.
4. Push only the owned task branch and open a draft PR against `master` early enough to expose interface overlap.
5. After implementation stabilizes, sync/retest; attach exact head and evidence, and mark ready for Codex review.
6. Codex verifies requirements, diff, public contracts, tests, preservation, CI and exact output provenance. Findings return to the same PR; Antigravity repairs and produces a new head.
7. Codex integrates only the reviewed candidate with required passing checks. Verify the merged result, update canonical status, notify both lanes, then start the next task from current `master`.

Commit and PR titles use lowercase Conventional Commits, for example `ci: enforce offline quality gates` or `fix: preserve profile retry evidence`. No tool-name commit prefixes. Stage explicit owned paths, never blindly all dirty files. No unrelated formatting/dependency changes. Never put credentials, raw private payloads, generated media or operational state into Git to make a receipt portable.

PR description fields: problem/result; linked inventory/task IDs; owned files and affected interfaces; exact base/head SHA; commands and observed results; artifact/receipt pointers and hashes; preservation checks; failure history; limitations/owner decisions; dependencies and downstream revalidation. Label unrun checks and skipped reviews honestly. Agent work is ready-for-review, not accepted, until the review/integration gate passes.

Default merge recommendation: preserve coherent evidence-referenced commits with a merge commit. A small single-change PR with noisy fixups may be squashed by Codex if the resulting identity/evidence mapping is recorded. Never squash the entire campaign into one enormous commit. Branch changes after approval require affected review/checks again.

If both tools use the owner's GitHub account, role separation is an operating rule rather than independent account permissions. Distinct bot identities and suitable branch protections can enforce it more strongly, if desired. Do not claim self-authored PR approval is an independent GitHub approval. No repository settings were changed here.

## Source isolation versus production isolation

- Tests use test-local resource databases and receipts, including spawned children. Verify the sandbox cannot accidentally connect to the canonical production DB before running broader suites.
- Do not copy `.env`, credentials, browser profiles, a live SQLite file or all production runs into the sandbox. Import only task-selected, hash-manifested inputs after classifying sensitivity and ownership.
- Real browser/GPU/Audacity/provider activity must obey the actual shared-resource authority/lease and bounded grant. A second clone, database, account counter or branch must not bypass shared physical-resource coordination.
- Production candidates use unique task/run/output locations; accepted narration, active pointers, rejected previews and recovery journals remain protected. Canonical activation is its own explicit step after review.
- Long tests, GPU renders and app sessions need a shared execution window where resources conflict. Two isolated source trees do not double the machine's encoder, browser or provider capacity.

## Bootstrap order

1. Review and publish the current backlog/navigation documents and this operating agreement through a setup PR, excluding `.serena/project.yml`. Capture the final backlog SHA and task ID mapping. Antigravity's old clone does not yet contain these local edits. This new session file is ignored by the existing session glob: stage only the reviewed session paths with `git add -f -- docs/sessions/ANTIGRAVITY_BACKLOG_WORKFLOW.md docs/sessions/ANTIGRAVITY_BACKLOG_LIVE_RUNS.md`, and verify those exact files are present in the setup PR tree before another clone fetches it. Do not unignore or stage the entire sessions directory.
2. Inventory the sandbox's local evidence/configuration and verify no active work/process relies on its old code. Preserve it, fetch, and fast-forward the clean hub to the reviewed setup baseline. No reset/clean/delete is required.
3. Check the actual sandbox interpreter, dependency/import origin, sparse projection, local state and test resource isolation. Reuse the existing environment where valid; repair only a demonstrated gap.
4. Use campaign issue #78 and initial jobs #79 (owner-only S01), #80 (first offline source slice S02) and #81 (E02 follow-up). Record Codex's current feature reservation and refresh the actual issue/PR states before claiming work.
5. Create the first Antigravity task branch from that baseline. Start with S01/S02 exposure handling and the status/CI backlog, with owner-only account steps surfaced separately. Do not dispatch all 62 rows at once.
6. Give Antigravity the brief, current backlog hash, ownership reservation and exact workspace. The owner starts it. Ask for an initial preflight receipt before implementation, then ready PRs and compact blocker notices rather than progress spam.

## Suggested kickoff message

> You are the backlog delivery coordinator for this repo. Read the current root/subtree contracts, tasks/REMAINING_WORK.md and docs/sessions/ANTIGRAVITY_BACKLOG_WORKFLOW.md. Work only in the verified teamwork_projects sandbox, using short owned task branches from current reviewed master. This task authorizes your coordinator to implement and test the selected backlog slices, make scoped Conventional Commits, push your task branches, and create/update draft PRs. Your workers return diffs/evidence only. Codex is the final reviewer and merge owner; do not merge or push master. Inventory and report optional/deferred/owner-only decisions honestly. Preserve accepted media, prior attempts, recovery state and cumulative accounting. Do not infer provider/browser/publication/credential-account grants. First return your workspace/HEAD/interpreter/import-isolation preflight, proposed first slice, owned paths/dependencies and protected-input pins. Then execute within that accepted scope and report exact evidence. At checkpoints consume upstream notices and coordinate overlaps; never overwrite the primary checkout or another lane's work.

## Completion

Review continuously, then perform one campaign-wide acceptance cross-check over the final integrated `master`: inventory dispositions, all required C/D product gates, current source/package checks, preservation/recovery and every remaining owner decision. A new feature changes the backlog only through an explicit scope/update record. Mark blocked, deferred and optional honestly; do not manufacture “all done” from successful code tests.

Sources: [remaining work](../../tasks/REMAINING_WORK.md), [canonical task master](../../tasks/BRANCH_COMPLETION_MASTER.md), [existing delegation template](ANTIGRAVITY_DELEGATION_TEMPLATE.md), [engineering workflows](../agents/workflows.md), [Git worktrees](https://git-scm.com/docs/git-worktree), [upstream PR synchronization](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/keeping-your-pull-request-in-sync-with-the-base-branch), [merge strategies](https://docs.github.com/en/pull-requests/reference/pull-request-merges).
