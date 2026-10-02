# Active adaptive visual engine work

See [adaptive-visual-plan.md](adaptive-visual-plan.md).

---

# Implementation Plan: flow_image_generator.py Hardening

## Overview
Fix the silent `TargetClosedError` death during Gemini planning, batch-kill on
character pre-flight failure, and a set of correctness bugs in the Flow image
rendering loop. All three tiers applied in one pass, verified with the repo's
green baseline (unit tests, ruff, fmt, mypy).

## Architecture Decisions
- Tier 1: graceful browser teardown + planning-phase retry (root causes RC1/RC2/RC3)
- Tier 2: character/scene pre-flight made non-fatal + editor-mount race fix (RC4)
- Tier 3: correctness fixes (health check, input selector, chaining, naming, exit semantics)
- Keep changes minimal; no signatures of exported helpers change; preserve backward compat with checkpoint files.

## Task List

### Tier 1 — silent TargetClosedError death
- [x] Task 1: Graceful browser close in main() finally + KeyboardInterrupt handler
- [x] Task 2: select_gemini_model resilient to TargetClosedError
- [x] Task 3: Planning calls (roadmap + plan_all_chunks) under retry guard

### Tier 2 — don't kill batch for one failure
- [x] Task 4: Wrap setup_flow_characters_and_scenes in try/except
- [x] Task 5: Fix editor-mount URL race

### Tier 3 — logical bugs
- [x] Task 6: Stronger is_flow_page_healthy
- [x] Task 7: Input-box selector: drop bare textarea fallback
- [x] Task 8: Chaining off-by-one + stale-skip integrity
- [x] Task 9: Empty-ts naming collision
- [x] Task 10: Recovery/fatal counter + outer-loop exit semantics
- [x] Task 11: Remove dead wake_up_page duplicate pass

### Checkpoint: Complete
- [ ] Unit tests pass (`python -m pytest tests/unit -v`)
- [ ] `ruff check . --fix`, `ruff format --check .`
- [ ] `mypy .`

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Restructuring main() while-loop | Med | Minimal finally/clause edits; preserve failover flow |
| Planning retry re-submits prompts | Med | Retry only roadmap/plan_all_chunks (idempotent via manifest/checkpoint) |
| Health check too strict | Med | Requires prompt bar + crash-pattern absence; fallback counts |