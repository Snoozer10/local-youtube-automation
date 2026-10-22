"""Fail-closed observations for a process-owned startup window."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class ReadinessState(str, Enum):
    READY = "ready"
    STARTUP = "startup"
    RECOVERY_MODAL = "recovery_modal"
    WELCOME_MODAL = "welcome_modal"
    UNKNOWN_MODAL = "unknown_modal"
    UNOWNED = "unowned"
    PID_EXITED = "pid_exited"
    TIMEOUT = "timeout"
    ERROR = "error"


class WindowRole(str, Enum):
    MAIN = "main"
    RECOVERY = "recovery"
    WELCOME = "welcome"
    MODAL = "modal"
    OTHER = "other"


@dataclass(frozen=True)
class WindowObservation:
    hwnd: int
    pid: int
    role: WindowRole
    visible: bool = True
    modal: bool = False


@dataclass(frozen=True)
class WindowSnapshot:
    pid: int
    creation_time: float
    executable: str
    windows: Sequence[WindowObservation]


@dataclass(frozen=True)
class ReadinessResult:
    state: ReadinessState
    reason: str
    observations: int
    evidence: object | None = None


class ProcessLike(Protocol):
    pid: int

    def poll(self) -> int | None: ...


ObserveWindows = Callable[[int], WindowSnapshot]
CaptureOwnedWindow = Callable[[int, int, float, str, float], object]


def wait_for_owned_window_readiness(
    process: ProcessLike,
    *,
    expected_creation_time: float,
    expected_executable: str,
    observe: ObserveWindows,
    capture: CaptureOwnedWindow,
    timeout_sec: float = 10.0,
    stable_observations: int = 3,
    interval_sec: float = 0.5,
    allow_headless: bool = False,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> ReadinessResult:
    """Wait for stable readiness of one owned process and its sole main window.

    ``capture`` receives only a verified HWND, owned PID and expected process
    creation time. Backends must capture that HWND only and enforce its timeout.
    The observer never dismisses a dialog or changes GUI state.
    """
    if (
        timeout_sec <= 0
        or stable_observations < 1
        or interval_sec < 0
        or not expected_creation_time > 0
        or not expected_executable
    ):
        return ReadinessResult(ReadinessState.ERROR, "invalid_bounds_or_identity", 0)

    deadline = monotonic() + timeout_sec
    max_observations = max(
        stable_observations,
        int(timeout_sec / max(interval_sec, 0.05)) + 1,
    )
    stable = 0
    count = 0
    last_signature: tuple[tuple[int, str, bool], ...] | tuple[str] | None = None
    signature: tuple[tuple[int, str, bool], ...] | tuple[str]

    while count < max_observations:
        if process.poll() is not None:
            return ReadinessResult(ReadinessState.PID_EXITED, "owned_process_exited", count)
        remaining = deadline - monotonic()
        if remaining <= 0:
            return ReadinessResult(ReadinessState.TIMEOUT, "readiness_deadline", count)
        try:
            snapshot = observe(process.pid)
            if monotonic() >= deadline:
                return ReadinessResult(ReadinessState.TIMEOUT, "readiness_observation_deadline", count)
            if (
                snapshot.pid != process.pid
                or snapshot.creation_time != expected_creation_time
                or snapshot.executable.casefold() != expected_executable.casefold()
            ):
                return ReadinessResult(ReadinessState.UNOWNED, "process_identity_mismatch", count)

            visible = [window for window in snapshot.windows if window.visible]
            if any(window.pid != process.pid for window in visible):
                return ReadinessResult(ReadinessState.UNOWNED, "foreign_window_observed", count)

            blocker: WindowObservation | None = None
            if any(window.role is WindowRole.RECOVERY for window in visible):
                blocker = next(window for window in visible if window.role is WindowRole.RECOVERY)
                state, reason = ReadinessState.RECOVERY_MODAL, "recovery_dialog"
            elif any(window.role is WindowRole.WELCOME for window in visible):
                blocker = next(window for window in visible if window.role is WindowRole.WELCOME)
                state, reason = ReadinessState.WELCOME_MODAL, "welcome_dialog"
            elif allow_headless and sum(window.role is WindowRole.MAIN for window in visible) == 0 and visible:
                state, reason = ReadinessState.STARTUP, "transient_startup_windows_observed"
            elif any(window.modal or window.role is WindowRole.MODAL for window in visible):
                blocker = next(window for window in visible if window.modal) if any(window.modal for window in visible) else visible[0]
                state, reason = ReadinessState.UNKNOWN_MODAL, "unknown_modal_dialog"
            elif not visible:
                signature = ("headless",)
                stable = stable + 1 if signature == last_signature else 1
                last_signature = signature
                if allow_headless:
                    if stable >= stable_observations:
                        return ReadinessResult(ReadinessState.READY, "stable_owned_headless_process", count + 1)
                    state, reason = ReadinessState.STARTUP, "headless_stability_pending"
                else:
                    state, reason = ReadinessState.STARTUP, "no_owned_visible_window"
            elif (
                all(w.role is WindowRole.OTHER and not w.modal for w in visible)
            ):
                state, reason = ReadinessState.STARTUP, "transient_splash_observed"
            elif sum(window.role is WindowRole.MAIN for window in visible) != 1:
                blocker = visible[0]
                state, reason = ReadinessState.STARTUP, "main_window_not_unique"
            elif any(window.role is not WindowRole.MAIN for window in visible):
                blocker = next(window for window in visible if window.role is not WindowRole.MAIN)
                state, reason = ReadinessState.UNKNOWN_MODAL, "unknown_owned_window"
            else:
                signature = tuple(sorted((w.hwnd, w.role.value, w.modal) for w in visible))
                stable = stable + 1 if signature == last_signature else 1
                last_signature = signature
                if stable >= stable_observations:
                    return ReadinessResult(ReadinessState.READY, "stable_owned_main_window", count + 1)
                state, reason = ReadinessState.STARTUP, "stability_pending"

            if blocker is not None:
                evidence = capture(
                    blocker.hwnd, process.pid, expected_creation_time, reason,
                    max(0.001, deadline - monotonic()),
                )
                if evidence is None:
                    return ReadinessResult(ReadinessState.ERROR, "capture_returned_no_evidence", count + 1)
                return ReadinessResult(state, reason, count + 1, evidence)

            if reason not in ("stability_pending", "headless_stability_pending"):
                stable = 0
                last_signature = None
            count += 1
            remaining = deadline - monotonic()
            if remaining <= 0:
                return ReadinessResult(ReadinessState.TIMEOUT, reason, count)
            sleep(min(interval_sec, remaining))
        except Exception as exc:
            return ReadinessResult(
                ReadinessState.ERROR,
                f"observation_or_capture_failed:{type(exc).__name__}:{exc}",
                count,
            )
    return ReadinessResult(ReadinessState.TIMEOUT, "readiness_observation_limit", count)
