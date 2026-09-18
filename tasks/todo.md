# Active adaptive visual engine work

See [adaptive-visual-tasks.md](adaptive-visual-tasks.md).

---

# Todo: flow_image_generator.py hardening (Tiers 1-3)

## Tier 1 — silent TargetClosedError death
- [x] Task 1: Graceful browser close in main() finally + KeyboardInterrupt handler
- [x] Task 2: select_gemini_model resilient to TargetClosedError
- [x] Task 3: Planning calls (roadmap + plan_all_chunks) under retry guard

## Tier 2 — don't kill batch for one failure
- [x] Task 4: Wrap setup_flow_characters_and_scenes in try/except
- [x] Task 5: Fix editor-mount URL race

## Tier 3 — logical bugs
- [x] Task 6: Stronger is_flow_page_healthy
- [x] Task 7: Input-box selector: drop bare textarea fallback
- [x] Task 8: Chaining off-by-one + stale-skip integrity
- [x] Task 9: Empty-ts naming collision
- [x] Task 10: Recovery/fatal counter + outer-loop exit semantics
- [x] Task 11: Remove dead wake_up_page duplicate pass

## Verification
- [ ] python -m pytest tests/unit -v
- [ ] ruff check . --fix && ruff format --check .
- [ ] mypy .
