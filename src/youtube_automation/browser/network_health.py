"""Bounded network health gate for provider work behind an unstable VPN/proxy.

The operator's connection can run through a local proxy (Psiphon) whose quality changes minute to
minute. A provider send made on a degraded path can spend a capped request and still fail (AI Studio
"http status code: 0", 2026-10-09). Before adaptive provider navigation or a send, callers wait here
until the same proxied path is healthy for two consecutive probes, or stop with NetworkDegradedError
before anything is spent. This module never changes proxy settings and never restarts the browser
or the VPN.
"""

from __future__ import annotations

import os
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

GEMINI_URL = "https://gemini.google.com/app"
AI_STUDIO_URL = "https://aistudio.google.com/"
CONNECTIVITY_URL = "https://www.google.com/generate_204"
HEALTHY_CONNECTIVITY_SECONDS = 1.5
TARGET_SECONDS = 8.0
TARGET_MIN_BYTES = 32 * 1024
BACKOFF_SECONDS = (15.0, 30.0, 60.0, 120.0)
CONFIRM_PAUSE_SECONDS = 5.0
DEFAULT_MAX_WAIT_SECONDS = 900.0


class NetworkDegradedError(Exception):
    """The proxied network stayed unhealthy past the wait limit; nothing was sent.

    Deliberately not a RuntimeError: request_json treats RuntimeError as a retryable transport
    failure, and a degraded network must stop the stage instead of spending retries.
    """


@dataclass(frozen=True)
class NetworkProbe:
    healthy: bool
    connectivity_seconds: float | None
    target_seconds: float | None
    target_bytes: int
    detail: str


def gate_enabled() -> bool:
    """On by default; NETWORK_HEALTH_GATE=0/off/false disables it. Off under pytest unless forced."""
    value = os.getenv("NETWORK_HEALTH_GATE")
    if value is not None:
        return value.strip().lower() not in {"0", "off", "false", "no"}
    # Unit tests drive provider code with fakes and must never touch the network.
    return "PYTEST_CURRENT_TEST" not in os.environ


def _timed_get(
    opener: Callable[..., Any], url: str, *, timeout: float, max_bytes: int
) -> tuple[int, float, int, bool]:
    """Return (status, seconds, bytes read, body complete) for one bounded GET."""
    start = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    received = 0
    complete = False
    with opener(request, timeout=timeout) as response:
        status = int(getattr(response, "status", 0) or response.getcode())
        while received < max_bytes and time.monotonic() - start <= timeout:
            chunk = response.read(min(16384, max_bytes - received))
            if not chunk:
                complete = True
                break
            received += len(chunk)
    return status, time.monotonic() - start, received, complete


def probe(
    target_url: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout: float = 10.0,
) -> NetworkProbe:
    """Probe the same (system-proxied) path the browser uses: a 204 check, then the target site."""
    try:
        status, seconds, _, _ = _timed_get(opener, CONNECTIVITY_URL, timeout=timeout, max_bytes=1024)
    except Exception as exc:
        return NetworkProbe(
            False, None, None, 0, f"connectivity check failed: {type(exc).__name__}: {str(exc)[:160]}"
        )
    if status != 204 or seconds > HEALTHY_CONNECTIVITY_SECONDS:
        return NetworkProbe(
            False,
            round(seconds, 3),
            None,
            0,
            f"connectivity check status {status} in {seconds:.2f} s "
            f"(limit {HEALTHY_CONNECTIVITY_SECONDS:g} s)",
        )
    try:
        t_status, t_seconds, received, complete = _timed_get(
            opener, target_url, timeout=TARGET_SECONDS, max_bytes=TARGET_MIN_BYTES
        )
    except Exception as exc:
        return NetworkProbe(
            False,
            round(seconds, 3),
            None,
            0,
            f"target fetch failed: {type(exc).__name__}: {str(exc)[:160]}",
        )
    healthy = (
        200 <= t_status < 400
        and t_seconds <= TARGET_SECONDS
        and (received >= TARGET_MIN_BYTES or complete)
    )
    detail = (
        f"connectivity {seconds:.2f} s; target status {t_status}, {received} B in {t_seconds:.2f} s"
    )
    return NetworkProbe(healthy, round(seconds, 3), round(t_seconds, 3), received, detail)


def direct_route_hint(*, opener: Callable[..., Any] | None = None) -> str:
    """Diagnostic only: is the direct (no-proxy) route healthy? Never changes any setting."""
    direct = opener or urllib.request.build_opener(urllib.request.ProxyHandler({})).open
    try:
        status, seconds, _, _ = _timed_get(direct, CONNECTIVITY_URL, timeout=5.0, max_bytes=1024)
    except Exception as exc:
        return f"direct route also failing ({type(exc).__name__})"
    if status == 204 and seconds <= HEALTHY_CONNECTIVITY_SECONDS:
        return f"direct route healthy ({seconds:.2f} s): the VPN/proxy path is the bottleneck"
    return f"direct route slow too (status {status}, {seconds:.2f} s)"


def require_healthy(
    target_url: str,
    *,
    max_wait_seconds: float | None = None,
    probe_fn: Callable[[str], NetworkProbe] = probe,
    hint_fn: Callable[[], str] = direct_route_hint,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = print,
) -> NetworkProbe | None:
    """Wait until two consecutive probes pass; raise NetworkDegradedError after the wait limit."""
    if not gate_enabled():
        return None
    if max_wait_seconds is not None:
        limit = float(max_wait_seconds)
    else:
        try:
            limit = float(os.getenv("NETWORK_MAX_WAIT_SECONDS", str(DEFAULT_MAX_WAIT_SECONDS)))
        except ValueError:
            limit = DEFAULT_MAX_WAIT_SECONDS
    started = clock()
    waits = 0
    while True:
        last = probe_fn(target_url)
        if last.healthy:
            sleep(CONFIRM_PAUSE_SECONDS)
            last = probe_fn(target_url)
            if last.healthy:
                if waits:
                    log(f"[NETWORK] Healthy again after {clock() - started:.0f} s ({last.detail}).")
                return last
        waited = clock() - started
        delay = BACKOFF_SECONDS[min(waits, len(BACKOFF_SECONDS) - 1)]
        if waited + delay > limit:
            raise NetworkDegradedError(
                f"Network stayed degraded for {waited:.0f} s (limit {limit:.0f} s): {last.detail}; "
                f"{hint_fn()}. Nothing was sent; check the VPN/proxy and rerun."
            )
        log(
            f"[NETWORK] Degraded ({last.detail}); waiting {delay:.0f} s before re-checking "
            f"({waited:.0f}/{limit:.0f} s)."
        )
        sleep(delay)
        waits += 1


__all__ = [
    "AI_STUDIO_URL",
    "GEMINI_URL",
    "NetworkDegradedError",
    "NetworkProbe",
    "direct_route_hint",
    "gate_enabled",
    "probe",
    "require_healthy",
]
