"""Unit tests: checkpoint idempotency across pipeline state manifests."""

import json
import os

import pytest

import automate_audacity
import compile_video
import refine_script
import run_agency


class TestRefineCheckpoint:
    def test_save_is_atomic_no_tmp_left_behind(self, tmp_path):
        folder = str(tmp_path)
        refine_script.save_checkpoint(
            folder, [refine_script.RefinedTurn(1, "o", "r", 1, 0.0, False)]
        )
        leftovers = [
            p for p in os.listdir(folder)
            if p.startswith("refine_checkpoint.json") and p != "refine_checkpoint.json"
        ]
        assert leftovers == []


class TestAudacityCheckpoint:
    def test_polished_files_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        automate_audacity.save_checkpoint("run_a", ["Chapter_1.wav"])
        loaded = automate_audacity.load_checkpoint("run_a")
        assert loaded == ["Chapter_1.wav"]
        automate_audacity.delete_checkpoint("run_a")
        assert automate_audacity.load_checkpoint("run_a") == []

    def test_corrupt_checkpoint_recovers_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        automate_audacity.save_checkpoint("run_b", ["Chapter_1.wav"])
        path = os.path.join("run_b", "audacity_checkpoint.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{BROKEN")
        assert automate_audacity.load_checkpoint("run_b") == []


class TestRunAgencyPipelineState:
    def test_default_state_shape(self, tmp_path):
        state = run_agency.get_pipeline_state(str(tmp_path))
        expected_keys = {
            "translate", "refine", "voice", "audacity", "stitch",
            "transcribe", "images", "fixtimes", "video", "thumbnail",
        }
        assert expected_keys <= set(state)
        assert not any(state.values())

    def test_save_then_load_preserves_flags(self, tmp_path):
        folder = str(tmp_path)
        state = run_agency.get_pipeline_state(folder)
        state["refine"] = True
        state["voice"] = True
        run_agency.save_pipeline_state(folder, state)
        reloaded = run_agency.get_pipeline_state(folder)
        assert reloaded["refine"] is True and reloaded["voice"] is True

    def test_corrupt_state_file_falls_back_to_defaults(self, tmp_path):
        folder = str(tmp_path)
        with open(os.path.join(folder, "pipeline.json"), "w", encoding="utf-8") as f:
            f.write("{NOT JSON")
        state = run_agency.get_pipeline_state(folder)
        assert state["video"] is False

    def test_partial_state_merges_with_defaults(self, tmp_path):
        folder = str(tmp_path)
        with open(os.path.join(folder, "pipeline.json"), "w", encoding="utf-8") as f:
            json.dump({"video": True}, f)
        state = run_agency.get_pipeline_state(folder)
        assert state["video"] is True and state["refine"] is False


class TestCompileCheckpointManager:
    @pytest.fixture
    def manager(self, tmp_path):
        cfg = {"CHECKPOINT_FILE": "compile_checkpoint.json"}
        return compile_video.CheckpointManager(str(tmp_path), cfg)

    def test_initialize_writes_valid_schema(self, manager):
        manager.initialize(
            total_clips=3,
            encoder_config={"video_codec": "libx264", "encoder_args": []},
            audio_path="ep.wav",
            audio_duration=12.5,
        )
        data = json.loads(open(manager.checkpoint_path, encoding="utf-8").read())
        assert data["version"] == 3
        assert data["total_clips"] == 3
        assert set(data["clip_states"]) == {"0", "1", "2"}
        assert data["audio_duration"] == pytest.approx(12.5)

    def test_mark_clip_done_updates_counter_and_disk(self, manager):
        manager.initialize(
            2, {"video_codec": "h264_nvenc", "encoder_args": []}, "a.wav", 5.0
        )
        manager.mark_clip_done(0, "chunk_0000.mp4", 2.5)
        fresh = compile_video.CheckpointManager(manager.run_folder, manager.config)
        assert fresh.is_clip_done(0)
        assert not fresh.is_clip_done(1)
        assert fresh.data["completed_clips"] == 1

    def test_signature_detects_resolution_change(self, tmp_path):
        cfg = {"CHECKPOINT_FILE": "compile_checkpoint.json"}
        mgr = compile_video.CheckpointManager(str(tmp_path), cfg)
        mgr.initialize(1, {"video_codec": "libx264", "encoder_args": []}, "a.wav", 1.0)
        changed = dict(cfg, OUTPUT_WIDTH=3840, OUTPUT_HEIGHT=2160, OUTPUT_FPS=30)
        other = compile_video.CheckpointManager(mgr.run_folder, changed)
        assert other.is_signature_valid() is False

    def test_corrupt_checkpoint_loads_as_none(self, tmp_path):
        cfg = {"CHECKPOINT_FILE": "compile_checkpoint.json"}
        bad = tmp_path / "compile_checkpoint.json"
        bad.write_text('{"half": ', encoding="utf-8")
        mgr = compile_video.CheckpointManager(str(tmp_path), cfg)
        assert mgr.data is None

    def test_cleanup_removes_checkpoint_only_on_success(self, manager):
        manager.initialize(
            1, {"video_codec": "libx264", "encoder_args": []}, "a.wav", 1.0
        )
        assert os.path.exists(manager.checkpoint_path)
        manager.cleanup_on_success()
        assert not os.path.exists(manager.checkpoint_path)
