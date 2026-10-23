"""Deadline supervision for the isolated, one-Help Audacity worker.

Only the worker and its inherited helpers enter the job. The worker must wait
for job_ready before native work; its sole Audacity launch explicitly breaks
away, preserving recoverable UI when the supervisor kills the worker job.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from ctypes import wintypes
from pathlib import Path
from typing import Protocol, TypedDict

PHASE_CAPS = {"identity": 5.0, "readiness": 30.0, "capture": 5.0,
              "pipes": 25.0, "handshake": 35.0, "failure_capture": 5.0,
              "persist": 5.0, "cleanup": 10.0}
_NORMAL_PHASES = ("identity", "readiness", "capture", "pipes", "handshake",
                  "persist", "cleanup")
HELP_COMMAND = "Help: Command=Help"
OUTER_CAP_SECONDS = 120.0
MAX_RECEIPT_BYTES = 16384
REAP_CAP_SECONDS = 0.25
RECEIPT_CAP_SECONDS = 5.0
TIMED_COMPONENT_CAP_SECONDS = OUTER_CAP_SECONDS + RECEIPT_CAP_SECONDS + 2 * REAP_CAP_SECONDS


def _direct_python_executable() -> str:
    """Resolve the interpreter binary behind Windows venv launch redirectors."""
    if os.name == "nt":
        executable = Path(sys.base_prefix) / "python.exe"
        runtime = executable.with_name(
            f"python{sys.version_info.major}{sys.version_info.minor}.dll"
        )
        if not executable.is_absolute() or not executable.is_file() or not runtime.is_file():
            raise RuntimeError("direct_interpreter_unavailable")
        return str(executable)
    executable = Path(sys.executable)
    if not executable.is_absolute() or not executable.is_file():
        raise RuntimeError("direct_interpreter_unavailable")
    return str(executable)


def _worker_environment() -> dict[str, str]:
    """Pass only Windows runtime paths needed by the isolated worker."""
    if os.name != "nt":
        raise RuntimeError("windows_worker_required")
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if not system_root or not Path(system_root).is_absolute():
        raise RuntimeError("windows_system_root_missing")
    system_path = Path(system_root) / "System32"
    if not system_path.is_dir():
        raise RuntimeError("windows_system_path_missing")
    base = Path(sys.base_prefix)
    venv = Path(sys.prefix)
    safe_path = [base, base / "DLLs", venv / "Scripts", system_path, Path(system_root)]
    environment = {
        "SystemRoot": system_root,
        "WINDIR": system_root,
        "PATH": os.pathsep.join(str(path) for path in safe_path if path.is_dir()),
    }
    for key in ("TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE"):
        value = os.environ.get(key)
        if value and Path(value).is_absolute() and Path(value).is_dir():
            environment[key] = value
    return environment


class SupervisedProcess(Protocol):
    @property
    def pid(self) -> int: ...

    def poll(self) -> int | None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


class JobContainment(Protocol):
    def assign(self, process: SupervisedProcess) -> None: ...
    def terminate(self) -> None: ...
    def close(self) -> None: ...


class _JobReady(TypedDict):
    schema: int
    worker_pid: int


class _JournalRecord(TypedDict):
    seq: int
    kind: str
    phase: str
    sha256: str


class _ReceiptRequired(TypedDict):
    schema: int
    outcome: str
    phase: str
    command: str
    command_count: int | str
    command_count_bounds: list[int | str | None]
    outer_cap_seconds: float
    phase_caps_seconds: dict[str, float]
    observed_elapsed_seconds: float
    worker_pid: int | None
    journal: list[_JournalRecord]
    cleanup_errors: list[str]


class SupervisorReceipt(_ReceiptRequired, total=False):
    worker_outcome: str
    measurement_scope: str
    observed_setup_seconds: float
    observed_worker_startup_seconds: float
    observed_worker_cleanup_seconds: float
    worker_watchdog_seconds: float
    worker_reap_cap_seconds: float
    receipt_persistence_cap_seconds: float
    receipt_reap_cap_seconds: float
    timed_component_cap_seconds: float
    persistence_status: str
    deadline_semantics: str
    unbounded_overhead: list[str]
    persistence_errors: list[str]


def _exclusive_json(path: Path, value: _JobReady) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


class WindowsJobContainment:
    """Own a kill-on-close job; failure never falls back to uncontained work."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("windows_job_required")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong),
                        ("job_time", ctypes.c_longlong), ("flags", wintypes.DWORD),
                        ("min_working", ctypes.c_size_t),
                        ("max_working", ctypes.c_size_t),
                        ("active_processes", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t),
                        ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ("read_ops", "write_ops", "other_ops", "read_bytes",
                         "write_bytes", "other_bytes")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                        ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t),
                        ("peak_process_memory", ctypes.c_size_t),
                        ("peak_job_memory", ctypes.c_size_t)]

        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                   ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        self._kernel = kernel
        self._handle = kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise RuntimeError("job_creation_failed")
        limits = ExtendedLimits()
        # BREAKAWAY_OK is explicit: native helpers stay in the job by default.
        limits.basic.flags = 0x2000 | 0x0800
        if not kernel.SetInformationJobObject(self._handle, 9,
                                              ctypes.byref(limits),
                                              ctypes.sizeof(limits)):
            self.close()
            raise RuntimeError("job_configuration_failed")

    def assign(self, process: SupervisedProcess) -> None:
        handle = getattr(process, "_handle", None)
        if handle is None or not self._kernel.AssignProcessToJobObject(
                self._handle, wintypes.HANDLE(int(handle))):
            raise RuntimeError("job_assignment_failed")

    def terminate(self) -> None:
        if self._handle and not self._kernel.TerminateJobObject(self._handle, 1):
            raise RuntimeError("job_termination_failed")

    def close(self) -> None:
        if self._handle:
            handle, self._handle = self._handle, None
            if not self._kernel.CloseHandle(handle):
                raise RuntimeError("job_close_failed")


def _start_worker(command: Sequence[str]) -> subprocess.Popen[bytes]:
    if os.name != "nt":
        raise RuntimeError("windows_worker_required")
    return subprocess.Popen(list(command), stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            cwd=sys.prefix, env=_worker_environment())


def supervise_one_help(
    command: Sequence[str], run_dir: str | Path, *,
    process_factory: Callable[[Sequence[str]], SupervisedProcess] | None = None,
    containment_factory: Callable[[], JobContainment] | None = None,
    persistence_process_factory: Callable[[Path, bytes], SupervisedProcess] | None = None,
    persistence_containment_factory: Callable[[], JobContainment] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> SupervisorReceipt:
    """Run once; seal a parent receipt even after timeout or unsafe events.

    The caller supplies the worker CLI, including its --run-dir argument.
    Journal files are six-digit sequential .json files, published atomically.
    Phase entry is anchored conservatively to the preceding parent poll;
    worker timestamps, heartbeats and repeated phase records cannot extend it.
    A before_send race is counted as unknown (zero or one), never as zero.
    The 120s worker watchdog is followed by <=250ms worker reap, <=5s receipt
    sealer and <=250ms sealer reap: 125.5s nominal timed components. Native
    creation/kernel/scheduling and parent setup/journal I/O are additional
    overhead, not a hard total deadline. Final fsync never runs in the parent.
    """
    if isinstance(command, (str, bytes)) or not command or any(
            not isinstance(arg, str) or not arg for arg in command):
        raise ValueError("worker_command_required")
    supervisor_started = monotonic()
    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=False)
    journal = directory / "journal"
    journal.mkdir()
    started = monotonic()
    previous_poll = started
    if not math.isfinite(started):
        raise ValueError("invalid_clock")
    phase, phase_started = "identity", started
    identity_started_seen = False
    visited = [phase]
    records: list[_JournalRecord] = []
    known_hashes: dict[str, str] = {}
    next_seq = 1
    command_count: int | str = 0
    before_send = after_send = result_seen = False
    gate_released = False
    accounting_unbounded = False
    worker_ok = False
    failure_mode = False
    worker = containment = None
    startup_elapsed = 0.0
    cleanup_started = None
    outcome = "supervisor_error"
    cleanup_errors: list[str] = []

    def read_events() -> None:
        nonlocal phase, phase_started, next_seq, command_count, identity_started_seen
        nonlocal before_send, after_send, result_seen, worker_ok, failure_mode
        names = sorted(journal.iterdir())
        if not set(known_hashes).issubset({path.name for path in names}):
            raise ValueError("journal_removed")
        if len(names) > 64:
            raise ValueError("journal_limit")
        for path in names:
            if path.name.startswith("."):
                continue  # worker's unpublished atomic-write temporary file
            if path.is_symlink() or not re.fullmatch(r"[0-9]{6}\.json", path.name):
                raise ValueError("unsafe_journal_path")
            if path.stat().st_size > 8192:
                raise ValueError("journal_record_limit")
            with path.open("rb") as stream:
                raw = stream.read(8193)
            if len(raw) > 8192:
                raise ValueError("journal_record_limit")
            digest = hashlib.sha256(raw).hexdigest()
            if path.name in known_hashes:
                if known_hashes[path.name] != digest:
                    raise ValueError("journal_changed")
                continue
            event = json.loads(raw)
            if not isinstance(event, dict) or type(event.get("seq")) is not int:
                raise ValueError("invalid_record")
            if event["seq"] != next_seq or path.name != f"{next_seq:06d}.json":
                raise ValueError("journal_sequence")
            kind, entry_phase = event.get("kind"), event.get("phase")
            if entry_phase not in PHASE_CAPS:
                raise ValueError("invalid_phase")
            if kind == "phase":
                if entry_phase != phase:
                    if entry_phase in visited:
                        raise ValueError("phase_reentry")
                    if entry_phase == "failure_capture":
                        if after_send and worker_ok:
                            raise ValueError("invalid_failure_phase")
                        failure_mode = True
                    elif failure_mode:
                        allowed = "persist" if phase == "failure_capture" else "cleanup"
                        if entry_phase != allowed:
                            raise ValueError("invalid_abort_order")
                    elif _NORMAL_PHASES.index(entry_phase) != _NORMAL_PHASES.index(phase) + 1:
                        raise ValueError("phase_order")
                    phase, phase_started = entry_phase, previous_poll
                    visited.append(phase)
                elif (
                    entry_phase == "identity"
                    and event.get("state") == "started"
                    and not identity_started_seen
                ):
                    phase_started = previous_poll
                    identity_started_seen = True
            elif entry_phase != phase:
                raise ValueError("event_phase_mismatch")
            elif kind == "before_send":
                if phase != "handshake" or before_send or result_seen:
                    raise ValueError("duplicate_or_unsafe_send")
                if event.get("command") != HELP_COMMAND:
                    raise ValueError("unexpected_command")
                before_send, command_count = True, "unknown"
            elif kind == "after_send":
                if phase != "handshake" or not before_send or after_send or event.get("command") != HELP_COMMAND:
                    raise ValueError("invalid_send_confirmation")
                if type(event.get("command_count")) is not int or event["command_count"] != 1:
                    raise ValueError("invalid_command_count")
                after_send, command_count = True, 1
            elif kind == "result":
                if result_seen or type(event.get("ok")) is not bool:
                    raise ValueError("invalid_result")
                claimed_count = event.get("command_count")
                if type(claimed_count) is not type(command_count) or claimed_count != command_count:
                    raise ValueError("result_accounting_mismatch")
                worker_ok = event["ok"]
                if worker_ok and (not after_send or phase != "handshake"):
                    raise ValueError("unsafe_success")
                result_seen = True
            else:
                raise ValueError("invalid_event_kind")
            known_hashes[path.name] = digest
            records.append({"seq": next_seq, "kind": kind, "phase": entry_phase,
                            "sha256": digest})
            next_seq += 1

    try:
        containment = (containment_factory or WindowsJobContainment)()
        worker = (process_factory or _start_worker)(command)
        if worker.poll() is not None:
            outcome = "startup_exit"
        else:
            containment.assign(worker)
            # This acknowledgment must precede every worker native action.
            _exclusive_json(directory / "job_ready", {"schema": 1,
                                                     "worker_pid": worker.pid})
            gate_released = True
            startup_elapsed = max(0.0, monotonic() - started)
            while True:
                now = monotonic()
                if not math.isfinite(now) or now < previous_poll:
                    outcome = "invalid_clock"
                    break
                if now - started >= OUTER_CAP_SECONDS:
                    outcome = "outer_timeout"
                    break
                if now - phase_started >= PHASE_CAPS[phase]:
                    outcome = "phase_timeout"
                    break
                try:
                    read_events()
                except (OSError, ValueError, TypeError, KeyError):
                    # Invalid bytes may conceal a durable before_send record.
                    command_count = "unknown"
                    accounting_unbounded = True
                    outcome = "unsafe_journal"
                    break
                exit_code = worker.poll()
                if exit_code is not None:
                    required = set(_NORMAL_PHASES)
                    outcome = ("success" if exit_code == 0 and result_seen and
                               worker_ok and command_count == 1 and
                               required.issubset(visited) and not failure_mode
                               else "worker_failed" if exit_code else "incomplete")
                    break
                previous_poll = now
                sleep(min(0.05, OUTER_CAP_SECONDS - (now - started),
                          PHASE_CAPS[phase] - (now - phase_started)))
    except Exception:
        outcome = "containment_or_startup_error"
    finally:
        cleanup_started = monotonic()
        # Closing the job terminates inherited helpers even on normal exit.
        if containment is not None:
            try:
                containment.terminate()
            except Exception:
                cleanup_errors.append("job_terminate_failed")
            try:
                containment.close()
            except Exception:
                cleanup_errors.append("job_close_failed")
        if worker is not None:
            try:
                if worker.poll() is None:
                    worker.kill()  # exact Popen handle; never a broad PID kill
                worker.wait(timeout=REAP_CAP_SECONDS)
            except Exception:
                cleanup_errors.append("worker_reap_failed")
        if gate_released:
            try:
                read_events()  # retain accounting from records published at deadline
            except (OSError, ValueError, TypeError, KeyError):
                command_count = "unknown"
                accounting_unbounded = True
                if outcome == "success":
                    outcome = "unsafe_journal"
        if cleanup_errors and outcome == "success":
            outcome = "cleanup_failed"
        receipt: SupervisorReceipt = {"schema": 1, "outcome": outcome, "phase": phase,
                   "command": HELP_COMMAND, "command_count": command_count,
                   "command_count_bounds": [0, None] if accounting_unbounded else
                   [0, 1] if command_count == "unknown"
                   else [command_count, command_count],
                   "outer_cap_seconds": OUTER_CAP_SECONDS,
                   "phase_caps_seconds": PHASE_CAPS,
                   "observed_elapsed_seconds": max(0.0, monotonic() - started),
                   "worker_pid": None if worker is None else worker.pid,
                   "journal": records, "cleanup_errors": cleanup_errors}
        receipt.update({
            "worker_outcome": outcome,
            "measurement_scope": "before_parent_receipt_sealing",
            "observed_setup_seconds": max(0.0, started - supervisor_started),
            "observed_worker_startup_seconds": startup_elapsed,
            "observed_worker_cleanup_seconds": max(0.0, monotonic() - cleanup_started),
            "worker_watchdog_seconds": OUTER_CAP_SECONDS,
            "worker_reap_cap_seconds": REAP_CAP_SECONDS,
            "receipt_persistence_cap_seconds": RECEIPT_CAP_SECONDS,
            "receipt_reap_cap_seconds": REAP_CAP_SECONDS,
            "timed_component_cap_seconds": TIMED_COMPONENT_CAP_SECONDS,
            "persistence_status": "sealed",
            # Elapsed above is sampled before sealing. Directory setup, journal
            # I/O, process creation, native calls and scheduling are not a
            # universal hard-real-time bound; the separate budgets are nominal.
            "deadline_semantics": "worker_watchdog_plus_bounded_closeout",
            "unbounded_overhead": ["directory_setup", "journal_io",
                                   "process_creation", "native_kernel_calls",
                                   "scheduling"],
        })
        status, persistence_errors = _seal_parent_receipt(
            directory, receipt,
            process_factory=persistence_process_factory or _start_receipt_sealer,
            containment_factory=persistence_containment_factory or WindowsJobContainment,
            monotonic=monotonic, sleep=sleep)
        if status != "sealed":
            receipt["outcome"] = "receipt_persistence_timeout" if status == "timeout" else "receipt_persistence_failed"
            receipt["persistence_status"] = status
            receipt["persistence_errors"] = persistence_errors
            # Return/stdout is authoritative when disk publication could not
            # complete; no foreground persistence or second attempt is allowed.
    return receipt



def _publish_receipt_payload(directory: Path, payload: bytes) -> None:
    """Validate and publish once in the killable helper, never in its parent."""
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_RECEIPT_BYTES:
        raise ValueError("receipt_payload_limit")
    if not directory.is_absolute() or len(str(directory)) > 4096:
        raise ValueError("unsafe_receipt_directory")
    # Reject symlinks/junctions in the complete existing path.
    if directory.resolve(strict=True) != directory:
        raise ValueError("unsafe_receipt_directory")
    for entry in (directory, *directory.parents):
        info = entry.stat()
        if entry.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("unsafe_receipt_directory")
    if not directory.is_dir():
        raise ValueError("unsafe_receipt_directory")
    value = json.loads(payload, parse_constant=lambda _: (_ for _ in ()).throw(
        ValueError("nonfinite_receipt")))
    if (not isinstance(value, dict) or type(value.get("schema")) is not int or
            value["schema"] != 1 or value.get("command") != HELP_COMMAND):
        raise ValueError("invalid_receipt")
    temporary = directory / ".supervisor_receipt.pending.json"
    final = directory / "supervisor_receipt.json"
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    # Windows rename is atomic and refuses an existing destination. POSIX link
    # gives the same exclusive publication contract without overwrite/replace.
    if os.name == "nt":
        os.rename(temporary, final)
    else:
        os.link(temporary, final)
        temporary.unlink()


def _start_receipt_sealer(directory: Path, payload: bytes) -> subprocess.Popen[bytes]:
    """Start only this stdlib-only file; no stdin, shell, package imports or child launches."""
    if not 0 < len(payload) <= MAX_RECEIPT_BYTES:
        raise ValueError("receipt_payload_limit")
    encoded = base64.b64encode(payload).decode("ascii")
    return _start_worker([_direct_python_executable(), "-I", "-S", "-B",
                          str(Path(__file__).absolute()), "--seal-receipt",
                          str(directory.absolute()), encoded,
                          ".receipt_sealer_job_ready"])


def _seal_parent_receipt(
    directory: Path, receipt: SupervisorReceipt, *,
    process_factory: Callable[[Path, bytes], SupervisedProcess],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    containment_factory: Callable[[], JobContainment] | None = None,
) -> tuple[str, list[str]]:
    """Seal once in an owned Job; bound execution and exact-handle reap."""
    process = containment = None
    errors: list[str] = []
    status = "failed"
    started = previous = None
    try:
        started = previous = monotonic()
        if not math.isfinite(started):
            raise ValueError("invalid_clock")
        payload = (json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        if len(payload) > MAX_RECEIPT_BYTES:
            raise ValueError("receipt_payload_limit")
        containment = (containment_factory or WindowsJobContainment)()
        process = process_factory(directory.absolute(), payload)
        if type(getattr(process, "pid", None)) is not int or process.pid <= 0:
            raise RuntimeError("receipt_sealer_pid_invalid")
        if process.poll() is not None:
            raise RuntimeError("receipt_sealer_startup_exit")
        containment.assign(process)
        _exclusive_json(directory / ".receipt_sealer_job_ready", {
            "schema": 1, "worker_pid": process.pid,
        })
        while True:
            now = monotonic()
            if not math.isfinite(now) or now < previous:
                errors.append("receipt_invalid_clock")
                break
            if now - started >= RECEIPT_CAP_SECONDS:
                status = "timeout"
                errors.append("receipt_persistence_timeout")
                break
            code = process.poll()
            if code is not None:
                status = "sealed" if code == 0 else "failed"
                if code:
                    errors.append("receipt_sealer_failed")
                break
            previous = now
            sleep(min(0.05, RECEIPT_CAP_SECONDS - (now - started)))
    except Exception:
        errors.append("receipt_persistence_failed")
    finally:
        if containment is not None:
            try:
                containment.terminate()
            except Exception:
                errors.append("receipt_sealer_job_terminate_failed")
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=REAP_CAP_SECONDS)
            except Exception:
                errors.append("receipt_sealer_reap_failed")
        if containment is not None:
            try:
                containment.close()
            except Exception:
                errors.append("receipt_sealer_job_close_failed")
    return ("sealed" if status == "sealed" and not errors else
            "timeout" if status == "timeout" else "failed"), errors


def _receipt_sealer_main(arguments: Sequence[str]) -> int:
    """Private bounded-payload entrypoint. Error leaves any partial evidence intact."""
    try:
        if len(arguments) != 4 or arguments[0] != "--seal-receipt":
            return 2
        directory, encoded, ready_name = arguments[1:]
        if (len(directory) > 4096 or len(encoded) > 4 * ((MAX_RECEIPT_BYTES + 2) // 3)
                or ready_name != ".receipt_sealer_job_ready"):
            return 2
        ready_path = Path(directory) / ready_name
        deadline = time.monotonic() + RECEIPT_CAP_SECONDS
        while not ready_path.exists():
            if time.monotonic() >= deadline:
                return 2
            time.sleep(0.01)
        if ready_path.is_symlink() or ready_path.stat().st_size > 4096:
            return 2
        with ready_path.open("rb") as stream:
            ready = json.loads(stream.read(4097))
        if (not isinstance(ready, dict) or type(ready.get("schema")) is not int
                or ready["schema"] != 1 or type(ready.get("worker_pid")) is not int
                or ready["worker_pid"] != os.getpid()):
            return 2
        _publish_receipt_payload(Path(directory), base64.b64decode(encoded, validate=True))
        return 0
    except (OSError, ValueError, TypeError, RecursionError):
        return 1


if __name__ == "__main__":
    raise SystemExit(_receipt_sealer_main(sys.argv[1:]))
