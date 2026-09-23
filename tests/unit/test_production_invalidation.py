"""Changed stage recipes deactivate only mutable outputs and recover after interruption."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from youtube_automation.production import invalidation
from youtube_automation.production.invalidation import invalidate_stage, reconcile_invalidation


def test_changed_plan_archives_downstream_pointers_but_preserves_accepted_bytes(tmp_path):
    (tmp_path / "shot_plan.json").write_text('{"old": true}', encoding="utf-8")
    (tmp_path / "shot_plan.partial.json").write_text('{"partial": true}', encoding="utf-8")
    receipts = tmp_path / "asset_receipts"
    receipts.mkdir()
    (receipts / "scene.json").write_text('{"sha256": "old"}', encoding="utf-8")
    accepted = tmp_path / "accepted_assets"
    accepted.mkdir()
    (accepted / "scene.png").write_bytes(b"expensive accepted image")
    renders = tmp_path / "adaptive_renders" / "generation"
    renders.mkdir(parents=True)
    (renders / "master.mp4").write_bytes(b"immutable render")
    (tmp_path / "adaptive_preview.json").write_text('{"old": true}', encoding="utf-8")
    (tmp_path / "active_master.json").write_text('{"old": true}', encoding="utf-8")

    archived = invalidate_stage(tmp_path, "plan", "a" * 64, "b" * 64)

    assert set(archived) == {
        "shot_plan.json",
        "shot_plan.partial.json",
        "asset_receipts/scene.json",
        "adaptive_preview.json",
        "active_master.json",
    }
    assert (accepted / "scene.png").read_bytes() == b"expensive accepted image"
    assert (renders / "master.mp4").read_bytes() == b"immutable render"
    assert not (tmp_path / "shot_plan.json").exists()
    history = tmp_path / ".adaptive_history" / ("a" * 12 + "-to-" + "b" * 12) / "plan"
    assert (history / "shot_plan.json").is_file()
    assert (history / "shot_plan.partial.json").is_file()
    assert not (tmp_path / ".publication_journal" / "stage-invalidation.json").exists()


def test_interrupted_invalidation_reconciles_without_losing_outputs(tmp_path, monkeypatch):
    (tmp_path / "adaptive_preview.json").write_text("preview", encoding="utf-8")
    (tmp_path / "editorial_approval.json").write_text("approval", encoding="utf-8")
    real_replace = invalidation.os.replace
    calls = []

    def fail_after_first(source, target):
        if str(target).endswith("stage-invalidation.json"):
            real_replace(source, target)
            return
        calls.append((source, target))
        if len(calls) == 2:
            raise OSError("injected crash")
        real_replace(source, target)

    monkeypatch.setattr(invalidation.os, "replace", fail_after_first)
    with pytest.raises(OSError, match="injected crash"):
        invalidate_stage(tmp_path, "preview", "c" * 64, "d" * 64)
    journal = tmp_path / ".publication_journal" / "stage-invalidation.json"
    assert journal.is_file()

    monkeypatch.setattr(invalidation.os, "replace", real_replace)
    recovered = reconcile_invalidation(tmp_path)
    assert set(recovered) == {"adaptive_preview.json", "editorial_approval.json"}
    assert not journal.exists()


def test_reconciliation_rejects_corrupted_archive(tmp_path, monkeypatch):
    active = tmp_path / "active_master.json"
    active.write_text("master", encoding="utf-8")
    real_replace = invalidation.os.replace

    def corrupt_after_move(source, target):
        if str(target).endswith("stage-invalidation.json"):
            real_replace(source, target)
            return
        real_replace(source, target)
        invalidation.Path(target).write_text("corrupt", encoding="utf-8")
        raise OSError("injected crash")

    monkeypatch.setattr(invalidation.os, "replace", corrupt_after_move)
    with pytest.raises(OSError, match="injected crash"):
        invalidate_stage(tmp_path, "render", "e" * 64, "f" * 64)
    monkeypatch.setattr(invalidation.os, "replace", real_replace)
    with pytest.raises(ValueError, match="missing or corrupt"):
        reconcile_invalidation(tmp_path)


def test_invalidation_journal_rejects_paths_outside_run(tmp_path):
    journal = tmp_path / ".publication_journal" / "stage-invalidation.json"
    journal.parent.mkdir()
    journal.write_text(
        json.dumps(
            {
                "version": 1,
                "files": [
                    {
                        "source": "../outside",
                        "archive": ".adaptive_history/outside",
                        "sha256": "0" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid path"):
        reconcile_invalidation(tmp_path)


def test_real_process_death_is_reconciled_on_restart(tmp_path):
    (tmp_path / "active_master.json").write_text("active", encoding="utf-8")
    source_root = Path(__file__).resolve().parents[2] / "src"
    crash_script = f"""
import os
import sys
sys.path.insert(0, {str(source_root)!r})
from youtube_automation.production import invalidation
real_replace = invalidation.os.replace
def replace_then_exit(source, target):
    real_replace(source, target)
    if not str(target).endswith('stage-invalidation.json'):
        os._exit(23)
invalidation.os.replace = replace_then_exit
invalidation.invalidate_stage(sys.argv[1], 'render', '1' * 64, '2' * 64)
"""
    process = subprocess.run(
        [sys.executable, "-c", crash_script, str(tmp_path)],
        check=False,
        timeout=15,
    )
    assert process.returncode == 23
    journal = tmp_path / ".publication_journal" / "stage-invalidation.json"
    assert journal.is_file()
    assert not (tmp_path / "active_master.json").exists()

    assert reconcile_invalidation(tmp_path) == ["active_master.json"]
    assert not journal.exists()
