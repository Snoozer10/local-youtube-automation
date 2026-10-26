# Engineering guidance consumers

## Purpose
Route shared engineering guidance to its single owner and maintain the navigation surface for agent-facing procedures.

## Ownership
- `issue-tracker.md`: GitHub issue and specification operations.
- `triage-labels.md`: canonical triage-role mappings.
- `domain.md`: project vocabulary and architecture-decision-record discovery.
- `workflows.md`: feature, debugging and release routes, research/delegation proportionality and verification.
- Root `AGENTS.md`: shared contract and routing map.
- `GEMINI.md` and `CLAUDE.md`: platform imports of root instructions.

## Local Contracts
- Use GitHub Issues for `Snoozer10/local-youtube-automation` with the configured five triage labels.
- Keep project terms in root `GLOSSARY.md`; keep architecture decisions in `docs/adr/`.
- Skill sources, hashes and archive mappings are owned by `skill-lock.json`; task selection is owned by `tasks/BRANCH_TASK_SKILLS.md`.
- Platform adapters import root guidance; this directory owns shared procedures and consumer links, not duplicated skill entry points.

## Work Guidance
- Update this index when a direct guidance file is added, removed, renamed or changes ownership.
- Preserve issue-tracker and triage-label procedures when revising routes.

## Verification

## Child DOX Index
