"""End-to-End Integration, Audio DSP Normalization & Quality Gates (Ticket 6 / #19 / ADR 0005)."""

from io import StringIO
from pathlib import Path

import automate_audacity
import compile_video
from pipeline_manifest import ChunkStatus, PhaseStatus, PipelineManifest
from timeline_engine import build_timeline, build_words_from_whisper


class TestE2EPipelineStateTransitions:
    """Verifies PipelineManifest and pipeline.json lifecycle states."""

    def test_pipeline_manifest_lifecycle(self, tmp_path: Path):
        manifest = PipelineManifest.load_or_create(tmp_path, script_hash="hash123")

        data = manifest.to_dict()
        assert data["roadmap_phase"]["status"] == PhaseStatus.PENDING.value
        assert data["planning_phase"]["status"] == PhaseStatus.PENDING.value
        assert len(manifest.rendered_indices) == 0

        # Update roadmap and planning phase
        manifest.set_roadmap_status(PhaseStatus.IN_PROGRESS)
        manifest.set_roadmap_totals(total_lines=50)
        manifest.init_planning(chunk_size=2, total_chunks=2)
        manifest.set_chunk_status("chunk_0", [0, 1], ChunkStatus.VERIFIED, attempts=1)
        manifest.set_chunk_status("chunk_1", [2, 3], ChunkStatus.REPAIRED, attempts=2)
        manifest.record_rendered(0)
        manifest.record_rendered(1)
        manifest.save()

        # Reload from disk
        loaded = PipelineManifest.load_or_create(tmp_path, script_hash="hash123")
        loaded_data = loaded.to_dict()
        assert loaded_data["roadmap_phase"]["status"] == PhaseStatus.IN_PROGRESS.value
        assert loaded.all_chunks_done() is True
        assert loaded.rendered_indices == [0, 1]

        # Mark roadmap complete
        loaded.set_roadmap_status(PhaseStatus.COMPLETED)
        loaded.save()

        final = PipelineManifest.load_or_create(tmp_path, script_hash="hash123")
        assert final.to_dict()["roadmap_phase"]["status"] == PhaseStatus.COMPLETED.value


class TestAudacitySessionCleanupContract:
    """Verifies ADR 0005 Audacity session cleanup and Named Pipes contracts."""

    def test_clear_audacity_temp_data_wipes_session_and_autosave(self, monkeypatch, tmp_path: Path):
        local_appdata = tmp_path / "LocalAppData"
        roaming_appdata = tmp_path / "AppData"

        session_dir = local_appdata / "Audacity" / "SessionData"
        autosave_dir = roaming_appdata / "audacity" / "AutoSave"
        session_dir.mkdir(parents=True, exist_ok=True)
        autosave_dir.mkdir(parents=True, exist_ok=True)

        # Create dummy crash/temp files
        (session_dir / "crash_lock.tmp").write_text("crash", encoding="utf-8")
        (session_dir / "temp_subfolder").mkdir()
        (session_dir / "temp_subfolder" / "data.raw").write_text("raw", encoding="utf-8")
        (autosave_dir / "project.autosave").write_text("autosave", encoding="utf-8")

        monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
        monkeypatch.setenv("APPDATA", str(roaming_appdata))

        automate_audacity.clear_audacity_temp_data()

        assert len(list(session_dir.iterdir())) == 0, "SessionData should be completely wiped"
        assert len(list(autosave_dir.iterdir())) == 0, "AutoSave should be completely wiped"

    def test_ensure_audacity_script_pipe_enabled(self, monkeypatch, tmp_path: Path):
        roaming_appdata = tmp_path / "AppData"
        cfg_dir = roaming_appdata / "audacity"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = cfg_dir / "audacity.cfg"
        cfg_file.write_text("[GUI]\nTheme=Classic\n", encoding="utf-8")

        monkeypatch.setenv("APPDATA", str(roaming_appdata))

        automate_audacity.ensure_audacity_script_pipe_enabled()

        content = cfg_file.read_text(encoding="utf-8")
        assert "mod-script-pipe=1" in content

    def test_apply_preset_file_always_selects_all_before_effect(self, tmp_path: Path):
        preset_file = tmp_path / "test_preset.txt"
        preset_file.write_text(
            "NoiseGate:attack=10\n"
            "Compressor:threshold=-20\n"
            "Normalize:peak=-1\n",
            encoding="utf-8",
        )

        sent_commands = []

        def fake_send_cmd(write_pipe, read_pipe, cmd):
            sent_commands.append(cmd)
            return "BatchCommand finished: OK"

        orig_send = automate_audacity.send_audacity_command
        automate_audacity.send_audacity_command = fake_send_cmd
        try:
            write_pipe = StringIO()
            read_pipe = StringIO("OK\n\n")
            success = automate_audacity.apply_preset_file(write_pipe, read_pipe, str(preset_file))
            assert success is True
            # Verify SelectAll: precedes every effect
            assert sent_commands == [
                "SelectAll:",
                "NoiseGate:attack=10",
                "SelectAll:",
                "Compressor:threshold=-20",
                "SelectAll:",
                "Normalize:peak=-1",
            ]
        finally:
            automate_audacity.send_audacity_command = orig_send


class TestEBUR128AudioLoudnessContract:
    """Verifies ADR 0005 loudness targets (-14 LUFS, -1 dBTP, LRA 11)."""

    def test_video_config_and_compile_defaults_match_adr0005(self):
        cfg = compile_video.load_video_config()
        assert float(cfg["LOUDNORM_I"]) == -14.0
        assert float(cfg["LOUDNORM_TP"]) == -1.0
        assert float(cfg["LOUDNORM_LRA"]) == 11.0
        assert str(cfg["AUDIO_BITRATE"]) == "320k"
        assert int(cfg["AUDIO_SAMPLE_RATE"]) == 48000

    def test_extract_loudnorm_measured_payload(self):
        sample_stderr = """
        [Parsed_loudnorm_0 @ 000001]
        {
            "input_i" : "-16.20",
            "input_tp" : "-2.10",
            "input_lra" : "9.50",
            "input_thresh" : "-26.50",
            "output_i" : "-14.00",
            "output_tp" : "-1.00",
            "output_lra" : "9.20",
            "output_thresh" : "-24.30",
            "normalization_type" : "dynamic",
            "target_offset" : "0.00"
        }
        """
        cfg = compile_video.load_video_config()
        measured = compile_video._extract_loudnorm_measured(sample_stderr, cfg, "")
        assert measured["LOUDNORM_MEASURED_I"] == -16.20
        assert measured["LOUDNORM_MEASURED_TP"] == -2.10
        assert measured["LOUDNORM_MEASURED_LRA"] == 9.50
        assert measured["LOUDNORM_MEASURED_THRESH"] == -26.50
        assert measured["LOUDNORM_OFFSET"] == 0.00


class TestZeroDriftFrameArithmeticAndAVSync:
    """Verifies integer frame arithmetic and continuous timeline sync."""

    def test_zero_drift_frame_budget_and_continuity(self):
        audio_durations = [10.0, 10.033, 45.167, 120.500]
        fps = 30.0

        for audio_dur in audio_durations:
            expected_total_frames = round(audio_dur * fps)
            whisper_segments = [
                {"words": [{"word": "Word1", "start": 0.0, "end": 2.5}]},
                {"words": [{"word": "Word2", "start": 2.5, "end": 5.0}]},
                {"words": [{"word": "Word3", "start": 5.0, "end": audio_dur}]},
            ]
            words = build_words_from_whisper(whisper_segments)
            timeline = build_timeline(
                words, audio_duration=audio_dur, fps=int(fps), vad_snap_threshold=0.35
            )

            assert timeline["total_frames"] == expected_total_frames
            # AV Sync error bound: max drift <= 0.5 frame (<= 0.017s at 30 fps)
            timeline_duration = timeline["total_frames"] / fps
            assert abs(timeline_duration - audio_dur) <= (0.5 / fps)

            # Check spans continuity
            spans = timeline["spans"]
            assert len(spans) > 0
            assert spans[0]["start_frame"] == 0
            for i in range(1, len(spans)):
                assert spans[i]["start_frame"] == spans[i - 1]["end_frame"]
