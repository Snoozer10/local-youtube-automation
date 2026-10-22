from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass

import pytest

from youtube_automation.audio.audacity_client import send_audacity_command
from youtube_automation.audio.audacity_readiness_probe import (
    HELP_COMMAND,
    ProbeAbort,
    _WorkerJournal,
    run_one_help_probe,
    validate_live_authorization,
    wait_for_supervisor_ready,
)
from youtube_automation.core.window_readiness import (
    WindowObservation,
    WindowRole,
    WindowSnapshot,
)


@dataclass
class FakeProcess:
    pid: int = 321
    exit_code: int | None = None

    def poll(self):
        return self.exit_code


class FakeBackend:
    creation_time = 1234.5
    executable = r"C:\Program Files\Audacity\Audacity.exe"

    def __init__(
        self,
        role: WindowRole = WindowRole.MAIN,
        *,
        creation_time: float = 1234.5,
        observed_creation_time: float | None = None,
        role_sequence=None,
        creation_sequence=None,
    ):
        self.role = role
        self.creation_time = creation_time
        self.observed_creation_time = observed_creation_time or creation_time
        self.role_sequence = list(role_sequence or [])
        self.creation_sequence = list(creation_sequence or [])
        self.observe_calls = 0
        self.capture_calls = []

    def observe(self, pid: int) -> WindowSnapshot:
        self.observe_calls += 1
        role = self.role_sequence[self.observe_calls - 1] if self.observe_calls <= len(self.role_sequence) else self.role
        creation = (
            self.creation_sequence[self.observe_calls - 1]
            if self.observe_calls <= len(self.creation_sequence)
            else self.observed_creation_time
        )
        return WindowSnapshot(
            pid,
            creation,
            self.executable,
            [WindowObservation(77, pid, role, visible=True, modal=role is WindowRole.MODAL)],
        )

    def capture(self, hwnd, pid, creation_time, reason, timeout):
        self.capture_calls.append((hwnd, pid, creation_time, reason, timeout))
        return {
            "hwnd": hwnd,
            "pid": pid,
            "creation_time": creation_time,
            "image_path": "owned.bmp",
            "sha256": "a" * 64,
        }


class FakePipeWriter:
    def __init__(self):
        self.data = []
        self.closed = False

    def write(self, data):
        self.data.append(data)

    def flush(self):
        return None

    def close(self):
        self.closed = True

    def value(self):
        return "".join(self.data)


class FakePipeReader:
    def __init__(self, lines=None):
        self.lines = iter(lines or [])
        self.closed = False

    def readline(self):
        return next(self.lines, "")

    def close(self):
        self.closed = True


def _journal(tmp_path):
    (tmp_path / "journal").mkdir()
    return _WorkerJournal(tmp_path, clock=lambda: "2026-10-13T00:00:00Z")


def _inspection(run_id, process, backend, capture, identity):
    return {
        "schema": 1,
        "run_id": run_id,
        "approved": True,
        "reviewer": "offline-test-reviewer",
        "inspected_utc": "2026-10-13T00:00:00Z",
        "pid": process.pid,
        "creation_time": backend.creation_time,
        "executable": backend.executable,
        "executable_sha256": "b" * 64,
        "hwnd": identity["hwnd"],
        "image_sha256": capture["sha256"],
    }


def _run(tmp_path, role=WindowRole.MAIN, *, backend=None, inspect=None, sender=None, pipe_owner=True, default_inspector=False):
    run_id = tmp_path.name
    process = FakeProcess()
    backend = backend or FakeBackend(role)
    opened = []
    writer = FakePipeWriter()
    reader = FakePipeReader(["BatchCommand finished: OK\n", "\n"])

    def open_pipes(owned):
        opened.append(owned.pid)
        return writer, reader

    def inspect_capture(capture, identity):
        if inspect:
            return inspect(capture, identity)
        return _inspection(run_id, process, backend, capture, identity)

    if default_inspector:
        inspect_capture = None

    result = run_one_help_probe(
        run_dir=tmp_path,
        process=process,
        executable_path=backend.executable,
        backend=backend,
        inspect_capture=inspect_capture,
        open_pipes=open_pipes,
        verify_pipe_owner=lambda _write, _read, pid: pipe_owner and pid == process.pid,
        send_command=sender or send_audacity_command,
        executable_sha256="b" * 64,
        run_id=run_id,
        journal=_journal(tmp_path),
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
    )
    return result, opened, writer, reader, process, backend


class NoWindowBackend(FakeBackend):
    def observe(self, pid: int) -> WindowSnapshot:
        self.observe_calls += 1
        return WindowSnapshot(
            pid, self.observed_creation_time, self.executable, []
        )


class DisappearingWindowBackend(FakeBackend):
    def __init__(self, disappear_at: int):
        super().__init__()
        self.disappear_at = disappear_at

    def observe(self, pid: int) -> WindowSnapshot:
        snapshot = super().observe(pid)
        if self.observe_calls == self.disappear_at:
            return WindowSnapshot(
                pid, self.observed_creation_time, self.executable, []
            )
        return snapshot


def test_missing_owned_window_aborts_before_pipes_without_inspection_receipt(tmp_path):
    backend = NoWindowBackend()
    result, opened, writer, _reader, _process, backend = _run(
        tmp_path, backend=backend
    )

    assert result.ok is False
    assert result.command_count == 0
    assert opened == []
    assert writer.value() == ""
    assert backend.capture_calls == []
    assert not (tmp_path / "capture" / "inspection.json").exists()


@pytest.mark.parametrize(
    ("disappear_at", "expected_opened"), [(5, []), (6, [321])]
)
def test_disappearing_owned_window_aborts_at_post_capture_and_pre_send_checks(
    tmp_path, disappear_at, expected_opened
):
    backend = DisappearingWindowBackend(disappear_at)
    result, opened, writer, reader, _process, backend = _run(
        tmp_path, backend=backend
    )

    assert result.ok is False
    assert result.command_count == 0
    assert opened == expected_opened
    assert writer.value() == ""
    assert [call[3] for call in backend.capture_calls] == [
        "one_help_preflight",
        "one_help_abort",
    ]
    if expected_opened:
        assert reader.closed and writer.closed


@pytest.mark.parametrize(
    "role",
    [WindowRole.RECOVERY, WindowRole.WELCOME, WindowRole.MODAL, WindowRole.OTHER],
)
def test_unsafe_visible_window_states_never_open_or_send_pipes(tmp_path, role):
    result, opened, writer, _reader, _process, _backend = _run(tmp_path, role)

    assert result.ok is False
    assert result.command_count == 0
    assert opened == []
    assert writer.value() == ""
    assert json.loads((tmp_path / "worker_result.json").read_text())[
        "command_count"
    ] == 0


def test_identity_mismatch_and_missing_pixel_approval_send_zero_commands(tmp_path):
    mismatched = FakeBackend(observed_creation_time=9999.0)
    result, opened, writer, *_ = _run(tmp_path, backend=mismatched)
    assert result.command_count == 0
    assert opened == []
    assert writer.value() == ""

    other = tmp_path / "missing-approval"
    other.mkdir()
    result, opened, writer, *_ = _run(other, inspect=lambda *_: None)
    assert result.command_count == 0
    assert opened == []
    assert writer.value() == ""


def test_ready_run_sends_one_exact_help_and_seals_receipt(tmp_path):
    result, opened, writer, reader, _process, backend = _run(tmp_path)

    assert result.ok is True
    assert result.command_count == 1
    assert result.state == "complete"
    assert opened == [321]
    assert writer.value() == HELP_COMMAND + "\r\n\0"
    assert reader.closed and writer.closed
    assert backend.observe_calls >= 4
    assert json.loads((tmp_path / "worker_result.json").read_text())["command_count"] == 1
    events = [json.loads(path.read_text()) for path in sorted((tmp_path / "journal").glob("*.json"))]
    before = [event for event in events if event["kind"] == "before_send"]
    after = [event for event in events if event["kind"] == "after_send"]
    assert len(before) == len(after) == 1
    assert before[0]["command"] == after[0]["command"] == HELP_COMMAND
    assert before[0]["command_count"] == "unknown"
    assert after[0]["command_count"] == 1


def test_sender_failure_after_before_send_is_unknown_and_never_retried(tmp_path):
    calls = []

    def uncertain_sender(*_args, **_kwargs):
        calls.append(1)
        raise TimeoutError("response did not arrive")

    result, opened, writer, *_ = _run(tmp_path, sender=uncertain_sender)
    assert result.ok is False
    assert result.command_count == "unknown"
    assert len(calls) == 1
    assert opened == [321]
    events = [json.loads(path.read_text()) for path in sorted((tmp_path / "journal").glob("*.json"))]
    assert any(event["kind"] == "before_send" for event in events)
    assert not any(event["kind"] == "after_send" for event in events)
    assert json.loads((tmp_path / "worker_result.json").read_text())["command_count"] == "unknown"


def test_window_modal_after_capture_aborts_before_pipe_acquisition(tmp_path):
    backend = FakeBackend(role_sequence=[
        WindowRole.MAIN, WindowRole.MAIN, WindowRole.MAIN, WindowRole.RECOVERY,
    ])
    result, opened, writer, *_ = _run(tmp_path, backend=backend)
    assert result.command_count == 0
    assert opened == []
    assert writer.value() == ""


def test_window_modal_after_pipe_acquisition_aborts_before_any_command(tmp_path):
    backend = FakeBackend(role_sequence=[
        WindowRole.MAIN, WindowRole.MAIN, WindowRole.MAIN,
        WindowRole.MAIN, WindowRole.MAIN, WindowRole.WELCOME,
    ])
    result, opened, writer, reader, *_ = _run(tmp_path, backend=backend)
    assert result.command_count == 0
    assert opened == [321]
    assert writer.value() == ""
    assert writer.closed and reader.closed


def test_process_creation_identity_change_after_capture_or_pipes_aborts(tmp_path):
    after_capture = FakeBackend(creation_sequence=[1234.5, 1234.5, 1234.5, 9999.0])
    result, opened, writer, *_ = _run(tmp_path, backend=after_capture)
    assert result.command_count == 0
    assert opened == []
    assert writer.value() == ""

    after_pipes = tmp_path / "identity-after-pipes"
    after_pipes.mkdir()
    backend = FakeBackend(creation_sequence=[1234.5, 1234.5, 1234.5, 1234.5, 1234.5, 9999.0])
    result, opened, writer, reader, *_ = _run(after_pipes, backend=backend)
    assert result.command_count == 0
    assert opened == [321]
    assert writer.value() == ""
    assert writer.closed and reader.closed


def test_pipe_server_pid_mismatch_aborts_before_help_send(tmp_path):
    result, opened, writer, reader, *_ = _run(tmp_path, pipe_owner=False)
    assert result.command_count == 0
    assert opened == [321]
    assert writer.value() == ""
    assert writer.closed and reader.closed


def test_supervisor_gate_requires_matching_worker_pid(tmp_path):
    clock = iter([1.0, 1.02])
    with pytest.raises(ProbeAbort, match="supervisor_gate_timeout"):
        wait_for_supervisor_ready(
            tmp_path,
            worker_pid=321,
            timeout_sec=0.01,
            monotonic=lambda: next(clock),
            sleep=lambda _seconds: None,
        )

    (tmp_path / "job_ready").write_text(json.dumps({"schema": 1, "worker_pid": 321}))
    assert wait_for_supervisor_ready(tmp_path, worker_pid=321)["worker_pid"] == 321
    with pytest.raises(ProbeAbort, match="supervisor_gate_identity_mismatch"):
        wait_for_supervisor_ready(tmp_path, worker_pid=999)


def test_live_grant_must_be_run_bound_single_use_and_current(tmp_path):
    grant = tmp_path / "grant.json"
    grant.write_text(json.dumps({
        "schema": 1,
        "run_id": "run-a",
        "authorize_launch": True,
        "authorize_help": True,
        "max_launches": 1,
        "max_pipe_commands": 1,
        "executable_sha256": "b" * 64,
        "expires_utc": "2026-10-13T01:00:00Z",
    }))
    from datetime import datetime, timezone

    assert validate_live_authorization(
        grant,
        run_id="run-a",
        executable_sha256="b" * 64,
        now=datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc),
    )["max_pipe_commands"] == 1
    with pytest.raises(ProbeAbort, match="separate_live_authorization_missing_or_invalid"):
        validate_live_authorization(
            grant,
            run_id="run-b",
            executable_sha256="b" * 64,
            now=datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc),
        )


def _mock_native_pipe_api(monkeypatch, owners, *, api_result=True):
    import ctypes
    from ctypes import wintypes
    from types import SimpleNamespace

    import youtube_automation.audio.audacity_readiness_probe as probe

    class NativeFunction:
        def __init__(self):
            self.argtypes = None
            self.restype = None

        def __call__(self, handle, output):
            if not api_result:
                return False
            ctypes.cast(output, ctypes.POINTER(wintypes.ULONG)).contents.value = owners[int(handle.value)]
            return True

    native_function = NativeFunction()
    monkeypatch.setattr(probe, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(probe, "msvcrt", SimpleNamespace(get_osfhandle=lambda fd: fd + 100))
    monkeypatch.setattr(probe.ctypes, "WinDLL", lambda *_args, **_kwargs: SimpleNamespace(
        GetNamedPipeServerProcessId=native_function
    ), raising=False)
    return probe, native_function


def test_native_pipe_owner_verifies_both_server_pids_with_mocked_api(monkeypatch):
    from types import SimpleNamespace

    probe, native_function = _mock_native_pipe_api(monkeypatch, {101: 321, 102: 321})
    assert probe.verify_native_pipe_owner(
        SimpleNamespace(fileno=lambda: 1), SimpleNamespace(fileno=lambda: 2), 321
    ) is True
    assert len(native_function.argtypes) == 2


def test_native_pipe_owner_rejects_wrong_server_pid(monkeypatch):
    from types import SimpleNamespace

    probe, _ = _mock_native_pipe_api(monkeypatch, {101: 321, 102: 999})
    assert probe.verify_native_pipe_owner(
        SimpleNamespace(fileno=lambda: 1), SimpleNamespace(fileno=lambda: 2), 321
    ) is False


def test_native_pipe_owner_fails_closed_when_api_or_handle_read_fails(monkeypatch):
    from types import SimpleNamespace

    probe, _ = _mock_native_pipe_api(monkeypatch, {}, api_result=False)
    assert probe.verify_native_pipe_owner(
        SimpleNamespace(fileno=lambda: 1), SimpleNamespace(fileno=lambda: 2), 321
    ) is False

    monkeypatch.setattr(probe.ctypes, "WinDLL", lambda *_args, **_kwargs: SimpleNamespace(), raising=False)
    assert probe.verify_native_pipe_owner(
        SimpleNamespace(fileno=lambda: 1), SimpleNamespace(fileno=lambda: 2), 321
    ) is False

    probe, _ = _mock_native_pipe_api(monkeypatch, {101: 321, 102: 321})

    def fail_fileno():
        raise OSError("offline handle failure")

    assert probe.verify_native_pipe_owner(
        SimpleNamespace(fileno=fail_fileno), SimpleNamespace(fileno=lambda: 2), 321
    ) is False


def test_default_inspector_writes_current_run_receipt_and_sends_one_help(tmp_path):
    capture_dir = tmp_path / "capture"
    capture_dir.mkdir()
    image_path = capture_dir / "owned-window.bmp"
    width = height = 2
    pixels = b"\x01\x02\x03\x04\x05\x06\x00\x00" * height
    pixel_offset = 54
    image_size = pixel_offset + len(pixels)
    image = (
        struct.pack("<2sIHHI", b"BM", image_size, 0, 0, pixel_offset)
        + struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 0, 0, 0, 0)
        + pixels
    )
    image_path.write_bytes(image)
    backend = FakeBackend()

    def capture(hwnd, pid, creation_time, _reason, _timeout):
        return {
            "hwnd": hwnd,
            "pid": pid,
            "creation_time": creation_time,
            "image_path": str(image_path),
            "sha256": hashlib.sha256(image).hexdigest(),
            "utc": "2026-10-13T00:00:01Z",
            "width": width,
            "height": height,
        }

    backend.capture = capture
    result, opened, writer, _reader, process, _backend = _run(
        tmp_path, backend=backend, default_inspector=True
    )

    receipt = json.loads((capture_dir / "inspection.json").read_text(encoding="utf-8"))
    assert result.ok is True
    assert opened == [process.pid]
    assert writer.value() == HELP_COMMAND + "\r\n\0"
    assert receipt["run_id"] == tmp_path.name
    assert receipt["inspection_kind"] == "owned_window_technical"
    assert receipt["image_sha256"] == hashlib.sha256(image).hexdigest()
    assert (receipt["width"], receipt["height"]) == (width, height)
    assert receipt["ready_state"] == "ready"
