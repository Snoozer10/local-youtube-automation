"""Unit tests for Audacity named-pipe protocol semantics against a fake pipe pair."""

import io
import sys

import pytest
from mocks.mock_named_pipe import NamedPipePair, consume_until_empty_line

import automate_audacity


@pytest.fixture
def pair() -> NamedPipePair:
    return NamedPipePair()


class TestCommandFraming:
    @pytest.mark.parametrize(
        ("platform", "frame"),
        [("win32", "SelectAll:\r\n\0"), ("linux", "SelectAll:\n")],
    )
    def test_command_is_framed_with_trailing_newline_and_flushed(
        self, pair, monkeypatch, platform, frame
    ):
        monkeypatch.setattr(sys, "platform", platform)
        automate_audacity.send_audacity_command(pair.write_pipe, pair.read_pipe, "SelectAll:")
        assert pair.sent_text == frame
        assert pair.flushes >= 1

    @pytest.mark.parametrize(
        ("platform", "frames"),
        [("win32", ["SelectAll:\r\n\0", "Export2:\r\n\0"]),
         ("linux", ["SelectAll:\n", "Export2:\n"])],
    )
    def test_sequential_commands_preserve_order(
        self, pair, monkeypatch, platform, frames
    ):
        monkeypatch.setattr(sys, "platform", platform)
        pair.enqueue_response("ok\n", "\n")
        automate_audacity.send_audacity_command(pair.write_pipe, pair.read_pipe, "SelectAll:")
        automate_audacity.send_audacity_command(pair.write_pipe, pair.read_pipe, "Export2:")
        assert pair.sent_text == "".join(frames)
        assert pair.sent_commands == ["SelectAll:", "Export2:"]
        assert pair.flushes == 2

    def test_sent_commands_removes_only_recognized_frame_suffixes(self, pair):
        pair.sent_chunks.extend(["windows:\r\n\0", "posix:\n", "malformed:\r\n", "malformed:\0"])
        assert pair.sent_commands == [
            "windows:",
            "posix:",
            "malformed:\r\n",
            "malformed:\0",
        ]

    def test_function_returns_raw_accumulated_response(self, pair):
        pair.enqueue_response("BatchCommand finished.\n", "\n")
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "SelectAll:"
        )
        assert response == "BatchCommand finished.\n\n"


class TestStrictExchangeBoundary:
    def test_strict_rejects_eof_after_success_status_without_blank_boundary(self):
        read_pipe = io.StringIO('BatchCommand finished: OK\n')
        with pytest.raises(RuntimeError, match='did not confirm success.*terminal blank boundary'):
            automate_audacity.send_audacity_command(
                io.StringIO(), read_pipe, 'Help:', strict=True
            )

    def test_strict_accepts_success_status_and_terminal_blank_line(self):
        response = 'BatchCommand finished: OK\r\n\r\n'
        actual = automate_audacity.send_audacity_command(
            io.StringIO(), io.StringIO(response), 'Help:', strict=True
        )
        assert actual == response

    def test_strict_rejects_blank_boundary_before_success_status(self):
        with pytest.raises(RuntimeError, match='did not confirm success.*BatchCommand finished status'):
            automate_audacity.send_audacity_command(
                io.StringIO(), io.StringIO('partial\n\n'), 'Help:', strict=True
            )

    def test_strict_rejects_eof_before_success_status(self):
        with pytest.raises(RuntimeError, match='did not confirm success.*BatchCommand finished status'):
            automate_audacity.send_audacity_command(
                io.StringIO(), io.StringIO('partial\n'), 'Help:', strict=True
            )

    def test_strict_preserves_response_size_limit_error(self):
        oversized = 'x' * (1024 * 1024 + 1)
        with pytest.raises(ValueError, match='exceeded 1 MiB'):
            automate_audacity.send_audacity_command(
                io.StringIO(), io.StringIO(oversized), 'Help:', strict=True
            )

    @pytest.mark.parametrize("eol", ["\n", "\r\n"])
    def test_strict_accepts_leading_empty_line_before_completion_status(self, eol):
        response = f"{eol}BatchCommand finished: OK{eol}{eol}"
        actual = automate_audacity.send_audacity_command(
            io.StringIO(), io.StringIO(response), "Help:", strict=True
        )
        assert actual == response

    @pytest.mark.parametrize("eol", ["\n", "\r\n"])
    def test_strict_rejects_leading_empty_lines_followed_by_eof(self, eol):
        with pytest.raises(RuntimeError, match="did not confirm success.*BatchCommand finished status"):
            automate_audacity.send_audacity_command(
                io.StringIO(), io.StringIO(eol), "Help:", strict=True
            )

class TestEmptyLineTerminator:
    def test_consumer_stops_at_first_empty_line(self, pair):
        pair.enqueue_response("line one\n", "line two\n", "\n", "post-terminator\n")
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "SelectAll:"
        )
        assert response == "line one\nline two\n\n"
        assert pair.read_pipe.has_pending()
        assert pair.read_pipe.readline() == "post-terminator\n"

    def test_multi_line_response_fully_drained(self, pair):
        pair.enqueue_response("a\n", "b\n", "c\n", "\n")
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "GetInfo"
        )
        assert response == "a\nb\nc\n\n"
        assert not pair.read_pipe.has_pending()

    def test_blank_only_response_terminates_immediately(self, pair):
        pair.enqueue_response("\n")
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "SelectAll:"
        )
        assert response == "\n"


class TestEofHandling:
    def test_eof_before_any_output_returns_without_hanging(self, pair):
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "SelectAll:"
        )
        assert response == ""

    def test_eof_after_partial_unterminated_line_returns_partial(self, pair):
        pair.enqueue_response("crashed mid-outpu")
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "SelectAll:"
        )
        assert response == "crashed mid-outpu"

    def test_helper_mirrors_send_audacity_command_consumption(self, pair):
        pair.enqueue_response("x\n", "y\n", "\n")
        via_helper = consume_until_empty_line(pair.read_pipe)
        pair.response_lines.clear()
        pair.enqueue_response("x\n", "y\n", "\n")
        via_command = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "same-command"
        )
        assert via_helper == via_command


class TestPolishedManifestSync:
    def test_probe_audio_file_nonexistent(self):
        assert automate_audacity.probe_audio_file("nonexistent_file.wav") is None

    def test_probe_audio_file_valid_wav(self, tmp_path):
        wav_path = str(tmp_path / "test.wav")
        import wave

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"\x00\x00" * 24000)  # 1.0 second

        info = automate_audacity.probe_audio_file(wav_path)
        assert info is not None
        assert info["duration"] == 1.0
        assert info["framerate"] == 24000
        assert info["channels"] == 1
        assert info["sampwidth"] == 2

    def test_sync_polished_audio_manifest(self, tmp_path):
        import json
        import wave

        run_dir = tmp_path / "run_test"
        run_dir.mkdir()
        polished_dir = run_dir / "polished_chapters"
        polished_dir.mkdir()

        # Create dummy Chapter_1.wav of 2.0s
        chap1_path = str(polished_dir / "Chapter_1.wav")
        with wave.open(chap1_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"\x00\x00" * 48000)  # 2.0 seconds

        manifest_data = {
            "silence_padding_sec": 0.3,
            "cumulative_duration_sec": 5.0,
            "segments": [
                {
                    "id": "001",
                    "index": 1,
                    "audio_file": "voice_chapters/Chapter_1.wav",
                    "text_arabic": "مرحبا بكم",
                    "start_time": 0.0,
                    "end_time": 5.0,
                    "duration": 5.0,
                    "status": "COMPLETED",
                }
            ],
        }
        manifest_path = run_dir / "audio_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f)

        automate_audacity.sync_polished_audio_manifest(str(run_dir))

        with open(manifest_path, encoding="utf-8") as f:
            updated = json.load(f)

        seg = updated["segments"][0]
        assert seg["audio_file"] == "polished_chapters/Chapter_1.wav"
        assert seg["duration"] == 2.0
        assert seg["start_time"] == 0.0
        assert seg["end_time"] == 2.0
        assert updated["cumulative_duration_sec"] == 2.3

