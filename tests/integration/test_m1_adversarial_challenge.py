"""Adversarial stress test harness for Milestone 1 (Chrome lifecycle, loopback & tab hygiene)."""

import asyncio
import concurrent.futures
import json
import time
import urllib.request

import pytest
from playwright.sync_api import sync_playwright

from youtube_automation.browser.cdp_client import (
    clean_context_tabs,
    connect_cdp,
    prepare_browser_context,
)
from youtube_automation.browser.ui_guard import (
    TargetProbeError,
    foreign_debugger_targets,
)
from youtube_automation.core.utils import _listener_pids


@pytest.mark.live_browser
def test_01_live_cdp_targets_and_foreign_targets():
    """Verify live CDP /json/list and check for zero foreign debugger targets."""
    port = 9222
    # 1. Inspect live /json/list
    url = f"http://127.0.0.1:{port}/json/list"
    with urllib.request.urlopen(url, timeout=5) as resp:
        assert resp.status == 200
        targets = json.loads(resp.read().decode("utf-8"))

    assert isinstance(targets, list), f"Expected list of targets, got {type(targets)}"
    assert len(targets) > 0, "Expected at least one active target"

    # 2. Check foreign_debugger_targets
    foreign = foreign_debugger_targets(port)
    assert foreign == [], f"Expected 0 foreign debugger targets, found: {foreign}"

    # 3. Verify registered PID ownership from disk file
    from pathlib import Path

    import psutil
    owned_file = Path(".runtime/owned_browsers.json")
    assert owned_file.exists(), ".runtime/owned_browsers.json does not exist"
    owned = json.loads(owned_file.read_text(encoding="utf-8"))
    assert str(port) in owned, f"Port {port} not in owned_browsers registry"
    reg_pid = owned[str(port)]["pid"]
    assert psutil.pid_exists(reg_pid), f"PID {reg_pid} is not running"
    active_listeners = _listener_pids(port)
    assert reg_pid in active_listeners, f"PID {reg_pid} not among active listeners {active_listeners}"
    print(f"\n[PASS] Live targets count: {len(targets)}, Foreign targets: {len(foreign)}, PID: {reg_pid}")


@pytest.mark.live_browser
def test_02_tab_hygiene_stress():
    """Adversarial stress testing of clean_context_tabs."""
    port = 9222
    with sync_playwright() as p:
        browser = connect_cdp(p, port=port)
        ctx = prepare_browser_context(browser)

        initial_pages_count = len(ctx.pages)
        print(f"\nInitial page count: {initial_pages_count}")

        # Stress Step A: Spawn 10 'about:blank' tabs
        blank_tabs = []
        for _ in range(10):
            page = ctx.new_page()
            blank_tabs.append(page)

        assert len(ctx.pages) == initial_pages_count + 10, "Failed to spawn 10 blank tabs"

        # Stress Step B: Add 2 non-blank pages (data URLs)
        page_non_blank_1 = ctx.new_page()
        page_non_blank_1.goto("data:text/html,<html><body><h1>Safe Tab 1</h1></body></html>")
        page_non_blank_2 = ctx.new_page()
        page_non_blank_2.goto("data:text/html,<html><body><h1>Safe Tab 2</h1></body></html>")

        assert len(ctx.pages) == initial_pages_count + 12

        # Execute tab hygiene
        clean_context_tabs(ctx)

        # Verification: all 10 about:blank tabs must be pruned, 2 safe tabs must remain
        remaining_pages = ctx.pages
        urls = [page.url for page in remaining_pages]
        assert "about:blank" not in urls, f"Found unpruned about:blank tabs: {urls}"
        assert "" not in urls, f"Found unpruned empty tabs: {urls}"
        assert len(remaining_pages) == initial_pages_count + 2, (
            f"Expected {initial_pages_count + 2} tabs, but found {len(remaining_pages)}"
        )

        # Stress Step C: Idempotence & Double Execution
        clean_context_tabs(ctx)
        assert len(ctx.pages) == initial_pages_count + 2

        # Clean up the non-blank test pages we opened
        page_non_blank_1.close()
        page_non_blank_2.close()

        # Final check
        clean_context_tabs(ctx)
        assert len(ctx.pages) == initial_pages_count
        print(f"[PASS] Tab hygiene stress test passed cleanly. Final page count: {len(ctx.pages)}")


@pytest.mark.live_browser
def test_03_concurrent_http_loopback_stress():
    """Stress test loopback HTTP endpoint with high concurrent load."""
    port = 9222
    num_requests = 50
    endpoints = [
        f"http://127.0.0.1:{port}/json/version",
        f"http://127.0.0.1:{port}/json/list",
    ]

    def fetch(url):
        req = urllib.request.Request(url, headers={"User-Agent": "StressTester"})
        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.status
            body = response.read()
        duration = time.perf_counter() - start
        return status, duration, len(body)

    urls = [endpoints[i % 2] for i in range(num_requests)]
    start_all = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch, urls))
    total_time = time.perf_counter() - start_all

    statuses = [r[0] for r in results]
    durations = [r[1] for r in results]
    avg_dur = sum(durations) / len(durations)

    assert all(s == 200 for s in statuses), f"Non-200 responses observed: {set(statuses)}"
    print(f"\n[PASS] HTTP Concurrency: {num_requests} requests in {total_time:.3f}s (avg {avg_dur*1000:.1f}ms). All 200 OK.")


@pytest.mark.live_browser
def test_04_websocket_loopback_concurrent_queries():
    """Verify webSocketDebuggerUrl stability under multiple concurrent async CDP queries."""
    import websockets

    port = 9222
    version_url = f"http://127.0.0.1:{port}/json/version"
    with urllib.request.urlopen(version_url, timeout=5) as resp:
        v_data = json.loads(resp.read().decode())
    ws_url = v_data.get("webSocketDebuggerUrl")
    assert ws_url and ws_url.startswith("ws://127.0.0.1:"), f"Invalid ws url: {ws_url}"

    async def run_cdp_stress():
        async with websockets.connect(ws_url, max_size=10_000_000) as ws:
            # Run 25 parallel queries on single websocket connection
            async def send_query(req_id, method, params=None):
                payload = {"id": req_id, "method": method, "params": params or {}}
                await ws.send(json.dumps(payload))

            # Fire 25 queries
            methods = [
                "Browser.getVersion",
                "Target.getTargets",
                "Browser.getVersion",
                "Target.getTargets",
            ]
            tasks = []
            for i in range(1, 26):
                m = methods[i % len(methods)]
                tasks.append(send_query(i, m))
            await asyncio.gather(*tasks)

            # Receive 25 responses
            received = {}
            for _ in range(25):
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                res = json.loads(msg)
                if "id" in res:
                    received[res["id"]] = res

            assert len(received) == 25, f"Expected 25 responses, got {len(received)}"
            for i in range(1, 26):
                assert i in received, f"Missing response for query id {i}"
                assert "result" in received[i], f"Error in response {i}: {received[i]}"

    asyncio.run(run_cdp_stress())
    print("\n[PASS] WebSocket CDP Concurrent Queries: 25 requests resolved with zero drops/disconnects.")


def test_05_foreign_targets_adversarial_oracle():
    """Adversarially probe foreign_debugger_targets against malicious or edge-case payloads."""
    # Test A: Hostile payload with foreign extension
    fake_list = [
        {"type": "page", "url": "https://google.com"},
        {"type": "page", "url": "chrome-extension://malicious_id/popup.html"},
        {"type": "other", "url": "https://browsermcp.io/dashboard"},
    ]

    class FakeOpener:
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    foreign = foreign_debugger_targets(port=9222, opener=lambda *args, **kwargs: FakeOpener(fake_list))
    assert len(foreign) == 2, f"Expected 2 foreign targets detected, got: {foreign}"
    assert foreign[0]["origin"] == "chrome-extension://malicious_id"
    assert foreign[1]["origin"] == "https://browsermcp.io"

    # Test B: Corrupt payload handling (invalid JSON / non-array)
    class CorruptOpener:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return b"{ not valid json"

    with pytest.raises(TargetProbeError):
        foreign_debugger_targets(port=9222, opener=lambda *args, **kwargs: CorruptOpener())

    print("\n[PASS] Foreign targets oracle verified: Hostile payloads and corrupt responses correctly classified.")


@pytest.mark.live_browser
def test_06_multi_connection_websocket_stress():
    """Verify stability with multiple concurrent WebSocket connections and queries."""
    import websockets

    port = 9222
    version_url = f"http://127.0.0.1:{port}/json/version"
    with urllib.request.urlopen(version_url, timeout=5) as resp:
        v_data = json.loads(resp.read().decode())
    ws_url = v_data.get("webSocketDebuggerUrl")

    async def single_client(client_id):
        async with websockets.connect(ws_url, max_size=10_000_000) as ws:
            for i in range(10):
                req_id = client_id * 100 + i
                payload = {"id": req_id, "method": "Browser.getVersion"}
                await ws.send(json.dumps(payload))
                resp_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                resp = json.loads(resp_raw)
                assert resp.get("id") == req_id
                assert "result" in resp

    async def run_all():
        tasks = [single_client(c) for c in range(10)]
        await asyncio.gather(*tasks)

    asyncio.run(run_all())
    print("\n[PASS] Multi-Connection WebSocket: 10 connections x 10 commands (100 total) succeeded without failure.")


@pytest.mark.live_browser
def test_07_tab_churn_during_target_probing():
    """Verify target list & foreign target probing stability during concurrent tab creation/closing."""
    port = 9222
    with sync_playwright() as p:
        browser = connect_cdp(p, port=port)
        ctx = prepare_browser_context(browser)

        # Churn: open and close tabs while polling /json/list
        for _ in range(5):
            new_tabs = [ctx.new_page() for _ in range(3)]
            # Probe while tabs are open
            targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5).read().decode())
            assert isinstance(targets, list)
            foreign = foreign_debugger_targets(port)
            assert foreign == []

            # Close tabs and clean
            for t in new_tabs:
                t.close()
            clean_context_tabs(ctx)

    print("\n[PASS] Target probing during tab churn passed: 0 malformed responses, 0 foreign targets.")


def test_08_tab_hygiene_edge_cases():
    """Verify clean_context_tabs handles edge cases: already closed pages, mock exception throwing."""
    from unittest.mock import MagicMock

    # Mock context where closing a page raises an exception
    mock_ctx = MagicMock()
    mock_page_1 = MagicMock()
    mock_page_1.url = "about:blank"
    mock_page_1.close.side_effect = RuntimeError("Page already detached")

    mock_page_2 = MagicMock()
    mock_page_2.url = ""
    mock_page_2.close.return_value = None

    mock_page_3 = MagicMock()
    mock_page_3.url = "https://google.com"

    mock_ctx.pages = [mock_page_1, mock_page_2, mock_page_3]

    # Should not raise any error despite mock_page_1 raising an exception
    clean_context_tabs(mock_ctx)
    mock_page_1.close.assert_called_once()
    mock_page_2.close.assert_called_once()
    mock_page_3.close.assert_not_called()
    print("\n[PASS] Tab hygiene edge cases: gracefully handles detached/closed pages and ignores real pages.")

