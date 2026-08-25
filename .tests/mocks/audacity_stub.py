"""Fake Audacity named-pipe doubles (\\\\.\\pipe\\ToSrvPipe / FromSrvPipe)."""


class FakeAudacityPipePair:
    """In-memory write/read pipe pair mimicking Audacity mod-script-pipe."""

    def __init__(self, responses=None, auto_ack=True):
        self.sent_commands = []
        self._queued = []
        self._buffer = []
        for group in responses or []:
            self._queued.append([str(ln) for ln in group])
        self.auto_ack = auto_ack
        self.closed_write = False
        self.closed_read = False

    def queue_response(self, *lines):
        self._queued.append([str(ln) for ln in lines])

    def _load_next(self):
        if self._queued:
            lines = self._queued.pop(0)
        elif self.auto_ack:
            lines = ["BatchCommand finished successfully", ""]
        else:
            lines = [""]
        for line in lines:
            self._buffer.append(line + "\n")

    # -- write side -----------------------------------------------------
    def write(self, data):
        self.sent_commands.append(str(data).rstrip("\n"))

    def flush(self):
        pass

    def close(self):
        self.closed_write = True

    # -- read side ------------------------------------------------------
    def readline(self):
        if not self._buffer:
            self._load_next()
        return self._buffer.pop(0)

    def close_read(self):
        self.closed_read = True
