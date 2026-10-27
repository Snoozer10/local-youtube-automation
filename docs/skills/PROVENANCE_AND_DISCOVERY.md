# Canonical Skill Provenance and Platform Discovery Audit

This document records the canonical provenance, active task bindings, consolidation status, restoration mappings, and platform discovery gaps for skills in this repository (Issue #39).

---

## 1. Authority and Lock Files

The repository maintains two complementary skill lock contracts:

1. **`skill-lock.json` (Project Skill Lock)**:
   - **Scope**: Project-level execution and task bindings.
   - **Bindings**: 52 explicit task bindings across 24 bound skills.
   - **Active Inventory**: 109 catalogued project skills.
   - **Archive Register**: 21 archived historical skills stored under `.agents/skill-archive/`.
   - **Policy**: `scope=project_only`, `invocation=explicit_per_task`.

2. **`skills-lock.json` (Package Manager Lock)**:
   - **Scope**: Upstream provenance and content hash verification.
   - **Registry**: 29 upstream repositories (e.g., `mattpocock/skills`, `sultanalsafran/agent-skills`).
   - **Verification**: SHA-256 `computedHash` per skill path.

---

## 2. Active Platform Discovery Surfaces

Different agent platforms enforce distinct discovery surfaces:

| Platform | Primary Discovery Surface | Status / Constraints |
| :--- | :--- | :--- |
| **Claude Code** | `.claude/skills/<skill-name>/SKILL.md` | Active & tracked in Git (14 skills). |
| **Antigravity (CLI / IDE / App)** | Workspace: `.agents/skills/<skill>/`<br>Global: `~/.gemini/config/skills/` | Workspace `.agents/` is gitignored by project convention. Global skills discovered via host configuration. |
| **Codex** | `.agents/skills/<skill-name>/` | Prior versions (<0.160) do not enforce project-level skill selection (explicit platform gap). |

---

## 3. Bound Skills and Task Coverage

The 24 bound skills defined in `skill-lock.json` cover all 52 project tasks:

1. `api-and-interface-design`
2. `arabic-copywriting-dialects`
3. `audio-dsp`
4. `audio-mixing-mastering`
5. `ci-cd-and-automation`
6. `code-review-and-quality`
7. `context-engineering`
8. `docs-guard`
9. `documentation-and-adrs`
10. `faster-whisper`
11. `ffmpeg`
12. `git-workflow-and-versioning`
13. `observability-and-instrumentation`
14. `planning-and-task-breakdown`
15. `research`
16. `security-and-hardening`
17. `serena`
18. `shipping-and-launch`
19. `source-driven-development`
20. `systematic-debugging`
21. `test-driven-development`
22. `test-guard`
23. `verification-before-completion`
24. `windows-desktop-e2e`

---

## 4. Bounded Consolidation and Redundancy Verification

Inspection of candidate copies across discovery roots established:

- **`.claude/skills/` Cohort**: 14 active, non-redundant skills (`ask-matt`, `code-review`, `domain-modeling`, `gem-devops-guidelines`, `grill-me`, `grill-with-docs`, `grilling`, `implement`, `setup-matt-pocock-skills`, `tdd`, `to-spec`, `to-tickets`, `wait-what`, `wayfinder`).
- **`grilling` vs `grill-me`**: Both are preserved because `grill-me` is the interactive interview tool while `grilling` represents the underlying execution capability; each is bound to distinct task entrypoints.
- **Archive Isolation**: The 21 archived entries in `.agents/skill-archive/` have verified SHA-256 receipts and remain isolated without duplicate active copies in `.claude/skills/`.

---

## 5. Restoration Mapping and Re-check Procedure

To restore an archived skill or reconstruct a verified copy from canonical provenance:

1. Look up the upstream source repository and relative path in `skills-lock.json`.
2. Verify the downloaded `SKILL.md` against `computedHash`.
3. If restoring from `.agents/skill-archive/<cohort>/<skill>`, verify the file bytes match the recorded checksum in `skill-lock.json: archive_integrity`.
4. Copy to the platform-specific directory (`.claude/skills/<skill>/` or `.agents/skills/<skill>/`).
5. Confirm discovery by running the test suite: `pytest tests/unit/test_skill_discovery_and_lock.py`.

---

## 6. Explicit Platform Limitations and Gaps

1. **Codex Selection Enforcement**: Codex versions prior to 0.160 do not enforce project-level skill selection at invocation time.
2. **Gitignored Workspace Directory**: The `.agents/` folder is explicitly excluded in `.gitignore`. Consequently, workspace skills on AGY/Codex rely on local filesystem presence rather than tracked Git revisions.
3. **No Dynamic Hot-Reload**: Active conversational sessions do not hot-reload skill catalog changes made during a task; fresh sessions are required to reflect catalog modifications.
