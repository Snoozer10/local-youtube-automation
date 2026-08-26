"""Unit tests for compile_video loudnorm measurement extraction and second-pass filter."""

import subprocess
from pathlib import Path

import pytest

import compile_video

REALISTIC_STDERR = (
    "ffmpeg version 7.0 Copyright (c) 2000-2024\n"
    "Input #0, wav, from 'audio.wav':\n"
    "  Duration: 00:10:00.00\n"
    "[Parsed_loudnorm_0 @ 0000025a6f3c9b40]\n"
    "{\n"
    '\t"input_i" : "-14.02",\n'
    '\t"input_tp" : "-1.02",\n'
    '\t"input_lra" : "7.40",\n'
    '\t"input_thresh" : "-24.04",\n'
    '\t"output_i" : "-14.11",\n'
    '\t"output_tp" : "-1.51",\n'
    '\t"output_lra" : "6.80",\n'
    '\t"output_thresh" : "-24.13",\n'
    '\t"normalization_type" : "linear",\n'
    '\t"target_offset" : "0.03"\n'
    "}\n"
    "size=N/A time=00:10:00.00\n"
)


@pytest.fixture
def audio_in_tmp(tmp_path: Path) -> str:
    return str(tmp_path / "episode.wav")


class TestExtractLoudnormMeasured:
    def test_realistic_multiline_stderr_maps_all_five_fields(self, config, audio_in_tmp):
        measured = compile_video._extract_loudnorm_measured(
            REALISTIC_STDERR, config, str(Path(audio_in_tmp).parent)
        )
        assert measured["LOUDNORM_MEASURED_I"] == pytest.approx(-14.02)
        assert measured["LOUDNORM_MEASURED_TP"] == pytest.approx(-1.02)
        assert measured["LOUDNORM_MEASURED_LRA"] == pytest.approx(7.40)
        assert measured["LOUDNORM_MEASURED_THRESH"] == pytest.approx(-24.04)
        assert measured["LOUDNORM_OFFSET"] == pytest.approx(0.03)

    def test_extraction_mutates_config_in_place(self, config, tmp_path):
        compile_video._extract_loudnorm_measured(REALISTIC_STDERR, config, str(tmp_path))
        assert float(config["LOUDNORM_MEASURED_I"]) == pytest.approx(-14.02)
        assert float(config["LOUDNORM_OFFSET"]) == pytest.approx(0.03)

    def test_measured_values_written_to_local_config_file(self, config, tmp_path):
        compile_video._extract_loudnorm_measured(REALISTIC_STDERR, config, str(tmp_path))
        local = tmp_path / "video_config.local.txt"
        assert local.exists()
        lines = {
            line.split("=", 1)[0]: line.split("=", 1)[1].strip()
            for line in local.read_text(encoding="utf-8").splitlines()
            if "=" in line
        }
        assert lines["LOUDNORM_MEASURED_I"] == "-14.02"
        assert lines["LOUDNORM_MEASURED_THRESH"] == "-24.04"

    def test_stderr_without_json_block_returns_empty_and_writes_nothing(self, config, tmp_path):
        measured = compile_video._extract_loudnorm_measured(
            "no metrics here", config, str(tmp_path)
        )
        assert measured == {}
        assert not (tmp_path / "video_config.local.txt").exists()

    def test_malformed_json_after_match_degrades_to_empty_dict(self, config, tmp_path):
        bad = '[Parsed_loudnorm_0 @ abc] { "input_i": "-12.5", "input_tp": oops }'
        measured = compile_video._extract_loudnorm_measured(bad, config, str(tmp_path))
        assert measured == {}

    def test_unterminated_json_block_yields_empty_dict(self, config, tmp_path):
        truncated = '{\n\t"input_i" : "-13.9",\n\t"input_tp" : "-1.0"'
        measured = compile_video._extract_loudnorm_measured(truncated, config, str(tmp_path))
        assert measured == {}

    def test_non_numeric_input_i_fails_regex_and_stays_clean(self, config, tmp_path):
        weird = '{ "input_i": "N/A", "target_offset": "0.0" }'
        measured = compile_video._extract_loudnorm_measured(weird, config, str(tmp_path))
        assert measured == {}


class TestMeasureLoudnorm:
    def _patch_run(self, monkeypatch: pytest.MonkeyPatch, stderr: str, returncode: int = 0):
        class R:
            pass

        result = R()
        result.stderr = stderr
        result.returncode = returncode
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)
        return captured

    def test_second_pass_filter_echoes_all_measured_values(self, monkeypatch, config, audio_in_tmp):
        self._patch_run(monkeypatch, REALISTIC_STDERR)
        filter_str = compile_video._measure_loudnorm(audio_in_tmp, config)
        assert filter_str.startswith("loudnorm=")
        assert f"I={config['LOUDNORM_I']}" in filter_str
        assert "measured_I=-14.02" in filter_str
        assert "measured_TP=-1.02" in filter_str
        assert "measured_LRA=7.4" in filter_str
        assert "measured_thresh=-24.04" in filter_str
        assert "offset=0.03" in filter_str
        assert "linear=true" in filter_str

    def test_measure_command_requests_json_print_format(self, monkeypatch, config, audio_in_tmp):
        captured = self._patch_run(monkeypatch, REALISTIC_STDERR)
        compile_video._measure_loudnorm(audio_in_tmp, config)
        cmd = captured["cmd"]
        joined = " ".join(cmd)
        assert "loudnorm" in joined
        assert "print_format=json" in joined

    def test_subprocess_failure_falls_back_to_single_pass_filter(
        self, monkeypatch, config, audio_in_tmp
    ):
        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=120)

        monkeypatch.setattr(subprocess, "run", boom)
        fallback = compile_video._measure_loudnorm(audio_in_tmp, config)
        assert fallback == (
            f"loudnorm=I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:"
            f"LRA={config['LOUDNORM_LRA']}"
        )

    def test_success_without_metrics_falls_back_to_single_pass_filter(
        self, monkeypatch, config, audio_in_tmp
    ):
        self._patch_run(monkeypatch, "quiet run, no json")
        fallback = compile_video._measure_loudnorm(audio_in_tmp, config)
        assert "measured_I" not in fallback
        assert fallback.startswith("loudnorm=I=")
