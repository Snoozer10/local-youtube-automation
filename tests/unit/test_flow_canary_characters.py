from youtube_automation.visuals.flow_generator import (
    StoryboardFrame,
    _select_canary_storyboard,
    _storyboard_character_ids,
)


def _frame(index, shot_id, asset_id, character_ids, reference_asset_id=None):
    return StoryboardFrame(
        index=index,
        timestamp="[00:00]",
        prompt_text="scene",
        raw_payload={
            "adaptive_shot": {
                "shot_id": shot_id,
                "asset_id": asset_id,
                "character_ids": character_ids,
                "reference_asset_id": reference_asset_id,
            }
        },
    )


def test_canary_characters_follow_selected_dependency_closed_frames_in_canonical_order():
    reference = _frame(1, "reference", "asset-reference", ["reference-character"])
    target = _frame(2, "target", "asset-target", ["target-character"], "asset-reference")
    unrelated = _frame(3, "unrelated", "asset-unrelated", ["unrelated-character"])
    frames = [reference, target, unrelated]

    selected = _select_canary_storyboard(frames, ["target", "reference"])

    assert selected == [reference, target]
    assert _storyboard_character_ids(selected) == {"reference-character", "target-character"}
