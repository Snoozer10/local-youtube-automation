"""Unit tests: Audacity named-pipe IPC command formatting & response handling."""


from mocks.audacity_stub import FakeAudacityPipePair

import automate_audacity


class TestSendAudacityCommand:
    def test_command_sent_with_newline_terminator(self):
        pipes = FakeAudacityPipePair()
        automate_audacity.send_audacity_command(pipes, pipes, "SelectAll:")
        assert pipes.sent_commands[-1] == "SelectAll:"
        assert len(pipes.sent_commands) >= 1

    def test_response_read_until_blank_terminator(self):
        pipes = FakeAudacityPipePair(responses=[["BatchCommand: OK", "elapsed 0.2 sec", ""]])
        response = automate_audacity.send_audacity_command(pipes, pipes, "SelectAll:")
        assert "BatchCommand: OK" in response
        assert "elapsed" in response

    def test_eof_on_pipe_returns_partial_response(self):
        pipes = FakeAudacityPipePair(auto_ack=False)
        pipes.queue_response(["dangling output"])  # no blank terminator, then EOF
        response = automate_audacity.send_audacity_command(pipes, pipes, "Export2:")
        assert "dangling output" in response  # graceful, no exception/hang

    def test_macro_import_formatting(self):
        """Command strings must follow <Cmd>:<Param>="<Val>" protocol shape."""
        pipes = FakeAudacityPipePair()
        cmd = 'Import2:Filename="C:\\\\audio\\\\ep.wav"'
        automate_audacity.send_audacity_command(pipes, pipes, cmd)
        assert pipes.sent_commands[-1] == cmd


class TestPresetApplication:
    def test_missing_preset_reports_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pipes = FakeAudacityPipePair()
        ok = automate_audacity.apply_preset_file(pipes, pipes, str(tmp_path / "none.txt"))
        assert ok is False

    def test_preset_lines_dispatched_as_commands(self, tmp_path):
        preset = tmp_path / "preset.txt"
        preset.write_text("SelectAll:\nNoiseGate:Threshold=-30\n", encoding="utf-8")
        pipes = FakeAudacityPipePair()
        ok = automate_audacity.apply_preset_file(pipes, pipes, str(preset))
        assert ok is True
        sent = [c.split(":")[0] for c in pipes.sent_commands if c.strip()]
        assert "SelectAll" in sent and "NoiseGate" in sent
