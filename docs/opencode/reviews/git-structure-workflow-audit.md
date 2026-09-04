**Git Structure / Workflow Audit — `image_generation`**

Using `git-workflow-and-versioning` — read-only inspection.

### 1. Current Structure

- **Trunk:** `master` (`origin/master` HEAD=`f11efbe`). You call it `master` not `main` — trunk-based, always deployable. Correct.
- **Local HEAD:** `893a13c` — **6 commits ahead** of `origin/master` (`origin/master..HEAD`):
  ```
  84f4084 feat(sync): canonical timeline.json (#14)
  79eb323 feat(compiler): hardware ladder (#15)
  05ff9b7 feat(prompt): 3-span planner (#16)
  3698a89 feat(compile): checkpoint hash (#17)
  baa68ec feat(visuals): text collision gate (#18)
  893a13c feat(pipeline): DSP + quality gates (#19)
  ```
  History is clean/atomic, conventional commits — good. But **unpushed**.

- **Working tree:** Dirty. 14 modified + 30+ untracked (`git status`):
  - Modified: `timeline_engine.py`, `prompt_planner.py`, `validator.py`, `compile_video.py`, `flow_image_generator.py`, 3 test files, `AGENTS.md`/`GEMINI.md`/docs. `git diff --stat HEAD` = +545/-441 across single unstaged set — violates atomic commit rule.
  - Untracked: `.cursorrules`, `*.bak`, `check_*.py`, `poll*.py`, `relay_omni/`, `brief_*.txt`, `docs/benchmarks/`, `tests/unit/test_post_encode_validation.py` — mix of artifacts, experiments, real code. Many likely should be ignored or committed separately.

- **Branches:** `Updates_V6` (0e697ba), `prototype/ken-burns-per-beat` (9e572f4, 1 ahead), `research/audit-sync-quality-pipeline` (c0291be), `worktree-spec-debate-delegation`/`worktree-sync-adr-0004-0005` (both at 40d58c7, stale). Remotes track but local diverges. No feature branches active for current work.

- **Worktrees:** `git worktree list` = 1 entry (this dir). No parallel worktrees despite multi-stream branches — missed isolation opportunity.

- **Tags/Releases:** `git tag -l` = empty. `git describe` = `fatal: No names found`. **Zero tags ever.** `pyproject.toml:4` declares `version = "4.0.0"` but never tagged/published from git.

- **Changelog:** No `CHANGELOG.md`, no `docs/CHANGELOG*`, no `releases/` content. `git log` ≠ changelog.

- **Hygiene:** `.gitignore:1` solid (venv, .env, checkpoints, logs, browser profiles, `youtube_runs/`, `.agents/.gemini/.opencode` excluded). Pre-commit config exists (`.pre-commit-config.yaml`) but dirty tree not staged.

### 2. How to Organize Parallel Streams

You already have the shape — not using it:

```
master (deployable trunk)
 ├── feature/collision-gate     ← could be baa68ec branch, 1-3 day life
 ├── feature/timeline-hash      ← 3698a89
 ├── fix/validator-timestamps   ← 8b911b1 pattern
 └── research/audit-sync        ← research/audit-sync-quality-pipeline (correct)
```

Skill recommendation: **trunk-based + worktrees**, not long-lived branches.

```bash
git worktree add ../image-gen-collision feature/text-collision-gate
git worktree add ../image-gen-prompt    feature/prompt-window
git worktree add ../image-gen-encode    feature/encode-ladder
# each has own branch, own venv, parallel agents, no checkout thrashing
# merge within 1-3 days, delete worktree → git worktree remove ../image-gen-collision
```

Your `worktree-spec-debate-delegation` branches are stale at `40d58c7` (6 commits behind HEAD) — archive or rebase before reuse. Don't let branches drift >3 days.

### 3. Release / Semver / Tagging / Changelog — Do You Need It?

**Yes, now.** Project has consumers (pip package `youtube-automation-pipeline`, README published). Skill checklist fails all 3 release gates:

| Gate | Status |
|------|--------|
| Version bump matches change | `pyproject.toml:4` stuck at `4.0.0` while HEAD has 6 `feat:` commits since `f11efbe` — at minimum MINOR |
| Tag immutable + version from tag | No tags. Version hand-edited, out of sync |
| Curated changelog | Missing. `git log --oneline` is not a changelog |

**Decision:** 
- 6 commits are additive feats (sync engine, compiler, prompt planner, checkpoint hash, text gate, DSP) — suggests `4.1.0` if backward-compatible, `5.0.0` if `timeline.json` schema / `validator.py:14` / `prompt_planner.py:107` break consumers. You must decide breaking vs additive — assume major if unsure.
- Writes since `893a13c` (validator, timeline_engine changes in dirty tree) are not yet committed — **don't cut release until tree clean**.

### 4. What You Should Do Next (Priority Order)

**P0 — Stabilize trunk (before anything else):**
1. Triage dirty tree: `git diff --stat HEAD` split into atomic commits, not one giant commit:
   - `refactor:` or `fix:` for `timeline_engine.py:14` + `tests/unit/test_timeline_engine.py:17`
   - `feat:` for `prompt_planner.py:107` + related tests
   - `fix:` for `validator.py:78` + `tests/unit/test_validator.py:41`
   - `feat:` for `compile_video.py:156`
   - `docs:` for `AGENTS.md/GEMINI.md/CONTINUITY.md`
   - Delete or `.gitignore` artifacts (`*.bak`, `check_*.py`, `poll*.py`, `relay_omni/`, `events_tail.txt`)
2. `git diff --staged | grep -i password\|secret\|token` + `pytest` + `ruff` before each commit
3. `git push origin master` — you are 6 commits ahead, risk of loss

**P1 — Parallel work hygiene:**
4. Create worktrees for current dirty work instead of piling on master: e.g. `git worktree add ../imagegen-validator fix/validator-timestamp`
5. Delete stale `worktree-*` branches or rebase to HEAD

**P2 — Release ceremony (after P0 pushed & CI green):**
6. Bump `pyproject.toml:4` to `4.1.0` (or `5.0.0` if breaking) — derive from tag later
7. Add `CHANGELOG.md` grouped `Added/Changed/Fixed` (e.g.):
   ```markdown
   ## [4.1.0] - 2026-09-04
   ### Added - Timeline hash checkpoint invalidation, 3-span prompt planner, text collision gate, DSP normalization
   ### Fixed - validator timestamp schema
   ```
   Write entry *with* the change, not at release time.
8. `git tag -a v4.1.0 -m "Release 4.1.0" && git push origin v4.1.0`