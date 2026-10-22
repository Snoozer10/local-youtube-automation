"""Isolated, exactly-one-Help Audacity readiness probe.

This module is separate from the production polishing lifecycle. It never calls
the production session opener and has no SelectAll/DSP path. A future live run
requires an explicit run-bound authorization file and a current pixel-inspection
receipt; tests exercise only injected fakes.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, overload

from youtube_automation.core.audacity_windows import OwnedAudacityWindows
from youtube_automation.core.window_readiness import (
    ReadinessState,
    WindowRole,
    wait_for_owned_window_readiness,
)

msvcrt: ModuleType | None
try:
    import msvcrt as _msvcrt
    msvcrt = _msvcrt
except ImportError:  # pragma: no cover - Windows-only live backend
    msvcrt = None

AUDACITY_EXE = Path(r"C:\Program Files\Audacity\Audacity.exe")
AUDACITY_EXE_SHA256 = "300a173a11ebed0d5786e5d5ed984bd812e6e9b944c58c9ae97233e52dbed33f"
HELP_COMMAND = "Help: Command=Help"
MAX_PIPE_COMMANDS = 1
READY_TIMEOUT_SEC = 30.0
READY_INTERVAL_SEC = 0.5
READY_STABLE_OBSERVATIONS = 3
CAPTURE_TIMEOUT_SEC = 5.0
PIPE_ACQUISITION_TIMEOUT_SEC = 25.0
HELP_RESPONSE_TIMEOUT_SEC = 30.0


class ProbeAbort(RuntimeError):
    """Fail-closed probe stop, including the command-count certainty state."""

    def __init__(self, reason: str, command_count: int | str = 0):
        super().__init__(reason)
        self.reason = reason
        self.command_count = command_count


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    run_id: str
    command_count: int | str
    state: str
    reason: str
    receipt_path: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class _WorkerJournal:
    """Exclusive, fsynced worker events in the supervisor-owned journal dir."""

    def __init__(self, run_dir: Path, *, clock: Callable[[], str] = _utc_now):
        self.run_dir = run_dir.resolve()
        self.directory = self.run_dir / "journal"
        if not self.directory.is_dir():
            raise ProbeAbort("supervisor_journal_directory_missing")
        self.clock = clock
        self.seq = 0

    def write(self, kind: str, phase: str, **fields: Any) -> Path:
        self.seq += 1
        payload = {
            "seq": self.seq,
            "kind": kind,
            "phase": phase,
            "utc": self.clock(),
            **fields,
        }
        path = self.directory / f"{self.seq:06d}.json"
        _exclusive_atomic_json(path, payload)
        return path


def _exclusive_atomic_json(path: Path, payload: dict[str, Any]) -> None:
    """Publish one complete JSON receipt without replacing prior evidence."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and fails if the destination exists.
        os.link(temporary, path)
    finally:
        os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def wait_for_supervisor_ready(
    run_dir: str | Path,
    *,
    worker_pid: int,
    timeout_sec: float = 10.0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Wait for the parent Job Object acknowledgement before native work."""
    if type(worker_pid) is not int or worker_pid <= 0 or timeout_sec <= 0:
        raise ProbeAbort("invalid_supervisor_gate")
    root = Path(run_dir).resolve()
    ready = root / "job_ready"
    deadline = monotonic() + timeout_sec
    while monotonic() < deadline:
        try:
            if ready.is_file() and not ready.is_symlink():
                raw = ready.read_bytes()
                if len(raw) > 4096:
                    raise ProbeAbort("supervisor_gate_invalid")
                payload = json.loads(raw.decode("utf-8"))
                if (
                    not isinstance(payload, dict)
                    or payload.get("schema") != 1
                    or payload.get("worker_pid") != worker_pid
                ):
                    raise ProbeAbort("supervisor_gate_identity_mismatch")
                return payload
        except ProbeAbort:
            raise
        except Exception:
            raise ProbeAbort("supervisor_gate_invalid") from None
        sleep(min(0.05, max(0.0, deadline - monotonic())))
    raise ProbeAbort("supervisor_gate_timeout")


@overload
def _single_ready_hwnd(snapshot: Any, process: Any, windows: Any, *,
                       allow_headless: bool = False, return_snapshot: Literal[False] = False) -> int: ...


@overload
def _single_ready_hwnd(snapshot: Any, process: Any, windows: Any, *,
                       allow_headless: bool = False, return_snapshot: Literal[True]) -> tuple[int, Any]: ...


def _single_ready_hwnd(
    snapshot: Any, process: Any, windows: Any, *, allow_headless: bool = False, return_snapshot: bool = False
) -> int | tuple[int, Any]:
    if process.poll() is not None:
        raise ProbeAbort("owned_process_exited")
    snapshot = windows.observe(process.pid)
    if (
        snapshot.pid != process.pid
        or snapshot.creation_time != windows.creation_time
        or snapshot.executable.casefold() != windows.executable.casefold()
    ):
        raise ProbeAbort("process_identity_mismatch")
    visible = [window for window in snapshot.windows if window.visible]
    if allow_headless and not visible:
        return (0, snapshot) if return_snapshot else 0
    mains = [window for window in visible if window.role is WindowRole.MAIN]
    if (
        len(mains) != 1
        or any(window.pid != process.pid for window in visible)
        or any(window.role is not WindowRole.MAIN or window.modal for window in visible)
    ):
        raise ProbeAbort("window_readiness_changed")
    hwnd = mains[0].hwnd
    return (hwnd, snapshot) if return_snapshot else hwnd


def _validate_inspection_receipt(
    receipt: Any,
    *,
    run_id: str,
    process: Any,
    windows: Any,
    hwnd: int,
    capture: dict[str, Any],
    executable_sha256: str,
) -> None:
    expected = {
        "schema": 1,
        "run_id": run_id,
        "approved": True,
        "pid": process.pid,
        "creation_time": windows.creation_time,
        "executable": windows.executable,
        "executable_sha256": executable_sha256,
        "hwnd": hwnd,
        "image_sha256": capture.get("sha256"),
    }
    if not isinstance(receipt, dict) or any(receipt.get(k) != v for k, v in expected.items()):
        raise ProbeAbort("owned_pixels_not_approved_for_current_capture")
    reviewer = receipt.get("reviewer")
    inspected_utc = receipt.get("inspected_utc")
    if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(inspected_utc, str):
        raise ProbeAbort("owned_pixels_inspection_receipt_incomplete")


def run_one_help_probe(
    *,
    run_dir: str | Path,
    process: Any,
    executable_path: str | Path,
    backend: Any,
    inspect_capture: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None] | None = None,
    open_pipes: Callable[[Any], tuple[Any, Any]],
    verify_pipe_owner: Callable[[Any, Any, int], bool],
    send_command: Callable[..., str],
    executable_sha256: str,
    run_id: str,
    journal: _WorkerJournal | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    phase: Callable[[str], Path | None] | None = None,
) -> ProbeResult:
    """Observe, capture/inspect, then issue one strictly bounded Help command.

    ``process`` must already be the exact breakaway child created by the
    supervisor worker. The caller owns its lifetime; this function never kills
    Audacity or dismisses dialogs. No pipe is acquired until current-pixel
    approval and a post-capture readiness/identity check both pass.
    """
    root = Path(run_dir).resolve()
    journal = journal or _WorkerJournal(root)
    phase = phase or (lambda _name: None)
    if process is None or type(getattr(process, "pid", None)) is not int:
        raise ProbeAbort("owned_process_handle_missing")
    if inspect_capture is not None and not callable(inspect_capture):
        raise ProbeAbort("pixel_inspector_unavailable")
    if str(executable_path).casefold() != str(backend.executable).casefold():
        raise ProbeAbort("process_executable_path_mismatch")

    write_pipe = read_pipe = None
    command_count: int | str = 0
    state = "preparing"
    result: ProbeResult | None = None
    success_event = False
    try:
        phase("readiness")
        readiness = wait_for_owned_window_readiness(
            process,
            expected_creation_time=backend.creation_time,
            expected_executable=backend.executable,
            observe=backend.observe,
            capture=backend.capture,
            timeout_sec=READY_TIMEOUT_SEC,
            stable_observations=READY_STABLE_OBSERVATIONS,
            interval_sec=READY_INTERVAL_SEC,
            allow_headless=False,
            monotonic=monotonic,
            sleep=sleep,
        )
        if readiness.state is not ReadinessState.READY:
            raise ProbeAbort(f"readiness_{readiness.state.value}:{readiness.reason}")

        phase("capture")
        hwnd, ready_snapshot = _single_ready_hwnd(
            None, process, backend, allow_headless=False, return_snapshot=True
        )
        if hwnd != 0:
            capture = backend.capture(
                hwnd,
                process.pid,
                backend.creation_time,
                "one_help_preflight",
                CAPTURE_TIMEOUT_SEC,
            )
            if not isinstance(capture, dict) or not isinstance(capture.get("sha256"), str):
                raise ProbeAbort("owned_window_capture_invalid")
            ready_window_snapshot = {
                "pid": ready_snapshot.pid,
                "creation_time": ready_snapshot.creation_time,
                "executable": ready_snapshot.executable,
                "windows": [
                    {
                        "hwnd": window.hwnd,
                        "pid": window.pid,
                        "role": window.role.value,
                        "visible": window.visible,
                        "modal": window.modal,
                    }
                    for window in ready_snapshot.windows
                ],
            }
            ready_snapshot_sha256 = hashlib.sha256(
                json.dumps(ready_window_snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            identity = {
                "run_id": run_id,
                "ready_state": readiness.state.value,
                "ready_observations": readiness.observations,
                "ready_window_snapshot": ready_window_snapshot,
                "ready_snapshot_sha256": ready_snapshot_sha256,
                "capture_dir": str((Path(run_dir) / "capture").resolve()),
                "pid": process.pid,
                "creation_time": backend.creation_time,
                "executable": backend.executable,
                "executable_sha256": executable_sha256,
                "hwnd": hwnd,
                "image_sha256": capture["sha256"],
                "image_path": capture.get("image_path"),
            }
            if inspect_capture is None:
                from .audacity_image_inspection import inspect_owned_capture

                default_inspection = inspect_owned_capture(capture, identity)
                _exclusive_atomic_json(Path(run_dir) / "capture" / "inspection.json", default_inspection)
                inspection: dict[str, Any] | None = default_inspection
            else:
                inspection = inspect_capture(capture, identity)
            _validate_inspection_receipt(
                inspection,
                run_id=run_id,
                process=process,
                windows=backend,
                hwnd=hwnd,
                capture=capture,
                executable_sha256=executable_sha256,
            )
            if process.poll() is not None or _single_ready_hwnd(None, process, backend, allow_headless=False) != hwnd:
                raise ProbeAbort("identity_or_hwnd_changed_after_capture")
        else:
            raise ProbeAbort("owned_visible_window_missing")

        phase("pipes")
        write_pipe, read_pipe = open_pipes(process)
        if write_pipe is None or read_pipe is None:
            raise ProbeAbort("incomplete_pipe_pair")
        if not verify_pipe_owner(write_pipe, read_pipe, process.pid):
            raise ProbeAbort("named_pipe_server_identity_mismatch")
        if process.poll() is not None or _single_ready_hwnd(None, process, backend, allow_headless=False) != hwnd:
            raise ProbeAbort("identity_or_hwnd_changed_before_send")

        phase("handshake")
        journal.write("phase", "handshake", state="before_send", command_count=0)
        state = "before_send"
        journal.write(
            "before_send",
            "handshake",
            command=HELP_COMMAND,
            command_count="unknown",
            hwnd=hwnd,
            pid=process.pid,
            image_sha256=capture["sha256"],
        )
        command_count = "unknown"
        try:
            response = send_command(
                write_pipe,
                read_pipe,
                HELP_COMMAND,
                strict=True,
                timeout_sec=HELP_RESPONSE_TIMEOUT_SEC,
            )
        except BaseException as exc:
            # The write may have reached Audacity even if response handling failed.
            raise ProbeAbort(f"help_outcome_uncertain:{type(exc).__name__}", "unknown") from None
        command_count = 1
        state = "sent"
        response_bytes = str(response).encode("utf-8", errors="replace")
        journal.write(
            "after_send",
            "handshake",
            command=HELP_COMMAND,
            command_count=1,
            response_sha256=hashlib.sha256(response_bytes).hexdigest(),
        )
        result = ProbeResult(True, run_id, 1, "complete", "help_confirmed")
        journal.write("result", "handshake", ok=True, command_count=1, state="complete")
        success_event = True
        phase("persist")
        _seal_worker_result(root, result)
        return result
    except ProbeAbort as exc:
        state = "uncertain" if exc.command_count == "unknown" else "stopped"
        result = ProbeResult(False, run_id, exc.command_count, state, exc.reason)
        try:
            phase("failure_capture")
            _capture_failure_evidence(backend, process, journal)
            phase("persist")
            _seal_worker_result(root, result)
        except FileExistsError:
            pass
        return result
    except Exception as exc:
        command_count = "unknown" if state == "before_send" else command_count
        state = "uncertain" if command_count == "unknown" else "stopped"
        result = ProbeResult(False, run_id, command_count, state, f"worker_error:{type(exc).__name__}")
        try:
            phase("failure_capture")
            _capture_failure_evidence(backend, process, journal)
            phase("persist")
            _seal_worker_result(root, result)
        except FileExistsError:
            pass
        return result
    finally:
        try:
            phase("cleanup")
            if result is not None and not success_event:
                journal.write(
                    "result",
                    "cleanup",
                    ok=False,
                    command_count=result.command_count,
                    reason=result.reason,
                )
        except Exception:
            pass
        for pipe in (write_pipe, read_pipe):
            try:
                if pipe is not None:
                    pipe.close()
            except Exception:
                pass


def _capture_failure_evidence(backend: Any, process: Any, journal: _WorkerJournal) -> None:
    """Best-effort owned-HWND capture; never dismiss or interact with a dialog."""
    try:
        if process.poll() is not None:
            journal.write("phase", "failure_capture", state="process_exited")
            return
        snapshot = backend.observe(process.pid)
        if snapshot.pid != process.pid or snapshot.creation_time != backend.creation_time:
            journal.write("phase", "failure_capture", state="identity_changed")
            return
        windows = [window for window in snapshot.windows if window.visible and window.pid == process.pid]
        if len(windows) != 1:
            journal.write("phase", "failure_capture", state="ambiguous_owned_windows")
            return
        capture = backend.capture(
            windows[0].hwnd,
            process.pid,
            backend.creation_time,
            "one_help_abort",
            CAPTURE_TIMEOUT_SEC,
        )
        journal.write(
            "phase",
            "failure_capture",
            state="captured",
            hwnd=windows[0].hwnd,
            image_sha256=capture.get("sha256") if isinstance(capture, dict) else None,
        )
    except Exception as exc:
        try:
            journal.write("phase", "failure_capture", state=f"capture_error:{type(exc).__name__}")
        except Exception:
            pass


def _seal_worker_result(run_dir: Path, result: ProbeResult) -> Path:
    path = run_dir / "worker_result.json"
    _exclusive_atomic_json(path, asdict(result))
    return path


def validate_live_authorization(
    path: str | Path,
    *,
    run_id: str,
    executable_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate a separate, current one-launch/one-Help operator grant."""
    try:
        source = Path(path)
        raw = source.read_bytes()
        if len(raw) > 16_384 or source.is_symlink():
            raise ValueError
        payload = json.loads(raw.decode("utf-8"))
        expiry = datetime.fromisoformat(str(payload["expires_utc"]).replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        if expiry.tzinfo is None or current.tzinfo is None:
            raise ValueError
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != 1
            or payload.get("run_id") != run_id
            or payload.get("authorize_launch") is not True
            or payload.get("authorize_help") is not True
            or payload.get("max_launches") != 1
            or payload.get("max_pipe_commands") != 1
            or payload.get("executable_sha256") != executable_sha256
            or expiry <= current
        ):
            raise ValueError
        return payload
    except Exception:
        raise ProbeAbort("separate_live_authorization_missing_or_invalid") from None


def _wait_for_inspection_file(
    run_dir: Path,
    *,
    run_id: str,
    process: Any,
    backend: Any,
    hwnd: int,
    capture: dict[str, Any],
    executable_sha256: str,
    deadline_sec: float = CAPTURE_TIMEOUT_SEC,
) -> dict[str, Any] | None:
    """Read a human/approved receipt only when it binds these exact pixels."""
    receipt_path = run_dir / "capture" / "inspection.json"
    deadline = time.monotonic() + deadline_sec
    while time.monotonic() < deadline:
        try:
            if receipt_path.is_file() and not receipt_path.is_symlink():
                raw = receipt_path.read_bytes()
                if len(raw) > 8192:
                    return None
                loaded: dict[str, Any] = json.loads(raw.decode("utf-8"))
                return loaded
        except (OSError, ValueError):
            return None
        time.sleep(0.05)
    return None


def run_worker_request(run_dir: str | Path, request_json: str) -> int:
    """Supervisor child: wait for Job assignment, then run the one-Help probe."""
    root = Path(run_dir).resolve()
    run_id = root.name
    journal = _WorkerJournal(root)
    process = None
    backend = None
    try:
        wait_for_supervisor_ready(root, worker_pid=os.getpid())
        if len(request_json.encode("utf-8")) > 8192:
            raise ProbeAbort("worker_request_too_large")
        request = json.loads(request_json)
        if (
            not isinstance(request, dict)
            or request.get("schema") != 1
            or request.get("run_id") != run_id
            or request.get("authorized_by_parent") is not True
            or request.get("executable") != str(AUDACITY_EXE)
            or request.get("executable_sha256") != AUDACITY_EXE_SHA256
        ):
            raise ProbeAbort("worker_request_invalid")
        journal.write("phase", "identity", state="started", command_count=0)
        if sys.platform != "win32":
            raise ProbeAbort("native_audacity_probe_requires_windows")
        _refuse_existing_audacity()
        digest = hashlib.sha256(AUDACITY_EXE.read_bytes()).hexdigest()
        if digest != AUDACITY_EXE_SHA256:
            raise ProbeAbort("executable_hash_mismatch")
        flags = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
        if not flags:
            raise ProbeAbort("breakaway_job_flag_unavailable")
        capture_dir = root / "capture"
        capture_dir.mkdir(exist_ok=False)
        process = subprocess.Popen([str(AUDACITY_EXE)], creationflags=flags)
        journal.write("phase", "identity", state="launched", pid=process.pid, executable_sha256=digest)
        backend = OwnedAudacityWindows(process, AUDACITY_EXE, capture_dir)
        result = run_one_help_probe(
            run_dir=root,
            process=process,
            executable_path=AUDACITY_EXE,
            backend=backend,
                        open_pipes=_open_pipes_with_phase_deadline,
            verify_pipe_owner=verify_native_pipe_owner,
            send_command=_send_one_help,
            executable_sha256=digest,
            run_id=run_id,
            journal=journal,
            phase=lambda name: journal.write("phase", name, state="started"),
        )
        return 0 if result.ok else 2
    except ProbeAbort as exc:
        _seal_preprobe_failure(root, journal, process, backend, run_id, exc.reason, exc.command_count)
        return 2
    except Exception as exc:
        events = _read_worker_events(root / "journal")
        count: int | str = "unknown" if any(event.get("kind") == "before_send" for event in events) else 0
        _seal_preprobe_failure(root, journal, process, backend, run_id,
                               f"worker_error:{type(exc).__name__}", count)
        return 2


def _refuse_existing_audacity() -> None:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Audacity.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=2.0, check=True,
        )
    except Exception:
        raise ProbeAbort("existing_process_probe_failed") from None
    import csv
    if any(row and row[0].casefold() == "audacity.exe" for row in csv.reader(result.stdout.splitlines())):
        raise ProbeAbort("preexisting_audacity_process")


def _read_worker_events(directory: Path) -> list[dict[str, Any]]:
    events = []
    for path in sorted(directory.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json")):
        try:
            events.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return events


def _seal_preprobe_failure(
    root: Path,
    journal: _WorkerJournal,
    process: Any,
    backend: Any,
    run_id: str,
    reason: str,
    command_count: int | str,
) -> None:
    try:
        journal.write("phase", "failure_capture", state="startup_failure")
        if process is not None and backend is not None:
            _capture_failure_evidence(backend, process, journal)
        journal.write("phase", "persist", state="sealing")
        result = ProbeResult(False, run_id, command_count, "stopped", reason)
        _seal_worker_result(root, result)
        journal.write("phase", "cleanup", state="complete")
        journal.write("result", "cleanup", ok=False, command_count=command_count, reason=reason)
    except FileExistsError:
        pass


def _open_pipes_with_phase_deadline(process: Any) -> tuple[Any, Any]:
    # The external supervisor's 25s phase cap is the hard deadline; the legacy
    # 80s opener cannot finish before the worker is killed by that supervisor.
    from youtube_automation.audio.audacity_client import _open_audacity_pipes

    return _open_audacity_pipes(process)


def _send_one_help(write_pipe: Any, read_pipe: Any, command: str, *, strict: bool, timeout_sec: float) -> str:
    if command != HELP_COMMAND or strict is not True or timeout_sec > HELP_RESPONSE_TIMEOUT_SEC:
        raise ProbeAbort("one_help_contract_violation")
    from youtube_automation.audio.audacity_client import send_audacity_command

    return send_audacity_command(
        write_pipe,
        read_pipe,
        HELP_COMMAND,
        strict=True,
        timeout_sec=HELP_RESPONSE_TIMEOUT_SEC,
    )


def verify_native_pipe_owner(write_pipe: Any, read_pipe: Any, expected_pid: int) -> bool:
    """Require both pipe server handles to belong to the launched Audacity PID."""
    if sys.platform != "win32" or msvcrt is None or type(expected_pid) is not int or expected_pid <= 0:
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        function = kernel32.GetNamedPipeServerProcessId
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
        function.restype = wintypes.BOOL
        for pipe in (write_pipe, read_pipe):
            handle = msvcrt.get_osfhandle(pipe.fileno())
            server_pid = wintypes.ULONG()
            if not function(wintypes.HANDLE(handle), ctypes.byref(server_pid)):
                return False
            if server_pid.value != expected_pid:
                return False
        return True
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Supervisor worker for one Audacity Help command")
    parser.add_argument("--worker", action="store_true", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--request-json", required=True)
    args = parser.parse_args(argv)
    return run_worker_request(args.run_dir, args.request_json)


__all__ = [
    "AUDACITY_EXE",
    "AUDACITY_EXE_SHA256",
    "HELP_COMMAND",
    "ProbeAbort",
    "ProbeResult",
    "run_one_help_probe",
    "validate_live_authorization",
    "wait_for_supervisor_ready",
    "_exclusive_atomic_json",
]
