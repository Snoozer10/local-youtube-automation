import pytest

from youtube_automation.audio import audacity_client
from youtube_automation.core.window_readiness import (
    ReadinessState,
    WindowObservation,
    WindowRole,
    WindowSnapshot,
)


class FakeProcess:
    pid = 321

    def poll(self):
        return None


class FakePipe:
    def __init__(self, name):
        self.name = name
        self.closed = False

    def close(self):
        self.closed = True


def test_unsafe_readiness_states_open_no_pipes_and_send_no_commands(monkeypatch, tmp_path):
    unsafe = [
        ReadinessState.RECOVERY_MODAL,
        ReadinessState.WELCOME_MODAL,
        ReadinessState.UNKNOWN_MODAL,
        ReadinessState.UNOWNED,
        ReadinessState.PID_EXITED,
        ReadinessState.TIMEOUT,
        ReadinessState.ERROR,
    ]
    for state in unsafe:
        calls = {"pipes": [], "commands": []}

        def blocked(*_args, _state=state, **_kwargs):
            raise RuntimeError(f"{_state.value}:blocked")

        monkeypatch.setattr(audacity_client, "_ensure_audacity_ready", blocked)
        with pytest.raises(RuntimeError, match=state.value):
            audacity_client._open_ready_audacity_session(
                FakeProcess(), "Audacity.exe", str(tmp_path),
                pipe_opener=lambda *args, calls=calls, **kwargs: calls["pipes"].append((args, kwargs)),
                command_sender=lambda *args, calls=calls, **kwargs: calls["commands"].append(args),
            )
        assert calls == {"pipes": [], "commands": []}


def test_readiness_is_rechecked_before_each_handshake_command(monkeypatch, tmp_path):
    events = []
    writer, reader = FakePipe("write"), FakePipe("read")
    checks = iter([None, None, None])

    def ready(*_args):
        next(checks)
        events.append("ready")

    def open_pipe(*args, **kwargs):
        events.append("open")
        return writer if len(args) > 1 and args[1] == "w" else reader

    def send(_writer, _reader, command, **kwargs):
        events.append(command)

    monkeypatch.setattr(audacity_client, "_ensure_audacity_ready", ready)
    got = audacity_client._open_ready_audacity_session(
        FakeProcess(), "Audacity.exe", str(tmp_path),
        pipe_opener=open_pipe, command_sender=send,
        pipe_owner_verifier=lambda *_args: True,
    )
    assert got == (writer, reader)
    assert events == [
        "ready", "open", "open", "ready", "Help: Command=Help", "ready", "SelectAll:"
    ]


def test_second_readiness_failure_closes_open_pipes_without_commands(monkeypatch, tmp_path):
    writer, reader = FakePipe("write"), FakePipe("read")
    checks = iter([None, RuntimeError("welcome_modal")])
    commands = []

    def ready(*_args):
        outcome = next(checks)
        if isinstance(outcome, Exception):
            raise outcome

    def open_pipe(*args, **kwargs):
        return writer if len(args) > 1 and args[1] == "w" else reader

    monkeypatch.setattr(audacity_client, "_ensure_audacity_ready", ready)
    with pytest.raises(RuntimeError, match="welcome_modal"):
        audacity_client._open_ready_audacity_session(
            FakeProcess(), "Audacity.exe", str(tmp_path),
            pipe_opener=open_pipe,
            command_sender=lambda *args, **kwargs: commands.append(args),
        )
    assert writer.closed and reader.closed


@pytest.mark.parametrize(
    ("server_pids", "query_error"),
    [
        ({"write": 321, "read": 222}, False),
        ({"write": 222, "read": 321}, False),
        ({"write": None, "read": 321}, False),
        ({"write": 321, "read": None}, False),
        ({"write": 321, "read": 321}, True),
    ],
)
def test_pipe_owner_mismatch_or_unknown_closes_both_before_handshake(
    monkeypatch, tmp_path, server_pids, query_error
):
    writer, reader = FakePipe("write"), FakePipe("read")
    commands = []
    monkeypatch.setattr(audacity_client, "_ensure_audacity_ready", lambda *_a, **_k: None)
    monkeypatch.setattr(audacity_client, "_open_audacity_pipes", lambda *_a, **_k: (writer, reader))

    def verify(write_pipe, read_pipe, expected_pid):
        assert expected_pid == 321
        if query_error:
            raise OSError("native server PID query failed")
        return all(server_pids[pipe.name] == expected_pid for pipe in (write_pipe, read_pipe))

    with pytest.raises(RuntimeError, match="pipe owner"):
        audacity_client._open_ready_audacity_session(
            FakeProcess(),
            "Audacity.exe",
            str(tmp_path),
            command_sender=lambda *args, **kwargs: commands.append(args),
            pipe_owner_verifier=verify,
        )

    assert commands == []
    assert writer.closed and reader.closed


def test_pipe_owner_success_checks_pair_then_sends_handshake(monkeypatch, tmp_path):
    writer, reader = FakePipe("write"), FakePipe("read")
    checks, commands = [], []
    monkeypatch.setattr(audacity_client, "_ensure_audacity_ready", lambda *_a, **_k: None)
    monkeypatch.setattr(audacity_client, "_open_audacity_pipes", lambda *_a, **_k: (writer, reader))

    def verify(write_pipe, read_pipe, expected_pid):
        checks.append((write_pipe, read_pipe, expected_pid))
        return write_pipe is writer and read_pipe is reader and expected_pid == 321

    result = audacity_client._open_ready_audacity_session(
        FakeProcess(),
        "Audacity.exe",
        str(tmp_path),
        command_sender=lambda write, read, command, **kwargs: commands.append(command),
        pipe_owner_verifier=verify,
    )

    assert result == (writer, reader)
    assert checks == [(writer, reader, 321), (writer, reader, 321)]
    assert commands == ["Help: Command=Help", "SelectAll:"]


def test_native_pipe_owner_check_queries_both_windows_handles(monkeypatch):
    writer, reader = FakePipe("write"), FakePipe("read")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    server_pids = {101: 321, 202: 321}
    native_handles = []

    class NativeFunction:
        argtypes = None
        restype = None

        def __call__(self, handle, server_pid):
            native_handle = getattr(handle, "value", handle)
            native_handles.append(native_handle)
            ctypes.cast(server_pid, ctypes.POINTER(wintypes.ULONG)).contents.value = (
                server_pids[native_handle]
            )
            return True

    class Kernel32:
        GetNamedPipeServerProcessId = NativeFunction()

    writer.fileno = lambda: 11
    reader.fileno = lambda: 22
    monkeypatch.setattr(msvcrt, "get_osfhandle", lambda fd: {11: 101, 22: 202}[fd])
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: Kernel32())
    monkeypatch.setattr(audacity_client.sys, "platform", "win32")

    assert audacity_client._verify_audacity_pipe_owner(writer, reader, 321)
    assert native_handles == [101, 202]

    server_pids[202] = 999
    assert not audacity_client._verify_audacity_pipe_owner(writer, reader, 321)
    assert native_handles == [101, 202, 101, 202]


def test_owned_dsp_command_rejects_foreign_pipe_before_send():
    writer, reader = FakePipe("write"), FakePipe("read")
    commands = []

    with pytest.raises(RuntimeError, match="pipe owner"):
        audacity_client._send_owned_audacity_command(
            writer,
            reader,
            "NoiseGate:",
            expected_pid=321,
            command_sender=lambda *args, **kwargs: commands.append(args),
            pipe_owner_verifier=lambda *_args: False,
            strict=True,
        )

    assert commands == []
    assert writer.closed and reader.closed
    assert commands == []


def test_final_ready_check_rejects_pid_exit(monkeypatch, tmp_path):
    class ExitsAfterReadiness(FakeProcess):
        def __init__(self):
            self.calls = 0

        def poll(self):
            self.calls += 1
            return None if self.calls < 5 else 0

    class Windows:
        creation_time = 42.0
        executable = "Audacity.exe"

        def observe(self, _pid):
            main = WindowObservation(99, 321, WindowRole.MAIN)
            return WindowSnapshot(321, 42.0, "Audacity.exe", [main])

        def capture(self, *_args):
            raise AssertionError("no capture should occur after process exit")

    monkeypatch.setattr(audacity_client, "OwnedAudacityWindows", lambda *_args: Windows())
    with pytest.raises(RuntimeError, match="pid_exited"):
        audacity_client._ensure_audacity_ready(
            ExitsAfterReadiness(), "Audacity.exe", str(tmp_path)
        )


@pytest.mark.parametrize("failure_stage", ["constructor", "readiness_helper"])
def test_readiness_backend_failures_preserve_owned_process_without_opening_pipes(
    monkeypatch, tmp_path, failure_stage
):
    from types import SimpleNamespace

    from youtube_automation.core.audacity_windows import OwnedWindowError

    chapter_dir = tmp_path / "voice_chapters"
    chapter_dir.mkdir()
    (chapter_dir / "Chapter_1.wav").write_bytes(b"audio")
    executable = r"C:\Program Files\Audacity\Audacity.exe"
    subprocess_calls = {"pipes": [], "terminate": [], "kill": []}

    class OwnedProcess(FakeProcess):
        def terminate(self):
            subprocess_calls["terminate"].append(self.pid)

        def kill(self):
            subprocess_calls["kill"].append(self.pid)

    monkeypatch.setattr(audacity_client, "audacity_is_running", lambda: False)
    monkeypatch.setattr(audacity_client, "ensure_audacity_script_pipe_enabled", lambda: None)
    monkeypatch.setattr(audacity_client, "find_preset_file", lambda: None)
    monkeypatch.setattr(audacity_client, "load_checkpoint", lambda _root: [])
    monkeypatch.setattr(audacity_client.subprocess, "Popen", lambda *_a, **_k: OwnedProcess())
    monkeypatch.setattr(
        audacity_client.os.path,
        "exists",
        lambda path: str(path) == executable or str(path) == str(chapter_dir),
    )
    if failure_stage == "constructor":
        monkeypatch.setattr(
            audacity_client,
            "OwnedAudacityWindows",
            lambda *_a, **_k: (_ for _ in ()).throw(OwnedWindowError("inspection failed")),
        )
    else:
        monkeypatch.setattr(
            audacity_client,
            "OwnedAudacityWindows",
            lambda *_a, **_k: SimpleNamespace(
                creation_time=1.0,
                executable=executable,
                observe=lambda _pid: None,
                capture=lambda *_a: None,
            ),
        )
        monkeypatch.setattr(
            audacity_client,
            "wait_for_owned_window_readiness",
            lambda *_a, **_k: (_ for _ in ()).throw(OwnedWindowError("helper failed")),
        )
    monkeypatch.setattr(
        audacity_client,
        "_open_audacity_pipes",
        lambda *_a, **_k: subprocess_calls["pipes"].append(True),
    )

    with pytest.raises(SystemExit):
        audacity_client._process_run(str(tmp_path), adaptive=False)

    assert subprocess_calls == {"pipes": [], "terminate": [], "kill": []}


def test_recovery_readiness_failure_preserves_new_owned_process(monkeypatch, tmp_path):
    chapter_dir = tmp_path / "voice_chapters"
    chapter_dir.mkdir()
    (chapter_dir / "Chapter_1.wav").write_bytes(b"audio")
    executable = r"C:\Program Files\Audacity\Audacity.exe"
    processes = []
    open_calls = []

    class OwnedProcess(FakeProcess):
        def __init__(self, pid):
            self.pid = pid
            self.terminated = False

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

    def spawn(*_args, **_kwargs):
        process = OwnedProcess(321 + len(processes))
        processes.append(process)
        return process

    def open_session(process, *_args):
        open_calls.append(process.pid)
        if len(open_calls) == 2:
            raise audacity_client.AudacityReadinessError("unknown startup window")
        return FakePipe("write"), FakePipe("read")

    monkeypatch.setattr(audacity_client, "audacity_is_running", lambda: False)
    monkeypatch.setattr(audacity_client, "ensure_audacity_script_pipe_enabled", lambda: None)
    monkeypatch.setattr(audacity_client, "find_preset_file", lambda: None)
    monkeypatch.setattr(audacity_client, "load_checkpoint", lambda _root: [])
    monkeypatch.setattr(audacity_client.subprocess, "Popen", spawn)
    monkeypatch.setattr(
        audacity_client.os.path,
        "exists",
        lambda path: str(path) == executable or str(path) == str(chapter_dir),
    )
    monkeypatch.setattr(audacity_client, "_open_ready_audacity_session", open_session)
    monkeypatch.setattr(
        audacity_client,
        "_send_owned_audacity_command",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("synthetic chapter failure")),
    )

    audacity_client._process_run(str(tmp_path), adaptive=False)

    assert open_calls == [321, 322]
    assert processes[0].terminated is True
    assert processes[1].terminated is False
