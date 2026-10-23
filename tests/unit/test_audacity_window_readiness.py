from dataclasses import dataclass

import pytest

from youtube_automation.core.window_readiness import (
    ReadinessState,
    WindowObservation,
    WindowRole,
    WindowSnapshot,
    wait_for_owned_window_readiness,
)


@dataclass
class FakeProcess:
    pid: int = 123
    exit_code: int | None = None

    def poll(self):
        return self.exit_code


def snapshot(*windows, pid=123, created=42.0, executable="audacity.exe"):
    return WindowSnapshot(pid, created, executable, windows)


def run(observations, *, process=None, capture=None, **kwargs):
    process = process or FakeProcess()
    calls = iter(observations)
    captured = []

    def observe(pid):
        return next(calls)

    def capture_window(hwnd, pid, at, reason, timeout):
        captured.append((hwnd, pid, at, reason, timeout))
        if capture:
            return capture(hwnd, pid, at, reason, timeout)
        return {"hwnd": hwnd, "pid": pid, "at": at, "reason": reason}

    result = wait_for_owned_window_readiness(
        process,
        expected_creation_time=42.0,
        expected_executable="Audacity.exe",
        observe=observe,
        capture=capture_window,
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        **kwargs,
    )
    return result, captured


def test_ready_requires_three_stable_owned_main_window_observations():
    main = WindowObservation(77, 123, WindowRole.MAIN)
    result, captures = run([snapshot(main), snapshot(main), snapshot(main)])

    assert result.state is ReadinessState.READY
    assert result.observations == 3
    assert captures == []


def test_startup_then_three_stable_main_observations_becomes_ready():
    main = WindowObservation(77, 123, WindowRole.MAIN)
    result, captures = run([snapshot(), snapshot(main), snapshot(main), snapshot(main)])
    assert result.state is ReadinessState.READY
    assert result.observations == 4
    assert captures == []


def test_transient_splash_then_three_stable_main_observations_becomes_ready():
    splash = WindowObservation(88, 123, WindowRole.OTHER)
    main = WindowObservation(77, 123, WindowRole.MAIN)
    result, captures = run([snapshot(splash), snapshot(splash), snapshot(main), snapshot(main), snapshot(main)])
    assert result.state is ReadinessState.READY
    assert result.observations == 5
    assert captures == []



def test_changed_hwnd_restarts_stability_count():
    first = WindowObservation(77, 123, WindowRole.MAIN)
    changed = WindowObservation(88, 123, WindowRole.MAIN)
    result, _ = run([snapshot(first), snapshot(changed), snapshot(changed), snapshot(changed)])
    assert result.state is ReadinessState.READY
    assert result.observations == 4


def test_unrecognized_owned_visible_window_blocks_ready():
    main = WindowObservation(77, 123, WindowRole.MAIN)
    other = WindowObservation(88, 123, WindowRole.OTHER)
    result, captures = run([snapshot(main, other)])
    assert result.state is ReadinessState.UNKNOWN_MODAL
    assert captures[0][0:3] == (88, 123, 42.0)


@pytest.mark.parametrize(
    "role,expected",
    [(WindowRole.RECOVERY, ReadinessState.RECOVERY_MODAL), (WindowRole.WELCOME, ReadinessState.WELCOME_MODAL)],
)
def test_modal_blocks_and_captures_only_its_owned_hwnd(role, expected):
    main = WindowObservation(77, 123, WindowRole.MAIN)
    dialog = WindowObservation(88, 123, role, modal=True)
    result, captures = run([snapshot(main, dialog)])

    assert result.state is expected
    assert captures[0][:3] == (88, 123, 42.0)
    assert captures[0][3] in {"recovery_dialog", "welcome_dialog"}


def test_pid_exit_and_identity_mismatch_fail_closed_without_capture():
    exited = FakeProcess(exit_code=0)
    result, captures = run([snapshot()], process=exited)
    assert result.state is ReadinessState.PID_EXITED
    assert captures == []

    result, captures = run([snapshot(pid=999)])
    assert result.state is ReadinessState.UNOWNED
    assert captures == []


def test_capture_failure_is_error_and_never_ready():
    main = WindowObservation(77, 123, WindowRole.MAIN)
    dialog = WindowObservation(88, 123, WindowRole.RECOVERY, modal=True)

    def fail_capture(*_args):
        raise OSError("capture unavailable")

    result, _ = run([snapshot(main, dialog)], capture=fail_capture)
    assert result.state is ReadinessState.ERROR
    assert result.reason.startswith("observation_or_capture_failed")


def test_headless_transient_startup_windows_then_stable_headless_becomes_ready():
    helper = WindowObservation(88, 123, WindowRole.MODAL, visible=True, modal=False)
    result, captures = run(
        [snapshot(helper), snapshot(helper), snapshot(), snapshot(), snapshot()],
        allow_headless=True,
    )
    assert result.state is ReadinessState.READY
    assert result.reason == "stable_owned_headless_process"
    assert result.observations == 5
    assert captures == []
