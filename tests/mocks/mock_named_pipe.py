"""Duck-typed stand-in for the Audacity mod-script-pipe pair.

Simulates \\\\.\\pipe\\ToSrvPipe (write) and \\\\.\\pipe\\FromSrvPipe (read)
following the protocol consumed by automate_audacity.send_audacity_command:
commands are framed with a trailing newline; every server response is a run of
newline-terminated lines followed by a single EMPTY line ("\\n") that
terminates the reply. A readline() returning "" means EOF/crashed pipe.
"""

from __future__ import annotations


class MockWritePipe:
    def __init__(self, pair: NamedPipePair) -> None:
        self._pair = pair

    def write(self, data: str) -> int:
        self._pair.sent_chunks.append(data)
        return len(data)

    def flush(self) -> None:
        self._pair.flushes += 1


class MockReadPipe:
    def __init__(self, pair: NamedPipePair) -> None:
        self._pair = pair

    def readline(self) -> str:
        if self._pair.response_lines:
            return self._pair.response_lines.pop(0)
        return ""

    def has_pending(self) -> bool:
        return bool(self._pair.response_lines)


class NamedPipePair:
    def __init__(self) -> None:
        self.sent_chunks: list[str] = []
        self.response_lines: list[str] = []
        self.flushes: int = 0
        self.write_pipe = MockWritePipe(self)
        self.read_pipe = MockReadPipe(self)

    @property
    def sent_text(self) -> str:
        return "".join(self.sent_chunks)

    @property
    def sent_commands(self) -> list[str]:
        return [c[:-1] if c.endswith("\n") else c for c in self.sent_chunks]

    def enqueue_response(self, *lines: str) -> None:
        """Queue canned server output verbatim.

        The terminating empty line is a bare newline ("\\n"), NOT "" — an
        empty string is reserved for EOF (crashed/closed pipe).
        """
        self.response_lines.extend(lines)


def consume_until_empty_line(read_pipe: MockReadPipe) -> str:
    """Mirror of automate_audacity.send_audacity_command's consumption loop."""
    response = ""
    while True:
        line = read_pipe.readline()
        if not line:
            break
        response += line
        if line.strip() == "":
            break
    return response


if __name__ == "__main__":
    pair = NamedPipePair()
    pair.enqueue_response("BatchCommand finished.\n", "\n", "must-not-leak\n")
    out = consume_until_empty_line(pair.read_pipe)
    assert out == "BatchCommand finished.\n\n", repr(out)
    assert pair.read_pipe.has_pending(), "post-terminator lines must stay queued"
    assert consume_until_empty_line(pair.read_pipe) == "must-not-leak\n"
    assert consume_until_empty_line(pair.read_pipe) == "", "EOF must not hang"
    print("mock_named_pipe self-test OK")
