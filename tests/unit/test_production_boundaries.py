import threading
import time
from contextlib import contextmanager
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


def test_legacy_flow_entrypoint_also_holds_shared_browser_lease(tmp_path, monkeypatch):
    from youtube_automation.production import ledger
    from youtube_automation.visuals import flow_generator

    database = tmp_path / "jobs.db"
    monkeypatch.setattr(ledger, "resource_database", lambda: database)

    def worker(folder):
        assert Path(folder) == tmp_path
        assert ledger.Ledger(database).claim("browser", "other", "competitor") is None

    monkeypatch.setattr(flow_generator, "_main", worker)
    flow_generator.main(str(tmp_path))


def test_system_clipboard_write_holds_short_shared_lease(tmp_path, monkeypatch):
    from youtube_automation.audio import tts_generator
    from youtube_automation.production import ledger

    database = tmp_path / "jobs.db"
    monkeypatch.setattr(ledger, "resource_database", lambda: database)

    def write(_text):
        assert ledger.Ledger(database).claim("clipboard", "other", "competitor") is None
        return True

    monkeypatch.setattr(tts_generator, "_set_clipboard_text", write)
    assert tts_generator.set_clipboard_text("hello") is True


def test_final_ffmpeg_timeout_is_not_blocked_by_stderr_readline(monkeypatch):
    from youtube_automation.video import compiler

    release = threading.Event()

    class StalledStream:
        def readline(self):
            release.wait(2)
            return ""

    class Process:
        def __init__(self):
            self.stderr = StalledStream()
            self.returncode = None

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

    process = Process()
    monkeypatch.setattr(compiler.subprocess, "Popen", lambda *_args, **_kwargs: process)
    started = time.monotonic()
    try:
        assert not compiler._execute_final_assembly(
            ["ffmpeg"], ".", 0.05, 1.0, "output.mp4"
        )
    finally:
        release.set()
    assert time.monotonic() - started < 1.0
    assert process.returncode == -9


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


def test_planner_attachment_mode_rejects_unknown_transport(monkeypatch):
    from youtube_automation.production import cli

    monkeypatch.setattr(cli, "get_config_value", lambda _key, _default: "canvas")
    assert cli._planner_attachment_mode(persistent_chat=False) == "inline"
    with pytest.raises(ValueError, match="IMAGE_PLANNER_TRANSPORT"):
        cli._planner_attachment_mode(persistent_chat=True)


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


def test_changed_source_archives_only_active_generation_and_reanalyzes_same_run(
    tmp_path, monkeypatch
):
    from youtube_automation.core.utils import atomic_write_json
    from youtube_automation.production import cli
    from youtube_automation.production.contracts import Analysis, Brief, Channel, fingerprint

    database = tmp_path / "jobs.db"
    old_raw = "Old source"
    new_raw = "New source"
    (tmp_path / "raw_transcript.txt").write_text(old_raw, encoding="utf-8")
    channel = Channel(
        channel_id="test", name="Test", audience="adults", language="Arabic",
        dialect="MSA", voice="voice", tone="calm", style="illustration",
        allowed_treatments=["subject_scene"],
    )
    profile = tmp_path / "channel.json"
    atomic_write_json(str(profile), channel.model_dump(mode="json"))
    analysis = Analysis(
        topics=["test"], claim_basis="factual", form="explanation",
        proposition="Scene", narrative_strategy="Observe",
        treatments=["subject_scene"], rationale="Concrete",
    )
    old_brief = Brief(
        source_sha256=fingerprint(old_raw), profile_sha256=fingerprint(channel),
        channel=channel, analysis=analysis,
    )
    atomic_write_json(str(tmp_path / "episode_brief.json"), old_brief.model_dump(mode="json"))
    (tmp_path / "final_output.txt").write_text("old writing", encoding="utf-8")
    (tmp_path / "active_master.json").write_text("old pointer", encoding="utf-8")
    accepted = tmp_path / "accepted_assets"
    accepted.mkdir()
    (accepted / "keep.png").write_bytes(b"accepted bytes")
    monkeypatch.setattr(cli, "resource_database", lambda: database)
    argv = ["analyze", "--run-dir", str(tmp_path), "--channel-profile", str(profile)]
    cli.main(argv)

    (tmp_path / "raw_transcript.txt").write_text(new_raw, encoding="utf-8")

    @contextmanager
    def transport():
        yield lambda _prompt: analysis.model_dump_json()

    monkeypatch.setattr(cli, "gemini_transport", transport)
    cli.main(argv)
    current = cli.load_brief(tmp_path)
    assert current.source_sha256 == fingerprint(new_raw)
    assert not (tmp_path / "final_output.txt").exists()
    assert not (tmp_path / "active_master.json").exists()
    assert (accepted / "keep.png").read_bytes() == b"accepted bytes"
    assert list((tmp_path / ".adaptive_history").rglob("final_output.txt"))


def test_changed_source_audio_cut_reruns_after_archiving_old_receipt(tmp_path, monkeypatch):
    from youtube_automation.production import cli

    database = tmp_path / "jobs.db"
    (tmp_path / "raw_transcript.txt").write_text("Spoken words", encoding="utf-8")
    (tmp_path / "episode_brief.json").write_text("{}", encoding="utf-8")
    media = tmp_path / "owner.wav"
    media.write_bytes(b"owner voice")
    receipt = tmp_path / "source_audio_receipt.json"
    executed = []

    monkeypatch.setattr(cli, "resource_database", lambda: database)
    monkeypatch.setattr(cli, "_stage_complete", lambda _root, _args: receipt.exists())

    def execute(args, _root, _database):
        executed.append(args.end_seconds)
        receipt.write_text(str(args.end_seconds), encoding="utf-8")

    monkeypatch.setattr(cli, "_execute_stage", execute)
    base = [
        "source-audio", "--run-dir", str(tmp_path), "--media-file", str(media),
        "--start-seconds", "0", "--end-seconds",
    ]
    cli.main([*base, "77.2"])
    cli.main([*base, "76.55"])

    assert executed == [77.2, 76.55]
    assert receipt.read_text(encoding="utf-8") == "76.55"
    assert [path.read_text(encoding="utf-8") for path in
            (tmp_path / ".adaptive_history").rglob("source_audio_receipt.json")] == ["77.2"]


def test_visual_only_profile_change_invalidates_plan_not_narration(tmp_path, monkeypatch):
    from youtube_automation.core.utils import atomic_write_json
    from youtube_automation.production import cli
    from youtube_automation.production.contracts import Analysis, Brief, Channel, fingerprint

    database = tmp_path / "jobs.db"
    (tmp_path / "raw_transcript.txt").write_text("Spoken words", encoding="utf-8")
    profile = tmp_path / "channel.json"
    old = Channel(
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
    atomic_write_json(str(profile), old.model_dump(mode="json"))
    invalidated = []
    executed = []
    monkeypatch.setattr(cli, "resource_database", lambda: database)
    monkeypatch.setattr(cli, "_stage_complete", lambda _root, _args: False)
    monkeypatch.setattr(
        cli,
        "_execute_stage",
        lambda args, _root, _database: executed.append(args.stage),
    )
    monkeypatch.setattr(
        cli,
        "is_visual_policy_update",
        lambda _root, channel: channel.version == 2,
    )
    monkeypatch.setattr(
        cli,
        "invalidate_stage",
        lambda _root, stage, _old, _new: invalidated.append(stage) or [],
    )
    argv = [
        "analyze",
        "--run-dir",
        str(tmp_path),
        "--channel-profile",
        str(profile),
    ]
    cli.main(argv)
    brief = Brief(
        source_sha256=fingerprint("Spoken words"),
        profile_sha256=fingerprint(old),
        channel=old,
        analysis=Analysis(
            topics=["attention"],
            claim_basis="factual",
            form="explanation",
            proposition="Attention changes with context",
            narrative_strategy="Observe daily situations",
            treatments=["subject_scene"],
            rationale="Concrete human scenes",
        ),
    )
    atomic_write_json(
        str(tmp_path / "episode_brief.json"), brief.model_dump(mode="json")
    )
    upgraded = old.model_copy(
        update={
            "version": 2,
            "visual_directives": ["Use concrete scenes"],
            "forbidden_motifs": ["glowing brain"],
        }
    )
    atomic_write_json(str(profile), upgraded.model_dump(mode="json"))
    cli.main(argv)

    assert executed == ["analyze", "analyze"]
    assert invalidated == ["plan"]


def test_visual_only_profile_change_without_analyze_ledger_still_invalidates_plan(
    tmp_path, monkeypatch
):
    from youtube_automation.core.utils import atomic_write_json
    from youtube_automation.production import cli
    from youtube_automation.production.contracts import Analysis, Brief, Channel, fingerprint

    database = tmp_path / "jobs.db"
    raw = "Spoken words"
    (tmp_path / "raw_transcript.txt").write_text(raw, encoding="utf-8")
    old = Channel(
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
    upgraded = old.model_copy(
        update={
            "version": 2,
            "visual_directives": ["Use concrete scenes"],
            "forbidden_motifs": ["glowing brain"],
        }
    )
    profile = tmp_path / "channel.json"
    atomic_write_json(str(profile), upgraded.model_dump(mode="json"))
    brief = Brief(
        source_sha256=fingerprint(raw),
        profile_sha256=fingerprint(old),
        channel=old,
        analysis=Analysis(
            topics=["attention"],
            claim_basis="factual",
            form="explanation",
            proposition="Attention changes with context",
            narrative_strategy="Observe daily situations",
            treatments=["subject_scene"],
            rationale="Concrete human scenes",
        ),
    )
    atomic_write_json(
        str(tmp_path / "episode_brief.json"), brief.model_dump(mode="json")
    )
    invalidated = []
    executed = []
    monkeypatch.setattr(cli, "resource_database", lambda: database)
    monkeypatch.setattr(cli, "_stage_complete", lambda _root, _args: False)
    monkeypatch.setattr(
        cli,
        "_execute_stage",
        lambda args, _root, _database: executed.append(args.stage),
    )
    monkeypatch.setattr(
        cli,
        "invalidate_stage",
        lambda _root, stage, old_recipe, new_recipe: invalidated.append(
            (stage, old_recipe, new_recipe)
        )
        or [],
    )

    cli.main(
        [
            "analyze",
            "--run-dir",
            str(tmp_path),
            "--channel-profile",
            str(profile),
        ]
    )

    assert executed == ["analyze"]
    assert invalidated == [("plan", fingerprint(old), fingerprint(upgraded))]
