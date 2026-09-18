from pathlib import Path
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
