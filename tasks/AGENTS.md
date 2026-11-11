# Purpose
Implementation plans, progress checklists and verification records.

## Ownership
- BRANCH_COMPLETION_MASTER.md owns current branch-completion task status, dependencies, acceptance evidence and resume order. Update it with linked execution records; check a task only after its acceptance passes for current inputs. HANDOFF carries the short cursor.
- Adaptive visual plan/checklist record feature scope and historical acceptance snapshots (current branch acceptance stays in BRANCH_COMPLETION_MASTER.md); adaptive-visual-usage.md preserves historical pilot workflow notes and dated A75/rollout evidence, while current user-facing staged commands, outputs, and limits are owned by docs/usage/adaptive-mode.md under docs/usage/AGENTS.md. Preserve historical plans.
- professor-visual-playbook.md owns timestamped reference-frame observations and the Professor visual repair/acceptance method; link it from the adaptive checklist. Distinguish sampled frames from complete viewing and design recommendations from observed creator workflows.

- BRANCH_TASK_SKILLS.md maps each branch task and workflow finding to explicitly invoked project skills; root skill-lock.json owns source/hash/archive data. Skill bindings never close task acceptance.

- REMAINING_WORK.md owns the dated user-facing inventory of remaining project work, missing evidence, critique and optional improvements. It links existing task/issue owners and does not replace BRANCH_COMPLETION_MASTER.md acceptance status.

- ANTIGRAVITY_CAMPAIGN.md owns the backlog campaign entry point, task-specific delegation grant, start/pause/resume protocol and operator prompt index. It links the GitHub campaign issue and private checkpoint; existing master/feature acceptance and runtime journals remain authoritative at their scopes.

## Local Contracts
- Check tasks only after implementation and verification; distinguish live checks from offline evidence.
- Generate test node identifiers from actual runtime collection (`pytest --collect-only -q`), never from convention or memory.
- Bind causal explanations of test skips or failures to exact raw log receipts; never infer cause from matching totals.
- Make sanitized review summaries accessible in tracked documentation or PR comments; retain raw private/secret-bearing receipts, byte archives, and operational state in ignored private storage and link only sanitized evidence.
- Refresh remote PR open/merged status, master, and branch pins before committing, pushing, or reporting handoffs.
- Link active work from plan.md and todo.md.

## Work Guidance
- Follow the shared root AGENTS.md contract and applicable local AGENTS.md files; platform adapters load the shared contract and cannot override it.

## Verification
- Verify linked task files exist and completed items have evidence.

## Child DOX Index
- None.
