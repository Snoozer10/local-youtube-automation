# Historical adaptive visual engine hardening checklist

Current execution/status: [master](BRANCH_COMPLETION_MASTER.md), [typing closeout](../docs/sessions/STRICT_TYPING_REVIEW_20261022.md) and [F1 dispositions](../docs/sessions/F1_REVIEW_DISPOSITIONS_20261022.md). Engineering review/gates are complete; formal exact-head review/CI/merge remain. The checklist below is historical.

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
