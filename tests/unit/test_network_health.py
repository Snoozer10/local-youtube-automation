"""Offline checks for the VPN/proxy network health gate used before adaptive provider work."""

import itertools
import urllib.error
from types import SimpleNamespace

import pytest

from youtube_automation.audio import tts_generator
from youtube_automation.browser import network_health
from youtube_automation.production import cli


class _Response:
    def __init__(self, status, body=b""):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def getcode(self):
        return self.status

    def read(self, size):
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


def _opener(connectivity_status=204, target_body=b"x" * 40_000, target_error=None):
    def open_(request, timeout):
        assert timeout > 0
        if request.full_url == network_health.CONNECTIVITY_URL:
            return _Response(connectivity_status)
        if target_error is not None:
            raise target_error
        return _Response(200, target_body)

    return open_


def _probe(healthy, detail="probe"):
    return network_health.NetworkProbe(healthy, 0.2, 0.5, 40_000, detail)


def test_gate_is_off_under_pytest_unless_forced(monkeypatch):
    monkeypatch.delenv("NETWORK_HEALTH_GATE", raising=False)
    assert network_health.gate_enabled() is False
    result = network_health.require_healthy(
        network_health.GEMINI_URL, probe_fn=lambda _url: pytest.fail("no probe when gate is off")
    )
    assert result is None
    monkeypatch.setenv("NETWORK_HEALTH_GATE", "1")
    assert network_health.gate_enabled() is True
    monkeypatch.setenv("NETWORK_HEALTH_GATE", "off")
    assert network_health.gate_enabled() is False


def test_probe_classifies_healthy_slow_failed_and_small_complete_pages():
    healthy = network_health.probe(network_health.GEMINI_URL, opener=_opener())
    assert healthy.healthy and healthy.target_bytes == network_health.TARGET_MIN_BYTES

    wrong_status = network_health.probe(network_health.GEMINI_URL, opener=_opener(200))
    assert not wrong_status.healthy and "status 200" in wrong_status.detail

    def raising(_request, timeout):
        raise urllib.error.URLError("proxy timed out")

    failed = network_health.probe(network_health.GEMINI_URL, opener=raising)
    assert not failed.healthy and "connectivity check failed" in failed.detail

    blocked = network_health.probe(
        network_health.GEMINI_URL,
        opener=_opener(target_error=urllib.error.URLError("reset")),
    )
    assert not blocked.healthy and "target fetch failed" in blocked.detail

    small = network_health.probe(network_health.GEMINI_URL, opener=_opener(target_body=b"x" * 5_000))
    assert small.healthy and small.target_bytes == 5_000


def test_probe_rejects_a_slow_connectivity_check(monkeypatch):
    ticks = itertools.chain([0.0], itertools.repeat(2.0))
    monkeypatch.setattr(network_health.time, "monotonic", lambda: next(ticks))
    slow = network_health.probe(network_health.GEMINI_URL, opener=_opener())
    assert not slow.healthy and "limit 1.5 s" in slow.detail


def test_waits_through_degradation_then_requires_two_healthy_probes(monkeypatch):
    monkeypatch.setenv("NETWORK_HEALTH_GATE", "1")
    results = iter([_probe(False, "slow"), _probe(True), _probe(False, "flap"), _probe(True), _probe(True)])
    sleeps, logs, now = [], [], [0.0]

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    result = network_health.require_healthy(
        network_health.AI_STUDIO_URL,
        max_wait_seconds=600,
        probe_fn=lambda _url: next(results),
        hint_fn=lambda: pytest.fail("no hint on success"),
        sleep=sleep,
        clock=lambda: now[0],
        log=logs.append,
    )
    assert result is not None and result.healthy
    assert sleeps == [15.0, 5.0, 30.0, 5.0]
    assert any("Degraded (slow)" in line for line in logs)
    assert any("Healthy again" in line for line in logs)


def test_gives_up_before_any_send_with_a_route_hint(monkeypatch):
    monkeypatch.setenv("NETWORK_HEALTH_GATE", "1")
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    with pytest.raises(network_health.NetworkDegradedError, match="Nothing was sent") as caught:
        network_health.require_healthy(
            network_health.GEMINI_URL,
            max_wait_seconds=40,
            probe_fn=lambda _url: _probe(False, "connectivity 4.10 s"),
            hint_fn=lambda: "direct route healthy (0.20 s)",
            sleep=sleep,
            clock=lambda: now[0],
            log=lambda _line: None,
        )
    assert "direct route healthy" in str(caught.value)
    assert not isinstance(caught.value, RuntimeError)
    assert now[0] == 15.0


def test_adaptive_tts_connect_waits_for_the_network_before_cdp(monkeypatch):
    calls = []
    monkeypatch.setattr(network_health, "require_healthy", lambda url: calls.append(("gate", url)))
    monkeypatch.setattr(tts_generator.ui_guard, "foreign_debugger_targets", lambda *_a, **_k: [])

    def connect(endpoint, **kwargs):
        calls.append(("connect", kwargs.get("timeout")))
        return SimpleNamespace()

    playwright = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect))
    tts_generator.connect_tts_browser(
        playwright, adaptive=True, browser_type="chrome", profile_index="1", port=9222
    )
    assert calls == [("gate", network_health.AI_STUDIO_URL), ("connect", 30000)]


@pytest.mark.parametrize("complete", [False, True])
def test_cli_gates_incomplete_provider_stages_before_any_browser_work(tmp_path, monkeypatch, complete):
    calls = []
    monkeypatch.setattr(network_health, "require_healthy", lambda url: calls.append(url))
    monkeypatch.setattr(cli, "_stage_complete", lambda _root, _args: complete)
    monkeypatch.setattr(cli, "_run_stage_attempt", lambda *_a: calls.append("stage"))
    cli.main(["analyze", "--run-dir", str(tmp_path), "--channel-profile", "channels/x.json"])
    assert calls == (["stage"] if complete else [network_health.GEMINI_URL, "stage"])
