"""Offline supervision tests: no Popen or native APIs are executed."""
import json
from pathlib import Path

import pytest

from youtube_automation.core.process_supervisor import HELP_COMMAND, supervise_one_help
from youtube_automation.core.process_supervisor import _start_receipt_sealer as RECEIPT_FACTORY


class FakeProcess:
    pid = 321

    def __init__(self):
        self.exit_code = None
        self.killed = False
        self.waited = False

    def poll(self):
        return self.exit_code

    def kill(self):
        self.killed = True
        self.exit_code = 1

    def wait(self, timeout):
        assert timeout <= 0.25
        self.waited = True
        return self.exit_code


class FakeJob:
    def __init__(self, fail_assign=False):
        self.assigned = None
        self.terminated = self.closed = False
        self.fail_assign = fail_assign

    def assign(self, process):
        if self.fail_assign:
            raise RuntimeError("failed")
        self.assigned = process

    def terminate(self):
        self.terminated = True

    def close(self):
        self.closed = True


class Clock:
    def __init__(self, process, run_dir, events=(), exit_at=None):
        self.now = 0.0
        self.process, self.run_dir = process, run_dir
        self.events = list(events)
        self.exit_at = exit_at
        self.seq = 0

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.now += duration
        assert self.run_dir.joinpath("job_ready").exists()
        while self.events and self.events[0][0] <= self.now:
            _, event = self.events.pop(0)
            self.seq += 1
            event = {"seq": self.seq, **event}
            path = self.run_dir / "journal" / f"{self.seq:06d}.json"
            path.write_text(json.dumps(event), encoding="utf-8")
        if self.exit_at is not None and self.now >= self.exit_at:
            self.process.exit_code = 0


def phase(name):
    return {"kind": "phase", "phase": name}


def run(tmp_path, events=(), *, exit_at=None, fail_assign=False, sealer_job=None):
    directory = tmp_path / "attempt"
    process, job = FakeProcess(), FakeJob(fail_assign)
    persistence_job = sealer_job or FakeJob()
    clock = Clock(process, directory, events, exit_at)
    result = supervise_one_help(["fake-worker", "--run-dir", str(directory)], directory,
                               process_factory=lambda command: process,
                               containment_factory=lambda: job,
                               persistence_containment_factory=lambda: persistence_job,
                               monotonic=clock.monotonic, sleep=clock.sleep)
    return result, process, job, directory, clock


def ready_events():
    return [(0.05, phase("identity")), (0.1, phase("readiness")),
            (0.15, phase("capture")), (0.2, phase("pipes")),
            (0.25, phase("handshake")),
            (0.3, {"kind": "before_send", "phase": "handshake", "command": HELP_COMMAND}),
            (0.35, {"kind": "after_send", "phase": "handshake", "command": HELP_COMMAND,
                    "command_count": 1}),
            (0.4, {"kind": "result", "phase": "handshake", "ok": True, "command_count": 1}),
            (0.45, phase("persist")), (0.5, phase("cleanup"))]


def test_delayed_first_identity_started_event_resets_work_clock(tmp_path):
    events = [(4.75, {**phase("identity"), "state": "started"})]
    result, _, _, _, clock = run(tmp_path, events)
    assert result["outcome"] == "phase_timeout"
    assert result["phase"] == "identity"
    assert 9.5 < clock.now < 10.0


def test_timeout_hard_kills_owned_worker_and_job_and_seals(tmp_path):
    result, worker, job, directory, clock = run(tmp_path)
    assert result["outcome"] == "phase_timeout"
    assert result["phase"] == "identity"
    assert clock.now <= 5.05
    assert worker.killed and worker.waited and job.terminated and job.closed
    assert job.assigned is worker
    assert json.loads((directory / "supervisor_receipt.json").read_text()) == result


def test_pipe_acquisition_cap_is_25_seconds(tmp_path):
    events = ready_events()[:4]
    result, worker, job, _, clock = run(tmp_path, events)
    assert result["outcome"] == "phase_timeout" and result["phase"] == "pipes"
    assert clock.now <= 25.2
    assert worker.killed and job.closed
    assert result["command_count"] == 0


def test_repeated_identity_started_event_cannot_extend_deadline(tmp_path):
    started = {**phase("identity"), "state": "started"}
    events = [(0.05, started), (4.9, dict(started))]
    result, _, _, _, clock = run(tmp_path, events)
    assert result["outcome"] == "phase_timeout"
    assert result["phase"] == "identity"
    assert clock.now <= 5.05


def test_job_assignment_failure_never_releases_startup_gate(tmp_path):
    result, worker, job, directory, _ = run(tmp_path, fail_assign=True)
    assert result["outcome"] == "containment_or_startup_error"
    assert not (directory / "job_ready").exists()
    assert worker.killed and job.closed
    assert result["command_count"] == 0


def test_ready_exact_one_command_receipt_and_cleanup(tmp_path):
    result, worker, job, directory, _ = run(tmp_path, ready_events(), exit_at=0.6)
    assert result["outcome"] == "success"
    assert result["command_count"] == 1 and result["command_count_bounds"] == [1, 1]
    assert not worker.killed and worker.waited and job.closed
    receipt = directory / "supervisor_receipt.json"
    with pytest.raises(FileExistsError):
        receipt.open("x")
    assert len(result["journal"]) == 10


def test_before_send_timeout_keeps_uncertain_accounting(tmp_path):
    result, worker, _, _, _ = run(tmp_path, ready_events()[:6])
    assert result["outcome"] == "phase_timeout" and worker.killed
    assert result["command_count"] == "unknown"
    assert result["command_count_bounds"] == [0, 1]


@pytest.mark.parametrize("state", ["welcome", "recovery", "unknown_modal", "identity_mismatch"])
def test_abort_result_has_zero_commands(tmp_path, state):
    events = [(0.05, phase("identity")), (0.1, phase("readiness")),
              (0.15, {"kind": "result", "phase": "readiness", "ok": False,
                      "command_count": 0, "reason": state}),
              (0.2, phase("failure_capture")), (0.25, phase("persist")),
              (0.3, phase("cleanup"))]
    result, _, _, _, _ = run(tmp_path, events, exit_at=0.4)
    assert result["outcome"] != "success"
    assert result["command_count"] == 0
    assert all(item["kind"] not in {"before_send", "after_send"} for item in result["journal"])


def test_reentering_pipe_phase_fails_closed(tmp_path):
    events = ready_events()[:5] + [(0.3, phase("pipes"))]
    result, worker, _, _, _ = run(tmp_path, events)
    assert result["outcome"] == "unsafe_journal" and worker.killed


def test_containment_failure_launches_no_worker_and_seals(tmp_path):
    directory = tmp_path / "attempt"
    calls = []

    def unavailable():
        raise RuntimeError("unavailable")

    result = supervise_one_help(["fake"], directory,
                               process_factory=lambda cmd: calls.append(cmd),
                               containment_factory=unavailable,
                               persistence_containment_factory=FakeJob)
    assert not calls
    assert result["outcome"] == "containment_or_startup_error"
    assert result["worker_pid"] is None and result["command_count"] == 0
    assert (directory / "supervisor_receipt.json").exists()


def test_outer_deadline_terminates_even_if_clock_jumps(tmp_path):
    directory = tmp_path / "attempt"
    worker, job = FakeProcess(), FakeJob()
    clock = Clock(worker, directory)

    def jump(seconds):
        clock.now = 120.0

    result = supervise_one_help(["fake"], directory,
                               process_factory=lambda cmd: worker,
                               containment_factory=lambda: job,
                               persistence_containment_factory=FakeJob,
                               monotonic=clock.monotonic, sleep=jump)
    assert result["outcome"] == "outer_timeout"
    assert worker.killed and job.terminated and job.closed


def test_deadline_race_reconciles_durable_before_send(tmp_path):
    directory = tmp_path / "attempt"
    worker, job = FakeProcess(), FakeJob()
    events = ready_events()[:5]
    clock = Clock(worker, directory, events)
    original_sleep = clock.sleep

    def race(seconds):
        if clock.now >= 0.3:
            clock.seq += 1
            event = {"seq": clock.seq, "kind": "before_send", "phase": "handshake",
                     "command": HELP_COMMAND}
            path = directory / "journal" / f"{clock.seq:06d}.json"
            path.write_text(json.dumps(event))
            clock.now = 120.0
        else:
            original_sleep(seconds)

    result = supervise_one_help(["fake"], directory,
                               process_factory=lambda cmd: worker,
                               containment_factory=lambda: job,
                               persistence_containment_factory=FakeJob,
                               monotonic=clock.monotonic, sleep=race)
    assert result["outcome"] == "outer_timeout"
    assert result["command_count"] == "unknown"
    assert result["command_count_bounds"] == [0, 1]


class FakeNativeFunction:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


class FakeKernel:
    def __init__(self, *, assign_ok=True, configure_ok=True):
        self.calls = []
        self.flags = None
        self.CreateJobObjectW = FakeNativeFunction(lambda security, name: 44)
        self.SetInformationJobObject = FakeNativeFunction(self.configure)
        self.AssignProcessToJobObject = FakeNativeFunction(
            lambda job, process: self.record("assign", job, process) and assign_ok)
        self.TerminateJobObject = FakeNativeFunction(
            lambda job, code: self.record("terminate", job, code))
        self.CloseHandle = FakeNativeFunction(lambda job: self.record("close", job))
        self.configure_ok = configure_ok

    def record(self, name, *args):
        self.calls.append((name, args))
        return True

    def configure(self, handle, info_class, pointer, size):
        import ctypes
        self.flags = ctypes.c_uint32.from_address(ctypes.addressof(pointer._obj) + 16).value
        self.calls.append(("configure", (handle, info_class, size)))
        return self.configure_ok


def native_job(monkeypatch, kernel):
    from types import SimpleNamespace

    from youtube_automation.core import process_supervisor as module
    monkeypatch.setattr(module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(module.ctypes, "WinDLL", lambda *a, **k: kernel, raising=False)
    return module.WindowsJobContainment()


def test_native_job_abi_and_exact_popen_handle(monkeypatch):
    from types import SimpleNamespace
    kernel = FakeKernel()
    job = native_job(monkeypatch, kernel)
    job.assign(SimpleNamespace(_handle=123456))
    job.terminate()
    job.close()
    assert kernel.flags == 0x2800
    assert kernel.CreateJobObjectW.restype is not None
    assert kernel.SetInformationJobObject.argtypes[3].__name__ == "c_ulong"
    assign = next(args for name, args in kernel.calls if name == "assign")
    assert assign[0] == 44 and assign[1].value == 123456
    assert [name for name, _ in kernel.calls] == ["configure", "assign", "terminate", "close"]
    job.close()
    assert len(kernel.calls) == 4


def test_native_assignment_failure_does_not_ack(monkeypatch):
    from types import SimpleNamespace
    kernel = FakeKernel(assign_ok=False)
    job = native_job(monkeypatch, kernel)
    with pytest.raises(RuntimeError, match="job_assignment_failed"):
        job.assign(SimpleNamespace(_handle=123))
    job.terminate()
    job.close()
    assert [name for name, _ in kernel.calls][-2:] == ["terminate", "close"]


def test_native_configuration_failure_closes_job(monkeypatch):
    kernel = FakeKernel(configure_ok=False)
    with pytest.raises(RuntimeError, match="job_configuration_failed"):
        native_job(monkeypatch, kernel)
    assert [name for name, _ in kernel.calls] == ["configure", "close"]


@pytest.fixture(autouse=True)
def prohibit_real_receipt_processes(monkeypatch):
    """Every default sealer is a fixture; no test can fall through to Popen."""
    from youtube_automation.core import process_supervisor as module
    monkeypatch.setattr(module.os, "fsync", lambda descriptor: None)

    def fake_sealer(directory, payload):
        process = FakeProcess()

        def poll():
            if not (directory / ".receipt_sealer_job_ready").exists():
                return None
            if process.exit_code is None:
                module._publish_receipt_payload(directory, payload)
                process.exit_code = 0
            return process.exit_code

        process.poll = poll
        return process

    monkeypatch.setattr(module, "_start_receipt_sealer", fake_sealer)


def test_parent_persistence_deadline_kills_exact_sealer_after_worker_cleanup(tmp_path):
    from youtube_automation.core import process_supervisor as module
    directory = tmp_path / "attempt"
    worker, job, sealer = FakeProcess(), FakeJob(), FakeProcess()
    clock = Clock(worker, directory, ready_events(), exit_at=0.6)
    requests = []

    def persist(path, payload):
        assert job.closed and worker.waited
        requests.append((path, payload))
        return sealer

    result = module.supervise_one_help(
        ["fake-worker"], directory, process_factory=lambda command: worker,
        containment_factory=lambda: job, persistence_process_factory=persist,
        persistence_containment_factory=FakeJob,
        monotonic=clock.monotonic, sleep=clock.sleep)
    assert sealer.killed and sealer.waited
    assert len(requests) == 1
    assert result["outcome"] == "receipt_persistence_timeout"
    assert result["worker_outcome"] == "success"
    assert result["persistence_status"] == "timeout"
    assert result["persistence_errors"] == ["receipt_persistence_timeout"]
    assert 5.6 <= clock.now <= 5.65
    assert not (directory / "supervisor_receipt.json").exists()


def test_receipt_sealer_is_assigned_to_its_job_before_ack(tmp_path):
    directory = tmp_path / "attempt"

    class AckOrderJob(FakeJob):
        def assign(self, process):
            assert not (directory / ".receipt_sealer_job_ready").exists()
            super().assign(process)

    sealer_job = AckOrderJob()
    result, worker, job, actual_directory, _ = run(
        tmp_path, ready_events(), exit_at=0.6, sealer_job=sealer_job)

    assert actual_directory == directory
    assert result["outcome"] == "success"
    assert job.closed and worker.waited
    assert sealer_job.assigned is not None
    assert sealer_job.terminated and sealer_job.closed
    assert (directory / ".receipt_sealer_job_ready").exists()
    assert (directory / "supervisor_receipt.json").exists()


def test_receipt_sealer_job_assignment_failure_withholds_ack_and_reaps(tmp_path):
    from youtube_automation.core import process_supervisor as module

    directory = tmp_path / "attempt"
    directory.mkdir()
    sealer, job = FakeProcess(), FakeJob(fail_assign=True)
    status, errors = module._seal_parent_receipt(
        directory, {"schema": 1, "command": HELP_COMMAND},
        process_factory=lambda path, payload: sealer,
        containment_factory=lambda: job,
        monotonic=lambda: 0.0,
        sleep=lambda _: None)

    assert status == "failed"
    assert errors == ["receipt_persistence_failed"]
    assert sealer.killed and sealer.waited
    assert job.terminated and job.closed
    assert not (directory / ".receipt_sealer_job_ready").exists()


def test_parent_persistence_process_failure_returns_failure_without_retry(tmp_path):
    from youtube_automation.core import process_supervisor as module
    directory = tmp_path / "attempt"
    worker, job = FakeProcess(), FakeJob()
    clock = Clock(worker, directory, ready_events(), exit_at=0.6)
    calls = []

    def fail(path, payload):
        assert job.closed and worker.waited
        calls.append(path)
        raise OSError("disk denied")

    result = module.supervise_one_help(
        ["fake-worker"], directory, process_factory=lambda command: worker,
        containment_factory=lambda: job, persistence_process_factory=fail,
        persistence_containment_factory=FakeJob,
        monotonic=clock.monotonic, sleep=clock.sleep)
    assert len(calls) == 1 and result["outcome"] == "receipt_persistence_failed"
    assert result["worker_outcome"] == "success"
    assert result["persistence_errors"] == ["receipt_persistence_failed"]


def test_parent_persistence_nonzero_exit_and_reap_failure_are_fail_closed(tmp_path):
    from youtube_automation.core import process_supervisor as module
    directory = tmp_path / "attempt"
    worker, job, sealer = FakeProcess(), FakeJob(), FakeProcess()
    clock = Clock(worker, directory, ready_events(), exit_at=0.6)
    sealer.exit_code = 1
    sealer.poll = lambda: (1 if (directory / ".receipt_sealer_job_ready").exists()
                           else None)

    def failed_reap(timeout):
        assert timeout == module.REAP_CAP_SECONDS
        raise TimeoutError("owned process not reaped")

    sealer.wait = failed_reap
    result = module.supervise_one_help(
        ["fake-worker"], directory, process_factory=lambda command: worker,
        containment_factory=lambda: job,
        persistence_process_factory=lambda path, payload: sealer,
        persistence_containment_factory=FakeJob,
        monotonic=clock.monotonic, sleep=clock.sleep)
    assert result["outcome"] == "receipt_persistence_failed"
    assert result["persistence_errors"] == ["receipt_sealer_failed", "receipt_sealer_reap_failed"]
    assert not (directory / "supervisor_receipt.json").exists()


def test_nominal_closeout_contract_and_successful_receipt_match(tmp_path):
    result, worker, job, directory, _ = run(tmp_path, ready_events(), exit_at=0.6)
    assert job.closed and worker.waited
    assert result["worker_watchdog_seconds"] == 120.0
    assert result["phase_caps_seconds"]["pipes"] == 25.0
    assert result["receipt_persistence_cap_seconds"] == 5.0
    assert result["worker_reap_cap_seconds"] == result["receipt_reap_cap_seconds"] == 0.25
    assert result["timed_component_cap_seconds"] == 125.5
    assert result["deadline_semantics"] == "worker_watchdog_plus_bounded_closeout"
    assert result["persistence_status"] == "sealed"
    assert "native_kernel_calls" in result["unbounded_overhead"]
    assert json.loads((directory / "supervisor_receipt.json").read_bytes()) == result


def test_receipt_sealer_is_stdlib_file_with_finite_argv_no_shell(monkeypatch, tmp_path):
    import base64

    from youtube_automation.core import process_supervisor as module
    captured = []
    monkeypatch.setattr(module, "_start_worker", lambda args: captured.append(args))
    payload = json.dumps({"schema": 1, "command": HELP_COMMAND}).encode()
    # The autouse fence is deliberately bypassed only to a mocked start function.
    real_start = RECEIPT_FACTORY
    real_start(tmp_path, payload)
    assert len(captured) == 1
    args = captured[0]
    assert args[0] == module._direct_python_executable()
    assert args[1:4] == ["-I", "-S", "-B"]
    assert Path(args[4]).name == "process_supervisor.py"
    assert args[5] == "--seal-receipt"
    assert base64.b64decode(args[7], validate=True) == payload
    assert args[8] == ".receipt_sealer_job_ready"
    with pytest.raises(ValueError, match="receipt_payload_limit"):
        real_start(tmp_path, b"x" * (module.MAX_RECEIPT_BYTES + 1))
    assert len(captured) == 1


def test_sealer_entrypoint_exclusive_publication_and_existing_bytes_preserved(tmp_path):
    import base64

    from youtube_automation.core import process_supervisor as module
    payload = json.dumps({"schema": 1, "command": HELP_COMMAND, "outcome": "success"}).encode()
    (tmp_path / ".receipt_sealer_job_ready").write_text(
        json.dumps({"schema": 1, "worker_pid": module.os.getpid()}), encoding="utf-8")
    args = ["--seal-receipt", str(tmp_path), base64.b64encode(payload).decode(),
            ".receipt_sealer_job_ready"]
    assert module._receipt_sealer_main(args) == 0
    final = tmp_path / "supervisor_receipt.json"
    assert final.read_bytes() == payload
    assert module._receipt_sealer_main(args) == 1
    assert final.read_bytes() == payload


@pytest.mark.parametrize("args", [
    [], ["--other", "x", "eA=="],
    ["--seal-receipt", "relative", "eA=="],
    ["--seal-receipt", "x" * 4097, "eA=="],
    ["--seal-receipt", "x", "!" * 100],
])
def test_sealer_entrypoint_invalid_arguments_fail_before_publication(tmp_path, args):
    from youtube_automation.core import process_supervisor as module
    assert module._receipt_sealer_main(args) != 0
    assert not (tmp_path / "supervisor_receipt.json").exists()


def test_sealer_fsync_failure_leaves_no_success_receipt(monkeypatch, tmp_path):
    import base64

    from youtube_automation.core import process_supervisor as module

    def fail(descriptor):
        raise OSError("disk failure")

    monkeypatch.setattr(module.os, "fsync", fail)
    payload = json.dumps({"schema": 1, "command": HELP_COMMAND}).encode()
    (tmp_path / ".receipt_sealer_job_ready").write_text(
        json.dumps({"schema": 1, "worker_pid": module.os.getpid()}), encoding="utf-8")
    args = ["--seal-receipt", str(tmp_path), base64.b64encode(payload).decode(),
            ".receipt_sealer_job_ready"]
    assert module._receipt_sealer_main(args) == 1
    assert not (tmp_path / "supervisor_receipt.json").exists()
    assert (tmp_path / ".supervisor_receipt.pending.json").exists()


def test_parent_never_uses_foreground_final_json_writer(monkeypatch, tmp_path):
    from youtube_automation.core import process_supervisor as module
    original = module._exclusive_json
    foreground_writes = []

    def write(path, value):
        foreground_writes.append(path.name)
        return original(path, value)

    monkeypatch.setattr(module, "_exclusive_json", write)
    result, _, _, _, _ = run(tmp_path, ready_events(), exit_at=0.6)
    assert result["outcome"] == "success"
    assert foreground_writes == ["job_ready", ".receipt_sealer_job_ready"]


def test_native_sealer_start_uses_only_exact_popen_with_hidden_window(monkeypatch):
    from types import SimpleNamespace

    from youtube_automation.core import process_supervisor as module
    calls = []
    sentinel = object()

    def fake_popen(command, **options):
        calls.append((command, options))
        return sentinel

    monkeypatch.setattr(module, "os", SimpleNamespace(name="nt"))
    environment = {"SystemRoot": "C:/Windows", "PATH": "controlled"}
    monkeypatch.setattr(module, "_worker_environment", lambda: environment)
    monkeypatch.setattr(module.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    assert module._start_worker(["python.exe", "-I", "-B", "process_supervisor.py"]) is sentinel
    assert len(calls) == 1
    _, options = calls[0]
    assert options["creationflags"] == 0x08000000
    assert options["stdin"] is options["stdout"] is options["stderr"] is module.subprocess.DEVNULL
    assert options["cwd"] == module.sys.prefix
    assert options["env"] == environment
    assert "shell" not in options


def test_receipt_sealer_rejects_boolean_schema_and_nonfinite_json(tmp_path):
    import base64

    from youtube_automation.core import process_supervisor as module
    (tmp_path / ".receipt_sealer_job_ready").write_text(
        json.dumps({"schema": 1, "worker_pid": module.os.getpid()}), encoding="utf-8")
    for payload in [
        b'{"schema":true,"command":"Help: Command=Help"}',
        b'{"schema":1,"command":"Help: Command=Help","value":NaN}',
    ]:
        args = ["--seal-receipt", str(tmp_path), base64.b64encode(payload).decode(),
                ".receipt_sealer_job_ready"]
        assert module._receipt_sealer_main(args) == 1
    assert not (tmp_path / "supervisor_receipt.json").exists()

@pytest.mark.parametrize("pid", [True, 0, -1])
def test_sealer_ack_rejects_nonmatching_identity_before_publication(tmp_path, pid):
    import base64

    from youtube_automation.core import process_supervisor as module
    module._exclusive_json(tmp_path / ".receipt_sealer_job_ready",
                           {"schema": 1, "worker_pid": pid})
    payload = b'{"schema":1,"command":"Help: Command=Help"}'
    args = ["--seal-receipt", str(tmp_path), base64.b64encode(payload).decode(),
            ".receipt_sealer_job_ready"]
    assert module._receipt_sealer_main(args) == 2
    assert not (tmp_path / "supervisor_receipt.json").exists()


def test_worker_command_uses_direct_isolated_interpreter_and_validated_venv(monkeypatch, tmp_path):
    from tools import audacity_help_once as cli
    environment = tmp_path / "venv"
    site = environment / "Lib" / "site-packages"
    site.mkdir(parents=True)
    (environment / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
    monkeypatch.setattr(cli.sys, "prefix", str(environment))
    monkeypatch.setattr(cli, "_direct_python_executable", lambda: "direct-python.exe")
    command = cli._worker_command(tmp_path / "run", "{}")
    assert command[:5] == ["direct-python.exe", "-I", "-S", "-B", "-c"]
    assert command[5] == cli._WORKER_BOOTSTRAP
    assert command[6] == str(site)
    assert Path(command[7]).resolve() == Path(cli.__file__).resolve()
    assert command[8:] == ["--worker", "--run-dir", str(tmp_path / "run"),
                          "--request-json", "{}"]
    (environment / "pyvenv.cfg").write_text("include-system-site-packages = true\n")
    with pytest.raises(cli.ProbeAbort, match="worker_environment_invalid"):
        cli._worker_command(tmp_path / "run", "{}")
