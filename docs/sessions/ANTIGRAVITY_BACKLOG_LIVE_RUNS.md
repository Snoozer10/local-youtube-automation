# Antigravity backlog live-run protocol

Prepared 2026-11-01. This protocol records the owner's standing policy: **prepare each live task offline, then ask the owner for that task's exact allowance.** No standing live allowance exists. This document grants no provider, browser, GUI, production, credential, publication, or spend authority.

## Scope and grant model

“Live” includes any action that can contact an external provider/account, send a prompt or request, launch or operate a real browser/GUI/editor, run a production pipeline, generate or publish media, mutate canonical runtime state, consume paid quota, or use a credential against a service. A dry-run or isolated test with synthetic media/test-local databases is offline only when its exact path proves no real provider/app/shared-production side effect; a flag named dry-run is insufficient.

Campaign-authorized Git/GitHub coordination is a separate source-control grant: fetch, owned task-branch pushes, task issue/draft-PR updates, CI-status reads and ordinary PR checks may use the existing approved CLI/connector authentication without a project live-run allowance. These operations do not authorize direct master pushes, Antigravity merges, account/credential changes, release/public-media publication or project provider/browser/GUI execution. Never expose authentication values.

The coordinator prepares a task-specific request and asks the owner for an exact allowance before any live probe or attempt. The grant must be attributable to the owner and retained in the private task checkpoint/grant record; issue #78 receives only a sanitized approval reference and status. It specifies:

- task ID and unique run ID; exact allowed action(s), target/service/account class and environment;
- source commit, input hashes, model/provider version or endpoint, runtime/interpreter, relevant profile/config pins and output destination;
- explicit maximum attempts/actions, including retries, repair calls, failover, critic/reviewer calls and uncertain sends; any paid-spend cap is separate and explicit;
- execution/time window and expiry, if any; output isolation and preservation rules;
- acceptance evidence, stop conditions, and what requires a fresh owner decision.

An allowance is cumulative for its task/run and does not replenish on pause, resume, new session, branch change or a new chat. Count every initiated live attempt, including retries; record successful, failed-before-send, failed-after-send and uncertain outcomes separately. Never treat an ambiguous transport/UI result as zero usage. Reconcile service receipts or other safe evidence before retrying. An expired grant is unusable. If a pinned input/code/runtime/config/profile/action changes, first test the grant's written validity conditions against fresh evidence; re-ask only for a material scope or pin change covered by those conditions. Do not broaden a grant by interpretation.

If the action itself cannot be bounded, stop and report the missing evidence. The offline run card may request a bounded, zero-send readiness/discovery phase within the same task grant. Record unknown live facts explicitly; perform no probe before approval. Generation begins only after current ownership, profile/model, lease, output, counter and send-boundary checks pass; otherwise stop and preserve evidence. The user decides whether to revise scope or grant.

## Offline preparation and owner request

Before asking, complete an offline-only run card with:

| Field | Required record |
| --- | --- |
| Task | Inventory/master ID, goal, acceptance and dependencies; unique run ID. |
| Source | Absolute checkout, branch, commit SHA, dirty paths, owned files and upstream base SHA. |
| Inputs | Exact path/hash for every input; sensitivity and owner; protected/preexisting evidence. |
| Runtime | Interpreter/executable, version, cwd, import origin, dependency state, OS and relevant process/helper identity. |
| Live action | Exact entrypoint/UI steps, service/model/profile, request or operation type, and proven send/action boundary. List retries, failover and critic calls. |
| Config | Required key **names** and source mechanism; non-secret config path/hash; state which values remain local. Never include secret values in issue, brief or receipt; relevant non-secret settings may be recorded. |
| Allowance request | Exact units/actions and max attempts, any distinct spend cap, time window/expiry, and cumulative prior used/succeeded/failed/uncertain counts. |
| Isolation | Unique run/output/receipt directory, shared resources/lease, no-overwrite and recovery plan, allowed local config/media inputs. |
| Acceptance | Observable outputs and checks, hashes/receipt schema, human review needed, downstream invalidation. |
| Stops | Any cap reached, changed pin, permission/identity mismatch, missing counter/receipt, refusal, unexpected output, crash/timeout with unknown send status, contamination, rejected candidate, or unmet prerequisite. |

Present the completed card to the owner as a narrow request: “For task [ID]/run [ID], authorize [actions] against [target] using [pins] for at most [exact allowance], with [spend cap if applicable], until [time/expiry]. Outputs go to [isolated path]; stop on [conditions].” Wait for the owner's exact answer. A request, silence, prior session, task checklist, test, or campaign issue does not itself authorize the action.

## Configuration and data

- Do not bulk-copy or attach a complete `.env`, credentials file, browser profile, production database or all production runs. A selected run may be staged only with a reviewed file inventory, sensitivity check, exact hashes and a verified copy under the task scope. Do not print secret values in prompts, terminal summaries, logs, checkpoints, Git, or external services.
- Determine required config key names from the pinned code and offline inspection. Supply the least required values through the already-approved local secret mechanism; record only secret key names and source identity, plus hashes of non-secret config/input manifests. In this repo core/utils.py loads the checkout .env with override=False, so an allowlisted child-process environment can supply required values without copying production .env. update_config_value mutates the checkout .env: do not use it to provision or change canonical settings incidentally.
- A local video/config file may be supplied only when the task requires it and the owner approves the exact file. Hash-pin it, classify sensitive fields, and redact/export a minimal copy when possible. For adaptive review, the code prefers the run-local video_config.txt before the repository default; use a reviewed run-local copy rather than relying on an old ignored video_config.local.txt. Do not silently edit a canonical config or treat a changed config as covered by an old pin.
- Copy only task-selected inputs after sensitivity/ownership review and hash manifest. Put outputs, raw responses, failures, screenshots and receipts in a unique isolated task/run location. Preserve rejected candidates and recovery journals. Never activate or publish outputs under a generation grant alone.

## Shared-resource and dependency readiness

The inspected sandbox has an editable install pointing to its own source, but no authority override/config. Without a verified live-child override it would discover a checkout-local .runtime/adaptive.sqlite3. That does not coordinate the same physical browser, clipboard, Audacity or encoder with the primary checkout. Before a live task, qualify the actual authority target/schema and all compatible clients under the task grant, plus the exact owned process/profile/listener/lease. YOUTUBE_AUTOMATION_AUTHORITY_DB is the supported environment pointer; conflicting config must fail closed. Never create a replacement DB or select an independent authority merely to avoid a busy lease. Keep test-local authority redirection confined to offline tests.

Browser logins live in the approved owned profile, not in a copied .env. Do not clone profiles/cookies. The initial dependency audit found faster-whisper absent; a task needing transcription must resolve that prerequisite through a scoped environment change and validation before a live attempt. Metadata and offline isolation tests do not qualify live readiness.

## Execution, accounting and interruption

Immediately before each allowed attempt, recheck task status, grant validity, exact pins, allowance remaining, resource ownership and output isolation. Write a pre-attempt journal entry. Afterward, record the outcome and raw receipt/hash before further work. Do not exceed any per-action or cumulative cap, even if a response is partial or a retry seems harmless. Do not substitute another provider/model/profile or broaden the output/action because the original is unavailable.

If an attempt fails, preserve its evidence, classify whether it reached the send/action boundary, and inspect available receipts/process state. A pre-send failure may be reported separately only with evidence that no action was submitted; it still counts as an initiated live attempt against the requested attempt cap. A request with an uncertain outcome remains uncertain and consumes its slot unless the owner explicitly grants a revised allowance after reconciliation. Do not blindly retry a timeout, wrapper interruption, UI disconnect or process exit.

On pause, stop new sends/side effects and record process IDs/ownership, in-flight request status, exact last confirmed event, cumulative counts, spend evidence and safe next step. Do not kill a possibly active request or close an owned application if doing so could lose evidence or make its outcome ambiguous. Resume only after fresh state reconciliation; do not reset the ledger. On stop condition, preserve artifacts, halt dependent actions, report the precise issue and wait for owner direction.

## Receipt and human review

For each run preserve an append-only ledger with UTC timestamp, task/run IDs, actor, action/entrypoint, source/input/runtime/config pins, grant reference, attempt ordinal, pre-send journal, result (success/failure/uncertain), service/process receipt IDs, spend/quota evidence if available, output hashes, failures, stop reason, and reviewer/owner disposition. Store raw receipts in the task's authorized local evidence location; publish only sanitized references and hashes. Reconcile the ledger to the campaign issue and lane checkpoint at pause and closeout.

Technical schema, passing tests, generated images/video, a model score, or an agent's self-review does not constitute owner acceptance. Bind editorial review to exact candidate hashes; preserve rejection and require fresh review after a candidate changes. Publication, activation, credential/account changes and canonical runtime mutation require their own explicit owner scope unless explicitly included in a valid grant.

## Resume checklist

Before continuing a live task, verify fresh issue/PR and Git state; checkpoint/run-ledger integrity; branch/HEAD and all code/input/model/runtime/profile/config pins; grant scope and any expiry; remaining attempt and spend caps; unresolved/uncertain outcomes; process and shared-resource ownership; output path and recovery state; and acceptance/review status. A pin mismatch or stale receipt blocks the affected action until it is safely assessed. Re-ask the owner only when the written grant conditions require it or the requested scope/allowance changes.

## References

- [Campaign entrypoint](../../tasks/ANTIGRAVITY_CAMPAIGN.md)
- [Backlog/feature workflow](ANTIGRAVITY_BACKLOG_WORKFLOW.md)
- [Delegation brief and historical evidence controls](ANTIGRAVITY_DELEGATION_TEMPLATE.md)
- [Remaining-work inventory](../../tasks/REMAINING_WORK.md)
- [Canonical task master](../../tasks/BRANCH_COMPLETION_MASTER.md)
- [Campaign issue #78](https://github.com/Snoozer10/local-youtube-automation/issues/78)
