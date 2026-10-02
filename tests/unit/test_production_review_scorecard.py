import pytest

from youtube_automation.production.review import PreviewScorecard


def scorecard(**updates):
    data = {
        "plan_sha256": "a" * 64,
        "preview_sha256": "b" * 64,
        "reviewer": "editor",
        "semantic_match": 4,
        "hook_strength": 4,
        "attractiveness": 4,
        "progression": 4,
        "continuity": 4,
        "readability": 4,
        "motion": 4,
        "notes": "Reviewed against the complete preview on a mobile-sized player.",
    }
    return PreviewScorecard(**(data | updates))


def test_preview_scorecard_requires_every_quality_dimension_to_pass():
    assert scorecard().hook_strength == 4
    with pytest.raises(ValueError, match="Every preview quality dimension"):
        scorecard(attractiveness=3)
