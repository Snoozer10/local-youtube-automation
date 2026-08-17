"""Shared ffmpeg subprocess stubs for compile_video tests."""

import io


class FakePopen:
    """Minimal subprocess.Popen stand-in for the chunked render loop.

    render_chunk/assemble_final_video read stderr via readline() until EOF and
    poll() is not None, then call wait() and read returncode.
    """

    def __init__(self, cmd, **kwargs):
        self.cmd = list(cmd)
        self.returncode = 0
        self.stderr = io.StringIO("")
        self.stdout = io.StringIO("")

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def communicate(self, *args, **kwargs):
        return "", ""

    def kill(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False