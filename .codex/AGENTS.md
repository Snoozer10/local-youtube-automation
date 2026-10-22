# Purpose
Branch-local Codex guidance and configuration.

## Ownership
- config.toml contains project settings only; user/global configuration is independent.
- ../skill-lock.json owns skill source/hash inventory, task bindings and archive integrity. ../tasks/BRANCH_TASK_SKILLS.md is its human-readable invocation map.

## Local Contracts
- Invoke the skills explicitly bound to the current task; do not implement a per-task enable/disable controller or alter global settings.
- Preserve unrelated project skills outside discovery under ../.agents/skill-archive/; validate hashes and existing destinations before any restoration.
- Project skills.config parsing is not proof of enforcement: local Codex 0.160 advertised excluded project skills. Current chat catalogs are not hot-unloaded by filesystem changes.
- Keep core MCP tools available; skill instructions do not change permissions, task acceptance or provider caps.

- Do not run bulk skill updates or setup installers that restore archived packs. Review intended changes against the root lock and preserve upstream installer provenance before any restoration.
## Work Guidance
- Follow root routing and the current task/skill map. Read only the selected skill bodies and necessary references.

## Verification
- Validate all 52 task bindings, active SKILL.md pins and archived file hashes against the root lock.
- codex --strict-config doctor --json checks configuration parsing/health only; do not use it as proof of skill exclusion.

## Child DOX Index
- None.
