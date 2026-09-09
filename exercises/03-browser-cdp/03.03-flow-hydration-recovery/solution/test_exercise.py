"""Test suite for Exercise 03.03 — Flow SPA Hydration Recovery.

Uses local HTML fixtures with setTimeout(...) to simulate SPA hydration delays,
transient CDK dialog backdrops, and quota/rate-limit error cards — all
deterministically, without requiring a live Google Flow connection.

Covers all 5 production-grade helper functions:
  - wait_for_flow_input_box
  - inject_prompt_safely
  - dismiss_blocking_flow_modals
  - check_for_quota_error
  - card_spawn_handshake
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Generator

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from exercise import (
    card_spawn_handshake,
    check_for_quota_error,
    dismiss_blocking_flow_modals,
    inject_prompt_safely,
    wait_for_flow_input_box,
)

# ---------------------------------------------------------------------------
# Local HTML fixtures
# ---------------------------------------------------------------------------

HYDRATION_DELAY_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Flow Hydration Fixture</title></head>
<body>
<div id="root">
  <p id="loading">Loading SPA...</p>
</div>
<script>
  // Simulate React SPA hydration: contenteditable appears after 4 seconds
  setTimeout(function() {
    var editor = document.createElement('div');
    editor.setAttribute('contenteditable', 'true');
    editor.setAttribute('data-placeholder', 'What do you want to create?');
    editor.style.width = '600px';
    editor.style.height = '60px';
    editor.style.border = '1px solid #ccc';
    editor.style.padding = '8px';
    editor.style.display = 'block';
    document.getElementById('root').appendChild(editor);
    document.getElementById('loading').remove();
  }, 4000);
</script>
</body>
</html>
"""

MODAL_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Modal Fixture</title></head>
<body>
<div role="dialog" id="modal" style="display:block; background:#fff; border:1px solid #000; padding:20px;">
  <p>Terms of Service Updated</p>
  <button aria-label="close">Close</button>
</div>
<div id="main-content" contenteditable="true" style="width:600px;height:60px;display:block;border:1px solid #ccc;"></div>
</body>
</html>
"""

NO_MODAL_HTML = """\
<!DOCTYPE html>
<html>
<head><title>No Modal Fixture</title></head>
<body>
<div id="main-content" contenteditable="true" style="width:600px;height:60px;display:block;border:1px solid #ccc;"></div>
</body>
</html>
"""

QUOTA_ERROR_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Quota Error Fixture</title></head>
<body>
<div id="workspace">
  <div class="generation-card" role="article">
    <p class="error-text">Failed</p>
    <p>You've reached your usage limit. Please try again later.</p>
    <p>You have not been charged for this generation.</p>
  </div>
</div>
</body>
</html>
"""

NO_ERROR_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Clean Workspace Fixture</title></head>
<body>
<div id="workspace">
  <div class="generation-card" role="article">
    <img src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==" width="600" height="338" />
  </div>
</div>
<div id="main-content" contenteditable="true" style="width:600px;height:60px;display:block;border:1px solid #ccc;"></div>
</body>
</html>
"""

CARD_SPAWN_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Card Spawn Fixture</title></head>
<body>
<div id="workspace">
  <div class="generation-card" role="article" id="card-1">
    <p>Previous generation</p>
  </div>
</div>
<script>
  // Simulate a new generation card appearing after 3 seconds
  setTimeout(function() {
    var card = document.createElement('div');
    card.className = 'generation-card';
    card.setAttribute('role', 'article');
    card.id = 'card-2';
    card.innerHTML = '<div role="progressbar" aria-label="generating">Generating...</div>';
    document.getElementById('workspace').appendChild(card);
  }, 3000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Minimal HTTP server fixture
# ---------------------------------------------------------------------------

class _FixtureHandler(BaseHTTPRequestHandler):
    """Serves static HTML fixtures for Playwright navigation."""
    _routes: dict[str, str] = {}

    def do_GET(self):
        path = self.path.lstrip("/")
        body = self._routes.get(path, "<html><body>404</body></html>")
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):  # suppress server logs
        pass


@pytest.fixture(scope="module")
def fixture_server() -> Generator[str, None, None]:
    """Starts a local HTTP server serving HTML fixtures."""
    _FixtureHandler._routes = {
        "hydration": HYDRATION_DELAY_HTML,
        "modal": MODAL_HTML,
        "no-modal": NO_MODAL_HTML,
        "quota-error": QUOTA_ERROR_HTML,
        "no-error": NO_ERROR_HTML,
        "card-spawn": CARD_SPAWN_HTML,
    }
    server = HTTPServer(("127.0.0.1", 0), _FixtureHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------------------------------------------------------------------------
# Playwright page fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pw_page(fixture_server):
    """Creates a Playwright browser page for the test module."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


# ---------------------------------------------------------------------------
# Tests — wait_for_flow_input_box
# ---------------------------------------------------------------------------

@pytest.mark.drill
def test_wait_for_flow_input_box_finds_after_hydration(fixture_server, pw_page):
    """wait_for_flow_input_box must succeed after the 4-second SPA hydration delay."""
    pw_page.goto(f"{fixture_server}/hydration")
    # With 15s timeout, the poller must find the editor that appears after 4s
    result = wait_for_flow_input_box(pw_page, timeout_seconds=15.0)
    assert result is not None, "Expected input box to be found after hydration delay"
    assert result.is_visible(), "Expected found input box to be visible"


@pytest.mark.drill
def test_wait_for_flow_input_box_times_out_gracefully(fixture_server, pw_page):
    """wait_for_flow_input_box must return None (not raise) on timeout."""
    pw_page.goto(f"{fixture_server}/no-modal")
    pw_page.evaluate("document.querySelector('[contenteditable]').remove()")
    result = wait_for_flow_input_box(pw_page, timeout_seconds=1.0)
    # Should return None without raising
    assert result is None or not result.is_visible()


# ---------------------------------------------------------------------------
# Tests — dismiss_blocking_flow_modals
# ---------------------------------------------------------------------------

@pytest.mark.drill
def test_dismiss_blocking_flow_modals_closes_dialog(fixture_server, pw_page):
    """dismiss_blocking_flow_modals must click the close button when a dialog is present."""
    pw_page.goto(f"{fixture_server}/modal")
    assert pw_page.locator("[role='dialog']").is_visible()
    dismissed = dismiss_blocking_flow_modals(pw_page)
    assert dismissed is True, "Expected modal to be detected and dismissed"


@pytest.mark.drill
def test_dismiss_blocking_flow_modals_noop_without_dialog(fixture_server, pw_page):
    """dismiss_blocking_flow_modals must not press Escape when no dialog is present."""
    pw_page.goto(f"{fixture_server}/no-modal")
    dismissed = dismiss_blocking_flow_modals(pw_page)
    assert dismissed is False, "Expected no modal to be detected or dismissed"


# ---------------------------------------------------------------------------
# Tests — inject_prompt_safely
# ---------------------------------------------------------------------------

@pytest.mark.drill
def test_inject_prompt_safely_sets_content(fixture_server, pw_page):
    """inject_prompt_safely must set content in a contenteditable div."""
    pw_page.goto(f"{fixture_server}/no-modal")
    editor = pw_page.locator("[contenteditable='true']").first
    assert editor.is_visible()
    inject_prompt_safely(pw_page, editor, "A scenic mountain landscape at golden hour")
    content = editor.evaluate("el => el.innerText || el.textContent || ''")
    assert "mountain" in content.lower(), f"Expected prompt text in editor, got: {content!r}"


# ---------------------------------------------------------------------------
# Tests — check_for_quota_error
# ---------------------------------------------------------------------------

@pytest.mark.drill
def test_check_for_quota_error_detects_usage_limit(fixture_server, pw_page):
    """check_for_quota_error must return the error text when a quota card is visible.

    This test validates the fix that prevented 120s stall timeouts when Google
    Flow displayed 'You've reached your usage limit' in the generation card.
    """
    pw_page.goto(f"{fixture_server}/quota-error")
    result = check_for_quota_error(pw_page)
    assert result is not None, (
        "Expected quota error text to be detected. "
        "Without this fix, the watchdog would stall for 120s before timing out."
    )
    assert any(
        phrase in result.lower()
        for phrase in ("usage limit", "not been charged", "reached your")
    ), f"Expected quota phrase in detected text, got: {result!r}"


@pytest.mark.drill
def test_check_for_quota_error_returns_none_on_clean_page(fixture_server, pw_page):
    """check_for_quota_error must return None when no error is present."""
    pw_page.goto(f"{fixture_server}/no-error")
    result = check_for_quota_error(pw_page)
    assert result is None, f"Expected no quota error on clean page, got: {result!r}"


# ---------------------------------------------------------------------------
# Tests — card_spawn_handshake
# ---------------------------------------------------------------------------

@pytest.mark.drill
def test_card_spawn_handshake_detects_new_card(fixture_server, pw_page):
    """card_spawn_handshake must return True when a new card appears within timeout.

    The fixture starts with 1 card and adds a second card with a progressbar
    after 3 seconds, simulating Google Flow's queue latency after submission.
    """
    pw_page.goto(f"{fixture_server}/card-spawn")
    # Record the pre-submit card count (1 existing card)
    pre_count = pw_page.locator(
        "div[data-card-index], .generation-card, [role='article']"
    ).count()
    assert pre_count == 1, f"Expected 1 pre-existing card, got {pre_count}"

    # Handshake: wait up to 10s for a new card (fixture spawns one at 3s)
    result = card_spawn_handshake(pw_page, pre_card_count=pre_count, timeout_seconds=10.0)
    assert result is True, (
        "Expected card_spawn_handshake to return True after new card appeared. "
        "Without this handshake, the generator may falsely re-trigger Enter."
    )


@pytest.mark.drill
def test_card_spawn_handshake_times_out_gracefully(fixture_server, pw_page):
    """card_spawn_handshake must return False (not raise) when no new card appears."""
    pw_page.goto(f"{fixture_server}/no-error")
    pre_count = pw_page.locator(
        "div[data-card-index], .generation-card, [role='article']"
    ).count()
    # With 2s timeout and no new cards spawning, should return False cleanly
    result = card_spawn_handshake(pw_page, pre_card_count=pre_count, timeout_seconds=2.0)
    assert result is False, "Expected False when no new card appeared within timeout"
