"""Offline contract tests for Audacity named-pipe framing and reply validation."""

import io

import pytest

from youtube_automation.audio import audacity_client


class _Reader:
    def __init__(self, lines):
        self._lines = iter(lines)
        self.read_count = 0

    def readline(self):
        self.read_count += 1
        try:
            return next(self._lines)
        except StopIteration:
            return ""


class _GuardedReader(_Reader):
    def __init__(self, lines):
        self._lines_source = list(lines)
        super().__init__(self._lines_source)

    def readline(self):
        if self.read_count >= len(self._lines_source):
            raise AssertionError("reader advanced past the blank frame boundary")
        return super().readline()


class _TextWrapperWriter:
    """Count calls while retaining real TextIOWrapper newline behavior."""

    def __init__(self):
        self.buffer = io.BytesIO()
        self.stream = io.TextIOWrapper(self.buffer, encoding="utf-8", newline="")
        self.writes = []
        self.flush_count = 0

    def write(self, text):
        self.writes.append(text)
        return self.stream.write(text)

    def flush(self):
        self.flush_count += 1
        self.stream.flush()


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("win32", "Help: Command=Help\r\n\0"), ("linux", "Help: Command=Help\n")],
)
def test_command_frame_uses_platform_eol_and_one_write_flush(
    monkeypatch, platform, expected
):
    monkeypatch.setattr(audacity_client.sys, "platform", platform)
    writer = _TextWrapperWriter()
    reader = _Reader(["BatchCommand finished: OK\n", "\n"])

    audacity_client.send_audacity_command(writer, reader, "Help: Command=Help")

    assert writer.writes == [expected]
    assert writer.flush_count == 1
    assert writer.buffer.getvalue() == expected.encode("utf-8")


def test_contentful_blank_boundary_without_status_fails_promptly():
    reader = _GuardedReader(["Help response without status\r\n", "\r\n"])

    with pytest.raises(RuntimeError, match="did not confirm success"):
        audacity_client.send_audacity_command(
            io.StringIO(), reader, "Help: Command=Help", strict=True, timeout_sec=1
        )

    assert reader.read_count == 2


@pytest.mark.parametrize(
    "reply",
    [
        "Help response\n\n",
        "BatchCommand finished: Failed\n\n",
    ],
)
def test_strict_reply_requires_explicit_ok_status(reply):
    with pytest.raises(RuntimeError, match="did not confirm success"):
        audacity_client.send_audacity_command(
            io.StringIO(),
            _Reader(reply.splitlines(keepends=True)),
            "Help:",
            strict=True,
            timeout_sec=1,
        )


def test_strict_reply_accepts_marked_ok_status():
    response = "Help response\r\nBatchCommand finished: OK\r\n\r\n"
    reader = _Reader(response.splitlines(keepends=True))

    result = audacity_client.send_audacity_command(
        io.StringIO(), reader, "Help:", strict=True, timeout_sec=1
    )

    assert result == response


@pytest.mark.parametrize(("platform", "newline"), [("win32", ""), ("linux", None)])
def test_pipe_opener_uses_newline_empty_only_on_windows(monkeypatch, platform, newline):
    monkeypatch.setattr(audacity_client.sys, "platform", platform)
    calls = []
    pipes = [object(), object()]

    def opener(*args, **kwargs):
        calls.append((args, kwargs))
        return pipes[len(calls) - 1]

    class OwnedProcess:
        def poll(self):
            return None

    opened = audacity_client._open_audacity_pipes(OwnedProcess(), pipe_opener=opener)

    assert opened == tuple(pipes)
    expected_kwargs = {"encoding": "utf-8"}
    if newline is not None:
        expected_kwargs["newline"] = newline
    assert calls == [
        ((r"\\.\pipe\ToSrvPipe", "w"), expected_kwargs),
        ((r"\\.\pipe\FromSrvPipe",), expected_kwargs),
    ]
