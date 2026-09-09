"""Unit & Diagnostic Drill Tests for 01.02 Audacity Named Pipe IPC."""


import pytest

from .exercise import (
    execute_batch_effects,
    format_audacity_command,
    is_audacity_pipe_available,
    send_audacity_command,
)


class MockPipePair:
    """Simulates duplex Windows Named Pipe behavior in memory."""

    def __init__(self, responses: list[str]) -> None:
        self.written: list[str] = []
        self._responses = responses
        self._resp_index = 0

    def write(self, data: str) -> None:
        self.written.append(data)

    def flush(self) -> None:
        pass

    def readline(self) -> str:
        if self._resp_index < len(self._responses):
            line = self._responses[self._resp_index]
            self._resp_index += 1
            return line
        return ""


@pytest.mark.drill
def test_format_audacity_command() -> None:
    cmd_select = format_audacity_command("SelectAll")
    assert cmd_select == "SelectAll:"

    cmd_import = format_audacity_command("Import2", {"Filename": r"C:\audio\raw.wav"})
    assert 'Import2:Filename="C:\\\\audio\\\\raw.wav"' in cmd_import

    cmd_export = format_audacity_command(
        "Export2", {"Filename": r"C:\audio\out.wav", "NumChannels": 1}
    )
    assert 'Export2:Filename="C:\\\\audio\\\\out.wav" NumChannels=1' in cmd_export


@pytest.mark.drill
def test_send_audacity_command_protocol_termination() -> None:
    # Audacity protocol: command terminates when an empty line is returned
    simulated_responses = [
        "Executing: SelectAll:\n",
        "BatchCommand finished: OK\n",
        "\n",  # Empty line terminator
    ]
    pipe = MockPipePair(simulated_responses)

    resp = send_audacity_command(pipe, pipe, "SelectAll:")

    assert len(pipe.written) == 1
    assert pipe.written[0] == "SelectAll:\n"
    assert "BatchCommand finished: OK" in resp


@pytest.mark.drill
def test_execute_batch_effects_interleaves_select_all() -> None:
    simulated_responses = [
        # SelectAll 1
        "BatchCommand finished: OK\n",
        "\n",
        # Effect 1
        "Applying NoiseGate...\n",
        "BatchCommand finished: OK\n",
        "\n",
        # SelectAll 2
        "BatchCommand finished: OK\n",
        "\n",
        # Effect 2
        "Applying Compressor...\n",
        "BatchCommand finished: OK\n",
        "\n",
    ]
    pipe = MockPipePair(simulated_responses)

    effects = ["NoiseGate:threshold=-30", "Compressor:ratio=3.0"]
    responses = execute_batch_effects(pipe, pipe, effects)

    assert len(responses) == 2
    assert pipe.written == [
        "SelectAll:\n",
        "NoiseGate:threshold=-30\n",
        "SelectAll:\n",
        "Compressor:ratio=3.0\n",
    ]


@pytest.mark.drill
@pytest.mark.skipif(
    not is_audacity_pipe_available(),
    reason=r"Audacity Named Pipe \\.\pipe\ToSrvPipe unavailable (Audacity daemon not running)",
)
def test_live_audacity_pipe_communication() -> None:
    """Pre-flight hardware drill probing live Audacity instance when active."""
    write_pipe = open(r"\\.\pipe\ToSrvPipe", "w", encoding="utf-8")
    read_pipe = open(r"\\.\pipe\FromSrvPipe", encoding="utf-8")
    try:
        response = send_audacity_command(write_pipe, read_pipe, "Help: Command=Help")
        assert "BatchCommand finished: OK" in response or len(response) > 0
    finally:
        write_pipe.close()
        read_pipe.close()
