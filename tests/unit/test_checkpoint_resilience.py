"""Unit tests for compile_video.CheckpointManager and run_agency pipeline.json state."""

import json
from pathlib import Path

import pytest

import compile_video
import run_agency


def make_encoder_config() -> dict:
    return {"video_codec": "libx264", "encoder_args": ["-preset", "veryfast"]}


@pytest.fixture
def cm(tmp_path: Path, config):
    return compile_video.CheckpointManager(str(tmp_path), config)


class TestHappyPathResume:
    def test_initialize_mark_reload_preserves_done_clips(self, tmp_path, config):
        manager = compile_video.CheckpointManager(str(tmp_path), config)
        manager.initialize(3, make_encoder_config(), "audio.wav", 10.0)
        manager.mark_clip_done(0, "clip_0.mp4", 3.33)
        manager.mark_clip_done(2, "clip_2.mp4", 3.34)

        reloaded = compile_video.CheckpointManager(str(tmp_path), config)
        assert reloaded.is_clip_done(0)
        assert not reloaded.is_clip_done(1)
        assert reloaded.is_clip_done(2)
        assert reloaded.data["completed_clips"] == 2
        assert reloaded.data["total_clips"] == 3
        assert reloaded.data["version"] == 3

    def test_save_now_false_defers_persistence_to_disk(self, tmp_path, config):
        manager = compile_video.CheckpointManager(str(tmp_path), config)
        manager.initialize(2, make_encoder_config(), "audio.wav", 10.0)
        manager.mark_clip_done(0, "clip_0.mp4", 5.0, save_now=False)

        assert manager.is_clip_done(0), "in-memory state must reflect the mark"
        reloaded = compile_video.CheckpointManager(str(tmp_path), config)
        assert not reloaded.is_clip_done(0), "unsaved mark must not survive reload"

    def test_cleanup_on_success_removes_checkpoint_file_and_is_idempotent(self, tmp_path, config):
        path = tmp_path / config["CHECKPOINT_FILE"]
        manager = compile_video.CheckpointManager(str(tmp_path), config)
        manager.initialize(1, make_encoder_config(), "audio.wav", 5.0)
        assert path.exists()
        manager.cleanup_on_success()
        assert not path.exists()
        manager.cleanup_on_success()

    def test_completed_counter_recounts_on_every_mark(self, tmp_path, config):
        manager = compile_video.CheckpointManager(str(tmp_path), config)
        manager.initialize(3, make_encoder_config(), "audio.wav", 9.0)
        manager.mark_clip_done(0, "a.mp4", 3.0)
        manager.mark_clip_done(0, "a.mp4", 3.0)
        manager.mark_clip_done(1, "b.mp4", 3.0)
        assert manager.data["completed_clips"] == 2


class TestSignatureValidation:
    def _initialize(self, tmp_path: Path, config) -> compile_video.CheckpointManager:
        manager = compile_video.CheckpointManager(str(tmp_path), config)
        manager.initialize(2, make_encoder_config(), "audio.wav", 10.0)
        return manager

    def test_unchanged_config_signature_stays_valid(self, tmp_path, config):
        self._initialize(tmp_path, config)
        reloaded = compile_video.CheckpointManager(str(tmp_path), config)
        assert reloaded.is_signature_valid()

    @pytest.mark.parametrize("dim_key", ["OUTPUT_WIDTH", "OUTPUT_HEIGHT"])
    def test_output_dimension_change_invalidates_checkpoint(self, tmp_path, config, dim_key):
        self._initialize(tmp_path, config)
        drifted = dict(config)
        drifted[dim_key] = int(drifted[dim_key]) + 2
        reloaded = compile_video.CheckpointManager(str(tmp_path), drifted)
        assert not reloaded.is_signature_valid()

    def test_fps_change_invalidates_checkpoint(self, tmp_path, config):
        self._initialize(tmp_path, config)
        drifted = dict(config)
        drifted["OUTPUT_FPS"] = int(config["OUTPUT_FPS"]) + 6
        reloaded = compile_video.CheckpointManager(str(tmp_path), drifted)
        assert not reloaded.is_signature_valid()

    @pytest.mark.parametrize(
        ("new_duration", "expect_valid"),
        [
            pytest.param(10.04, True, id="duration-drift-within-tolerance-stays-valid"),
            pytest.param(999.0, False, id="duration-drift-beyond-tolerance-invalidates"),
        ],
    )
    def test_audio_duration_drift_gate(self, tmp_path, config, new_duration, expect_valid):
        self._initialize(tmp_path, config)
        drifted = dict(config)
        drifted["_audio_duration"] = new_duration
        reloaded = compile_video.CheckpointManager(str(tmp_path), drifted)
        assert reloaded.is_signature_valid() is expect_valid

    def test_encoder_swap_invalidates_only_with_expected_codec(self, tmp_path, config):
        manager = self._initialize(tmp_path, config)
        manager.data["encoder"] = "h264_qsv"
        manager.save()

        reloaded = compile_video.CheckpointManager(str(tmp_path), config)
        assert reloaded.data["encoder"] == "h264_qsv"
        assert not reloaded.is_signature_valid(
            expected_codec="libx264"
        ), "codec mismatch must invalidate when expected_codec is supplied"
        assert reloaded.is_signature_valid(), "no-arg call preserves legacy dims/FPS-only semantics"

    def test_legacy_minimal_checkpoint_without_duration_key_stays_valid(self, tmp_path, config):
        sig = f"{config['OUTPUT_WIDTH']}x{config['OUTPUT_HEIGHT']}@{config['OUTPUT_FPS']}"
        legacy_payload = {"version": 3, "render_signature": sig}
        (tmp_path / config["CHECKPOINT_FILE"]).write_text(
            json.dumps(legacy_payload), encoding="utf-8"
        )
        reloaded = compile_video.CheckpointManager(str(tmp_path), config)
        assert reloaded.data is not None
        assert reloaded.is_signature_valid()


class TestCorruptAndMissingCheckpoint:
    @pytest.mark.parametrize(
        ("label", "raw"),
        [
            ("truncated-json", '{"version": 3, "clip_stat'),
            ("invalid-token", "{not json at all"),
            ("partial-valid-prefix", '{"version": 3, "clip_states": {'),
            ("empty-file", ""),
        ],
    )
    def test_unreadable_checkpoint_treated_as_fresh_without_raising(
        self, tmp_path, config, label, raw
    ):
        (tmp_path / config["CHECKPOINT_FILE"]).write_text(raw, encoding="utf-8")
        reloaded = compile_video.CheckpointManager(str(tmp_path), config)
        assert reloaded.data is None
        assert reloaded.is_signature_valid(), "fresh semantics: no data means valid"

    def test_is_clip_done_returns_false_on_fresh_checkpoint(self, tmp_path, config):
        (tmp_path / config["CHECKPOINT_FILE"]).write_text("{not json", encoding="utf-8")
        reloaded = compile_video.CheckpointManager(str(tmp_path), config)
        assert reloaded.is_clip_done(0) is False

    def test_mark_clip_done_on_fresh_checkpoint_raises_runtime_error(self, tmp_path, config):
        (tmp_path / config["CHECKPOINT_FILE"]).write_text("{not json", encoding="utf-8")
        reloaded = compile_video.CheckpointManager(str(tmp_path), config)
        with pytest.raises(RuntimeError, match="checkpoint not initialized"):
            reloaded.mark_clip_done(0, "clip_0.mp4", 3.0)

    def test_initialize_after_corrupt_load_recovers_clip_queries(self, tmp_path, config):
        (tmp_path / config["CHECKPOINT_FILE"]).write_text("{not json", encoding="utf-8")
        reloaded = compile_video.CheckpointManager(str(tmp_path), config)
        reloaded.initialize(2, make_encoder_config(), "audio.wav", 10.0)
        assert not reloaded.is_clip_done(0)
        assert not reloaded.is_clip_done(1)

    def test_missing_file_starts_fresh(self, tmp_path, config):
        manager = compile_video.CheckpointManager(str(tmp_path), config)
        assert manager.data is None
        manager.initialize(2, make_encoder_config(), "audio.wav", 10.0)
        assert manager.is_clip_done(0) is False

    def test_corrupt_checkpoint_then_initialize_recovers(self, tmp_path, config):
        (tmp_path / config["CHECKPOINT_FILE"]).write_text("garbage{", encoding="utf-8")
        manager = compile_video.CheckpointManager(str(tmp_path), config)
        manager.initialize(1, make_encoder_config(), "audio.wav", config["_audio_duration"])
        reloaded = compile_video.CheckpointManager(str(tmp_path), config)
        assert reloaded.data is not None
        assert reloaded.is_signature_valid()


class TestPipelineStateRoundtrip:
    def test_save_then_load_roundtrip_merges_over_defaults(self, tmp_path):
        state = run_agency.get_pipeline_state(str(tmp_path))
        assert state == {
            "translate": False,
            "refine": False,
            "voice": False,
            "audacity": False,
            "stitch": False,
            "transcribe": False,
            "images": False,
            "fixtimes": False,
            "video": False,
            "thumbnail": False,
        }

        saved = dict(state)
        saved["voice"] = True
        saved["custom_key"] = "kept"
        run_agency.save_pipeline_state(str(tmp_path), saved)

        loaded = run_agency.get_pipeline_state(str(tmp_path))
        assert loaded["voice"] is True
        assert loaded["translate"] is False
        assert loaded["custom_key"] == "kept"

    def test_corrupt_pipeline_json_falls_back_to_default_state(self, tmp_path):
        (tmp_path / "pipeline.json").write_text('{"video": tru', encoding="utf-8")
        state = run_agency.get_pipeline_state(str(tmp_path))
        assert all(v is False for v in state.values())
        assert len(state) == 10

    def test_partial_json_prefix_cut_mid_object_falls_back_to_defaults(self, tmp_path):
        (tmp_path / "pipeline.json").write_text('{"images": true, "fixtimes"', encoding="utf-8")
        state = run_agency.get_pipeline_state(str(tmp_path))
        assert state["images"] is False
        assert state["thumbnail"] is False

    def test_save_into_missing_folder_silently_writes_nothing(self, tmp_path):
        target = tmp_path / "does-not-exist"
        run_agency.save_pipeline_state(str(target), {"video": True})
        assert not (target / "pipeline.json").exists()
        assert run_agency.get_pipeline_state(str(target))["video"] is False
