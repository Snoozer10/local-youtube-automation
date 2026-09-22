from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_legacy_supervisor_rejects_adaptive_before_state_mutation(tmp_path, monkeypatch):
    import run_agency

    (tmp_path / "episode_brief.json").write_text("{}")
    changed = MagicMock()
    monkeypatch.setattr(run_agency, "get_pipeline_state", changed)
    with pytest.raises(ValueError, match="explicit editorial review"):
        run_agency.process_folder(str(tmp_path))
    changed.assert_not_called()


def test_invalid_audio_directory_fails_before_touching_audacity(tmp_path, monkeypatch):
    from youtube_automation.audio import audacity_client

    mutation = MagicMock()
    monkeypatch.setattr(
        audacity_client.sys, "argv", ["automate_audacity.py", str(tmp_path / "missing")]
    )
    monkeypatch.setattr(audacity_client.subprocess, "run", mutation)
    monkeypatch.setattr(audacity_client, "clear_audacity_temp_data", mutation)
    with pytest.raises(ValueError, match="existing run"):
        audacity_client.main()
    mutation.assert_not_called()


def test_flow_entrypoint_holds_shared_browser_lease(tmp_path, monkeypatch):
    from youtube_automation.production import ledger
    from youtube_automation.visuals import flow_generator

    database = tmp_path / "jobs.db"
    (tmp_path / "episode_brief.json").write_text("{}")
    monkeypatch.setattr(ledger, "resource_database", lambda: database)

    def worker(folder):
        assert Path(folder) == tmp_path
        assert ledger.Ledger(database).claim("browser", "other", "competitor") is None

    monkeypatch.setattr(flow_generator, "_main", worker)
    flow_generator.main(str(tmp_path))
    assert ledger.Ledger(database).status()[0]["state"] == "SUCCEEDED"


def test_stage_recipe_changes_with_inputs_not_outputs(tmp_path):
    from youtube_automation.production import cli

    args = SimpleNamespace(
        stage="plan",
        channel_profile=None,
        media_file=None,
        start_seconds=None,
        end_seconds=None,
        reviewer=None,
    )
    (tmp_path / "episode_brief.json").write_text("brief", encoding="utf-8")
    (tmp_path / "timeline.json").write_text("timeline", encoding="utf-8")
    first = cli._stage_recipe(tmp_path, args)
    (tmp_path / "shot_plan.json").write_text("output", encoding="utf-8")
    assert cli._stage_recipe(tmp_path, args) == first
    (tmp_path / "timeline.json").write_text("changed", encoding="utf-8")
    assert cli._stage_recipe(tmp_path, args) != first


def test_generation_stage_recipe_includes_effective_flow_model(tmp_path, monkeypatch):
    from youtube_automation.production import cli

    args = SimpleNamespace(
        stage="generate",
        channel_profile=None,
        media_file=None,
        start_seconds=None,
        end_seconds=None,
        reviewer=None,
    )
    values = {"FLOW_IMAGE_MODEL": "model-one", "FLOW_IMAGE_COUNT": "1x"}
    monkeypatch.setattr(cli, "get_config_value", lambda key, default: values.get(key, default))
    first = cli._stage_recipe(tmp_path, args)
    values["FLOW_IMAGE_MODEL"] = "model-two"
    assert cli._stage_recipe(tmp_path, args) != first


def test_cli_skips_successful_unchanged_stage_and_reruns_changed_recipe(
    tmp_path, monkeypatch
):
    from youtube_automation.production import cli

    database = tmp_path / "jobs.db"
    report = MagicMock()

    def write_report(_root):
        output = tmp_path / "adaptive_review" / "index.html"
        output.parent.mkdir(exist_ok=True)
        output.write_text("report", encoding="utf-8")
        return output

    report.side_effect = write_report
    monkeypatch.setattr(cli, "resource_database", lambda: database)
    monkeypatch.setattr(cli, "write_review", report)
    cli.main(["report", "--run-dir", str(tmp_path)])
    cli.main(["report", "--run-dir", str(tmp_path)])
    assert report.call_count == 1
    (tmp_path / "adaptive_review" / "index.html").unlink()
    cli.main(["report", "--run-dir", str(tmp_path)])
    assert report.call_count == 2
    (tmp_path / "shot_plan.json").write_text("new plan", encoding="utf-8")
    cli.main(["report", "--run-dir", str(tmp_path)])
    assert report.call_count == 3


def test_cli_adopts_content_bound_existing_output_without_repeating_stage(
    tmp_path, monkeypatch
):
    from youtube_automation.core.utils import atomic_write_json
    from youtube_automation.production import cli
    from youtube_automation.production.contracts import Analysis, Brief, Channel, fingerprint

    database = tmp_path / "jobs.db"
    raw = "Existing source"
    (tmp_path / "raw_transcript.txt").write_text(raw, encoding="utf-8")
    channel = Channel(
        channel_id="test",
        name="Test",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="voice",
        tone="calm",
        style="illustration",
        allowed_treatments=["subject_scene"],
    )
    profile = tmp_path / "channel.json"
    atomic_write_json(str(profile), channel.model_dump(mode="json"))
    brief = Brief(
        source_sha256=fingerprint(raw),
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=Analysis(
            topics=["test"],
            claim_basis="factual",
            form="explanation",
            proposition="Scene",
            narrative_strategy="Observe",
            treatments=["subject_scene"],
            rationale="Concrete",
        ),
    )
    atomic_write_json(str(tmp_path / "episode_brief.json"), brief.model_dump(mode="json"))
    analyze = MagicMock()
    monkeypatch.setattr(cli, "resource_database", lambda: database)
    monkeypatch.setattr(cli, "ensure_brief", analyze)

    cli.main(
        [
            "analyze",
            "--run-dir",
            str(tmp_path),
            "--channel-profile",
            str(profile),
        ]
    )

    analyze.assert_not_called()
    row = cli.Ledger(database).status()[0]
    assert row["state"] == "SUCCEEDED"
    assert row["key"].endswith(":analyze")
