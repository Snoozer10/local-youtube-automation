"""Regression coverage for two fail-closed contracts recorded in tasks/claude-feedback-coverage.md.

A3b: a typed character setup block stops the Flow orchestrator on the first occurrence,
without the generic retry/sleep path. A5: an unbound legacy human rejection only feeds
replanning when its plan and brief bindings still verify.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from youtube_automation.production import review


def _flow_harness(monkeypatch, error):
    from youtube_automation.core import utils
    from youtube_automation.visuals import flow_generator

    attempts = []
    sleeps = []

    @contextmanager
    def fake_playwright():
        yield object()

    def failing_browser(*_args, **_kwargs):
        attempts.append(1)
        raise error

    config = {"SWITCH_ACCOUNTS_ENABLED": "false", "CDP_PORT": "9222"}
    monkeypatch.setattr(flow_generator, "sync_playwright", fake_playwright)
    monkeypatch.setattr(flow_generator, "ensure_cdp_browser", failing_browser)
    monkeypatch.setattr(
        flow_generator, "get_config_value", lambda key, default=None: config.get(key, default)
    )
    monkeypatch.setattr(flow_generator.time, "sleep", sleeps.append)
    monkeypatch.setattr(utils, "active_profile_index", lambda: 2)
    return flow_generator, attempts, sleeps


def test_character_profile_mismatch_stops_flow_without_retry(tmp_path, monkeypatch):
    from youtube_automation.production.characters import CharacterProfileMismatch

    flow_generator, attempts, sleeps = _flow_harness(
        monkeypatch, CharacterProfileMismatch("character pinned to Flow profile 3")
    )
    with pytest.raises(SystemExit) as stopped:
        flow_generator._main(str(tmp_path))
    assert stopped.value.code == 1
    assert isinstance(stopped.value.__cause__, CharacterProfileMismatch)
    assert attempts == [1]
    assert sleeps == []


def test_generic_orchestration_error_still_uses_bounded_retry(tmp_path, monkeypatch):
    flow_generator, attempts, sleeps = _flow_harness(
        monkeypatch, RuntimeError("transient CDP failure")
    )
    with pytest.raises(SystemExit) as stopped:
        flow_generator._main(str(tmp_path))
    assert stopped.value.code == 1
    assert len(attempts) == 3
    assert sleeps == [5, 5]


def _legacy_feedback(tmp_path, monkeypatch, *, plan_sha256, plan_brief_sha256):
    from youtube_automation.production import shots

    brief = SimpleNamespace(source_sha256="d" * 64)
    legacy_plan = SimpleNamespace(brief_sha256=plan_brief_sha256)
    identities = {id(legacy_plan): "a" * 64, id(brief): "c" * 64}
    monkeypatch.setattr(
        shots, "ShotPlan", SimpleNamespace(model_validate_json=lambda _text: legacy_plan)
    )
    monkeypatch.setattr(shots, "fingerprint", lambda value: identities[id(value)])
    (tmp_path / "shot_plan.json").write_text("{}", encoding="utf-8")
    rejection = review.HumanPreviewRejection(
        reviewer="owner",
        overall_rating=1.5,
        plan_sha256=plan_sha256,
        preview_sha256="b" * 64,
        reasons=["The returning participant changes appearance"],
        required_next="Fresh review",
        source="owner",
    )
    assert rejection.source_sha256 is None
    (tmp_path / "human_review_rejection.json").write_text(
        rejection.model_dump_json(), encoding="utf-8"
    )
    return shots._human_quality_feedback(tmp_path, brief)


def test_unbound_legacy_rejection_feeds_replan_only_when_plan_and_brief_verify(
    tmp_path, monkeypatch
):
    feedback = _legacy_feedback(
        tmp_path, monkeypatch, plan_sha256="a" * 64, plan_brief_sha256="c" * 64
    )
    assert "HUMAN QUALITY REJECTION SUPERSEDES MODEL APPROVAL" in feedback
    assert "The returning participant changes appearance" in feedback


@pytest.mark.parametrize(
    ("plan_sha256", "plan_brief_sha256"),
    [("f" * 64, "c" * 64), ("a" * 64, "9" * 64)],
    ids=["plan_changed", "brief_changed"],
)
def test_unbound_legacy_rejection_fails_closed_when_binding_changed(
    tmp_path, monkeypatch, plan_sha256, plan_brief_sha256
):
    with pytest.raises(ValueError, match="Legacy human feedback needs verified source binding"):
        _legacy_feedback(
            tmp_path, monkeypatch, plan_sha256=plan_sha256, plan_brief_sha256=plan_brief_sha256
        )
