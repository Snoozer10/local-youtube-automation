"""Chrome DevTools Protocol (CDP) Client & Browser Context Lifecycle Manager.

Handles CDP connection lifecycle over port 9222 (or configured port), browser
launching with targeted profiles, tab hygiene (pruning orphaned/blank tabs),
browser context management, and graceful failover teardown with profile rotation.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import time
import urllib.request
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright

try:
    from utils import (
        get_config_value,
        kill_cdp_chrome,
        launch_browser_with_profile,
        rotate_profile_index,
    )
except ImportError:
    from youtube_automation.core.utils import (
        get_config_value,
        kill_cdp_chrome,
        launch_browser_with_profile,
        rotate_profile_index,
    )

logger = logging.getLogger("BrowserCDP")

DEFAULT_CDP_PORT = 9222
DEFAULT_CDP_HOST = "127.0.0.1"


def is_port_in_use(port: int | str = DEFAULT_CDP_PORT, host: str = DEFAULT_CDP_HOST) -> bool:
    """Checks if a local TCP port is actively occupied."""
    port_num = int(port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port_num)) == 0


def verify_cdp_port(
    port: int | str = DEFAULT_CDP_PORT,
    host: str = DEFAULT_CDP_HOST,
    timeout_seconds: float = 2.0,
) -> bool:
    """Verifies that the Chrome DevTools Protocol endpoint is responding over HTTP."""
    port_num = int(port)
    url = f"http://{host}:{port_num}/json/version"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CDPClient"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            return response.status == 200
    except Exception:
        return False


def connect_cdp(
    playwright: Playwright,
    port: int | str = DEFAULT_CDP_PORT,
    host: str = DEFAULT_CDP_HOST,
) -> Browser:
    """Connects to a running browser instance over CDP."""
    port_num = int(port)
    cdp_endpoint = f"http://{host}:{port_num}"
    return playwright.chromium.connect_over_cdp(cdp_endpoint)


def ensure_cdp_browser(
    playwright: Playwright,
    port: int | str | None = None,
    profile_index: str | None = None,
    browser_type: str | None = None,
) -> Browser:
    """Connects to Chrome/Opera via CDP, launching the browser process if not already running."""
    cdp_port = int(port or get_config_value("CDP_PORT", str(DEFAULT_CDP_PORT)))
    current_profile_idx = str(profile_index or get_config_value("ACTIVE_PROFILE_INDEX", "1"))
    b_type = str(browser_type or get_config_value("BROWSER_TYPE", "chrome"))

    try:
        return connect_cdp(playwright, port=cdp_port)
    except Exception:
        if not launch_browser_with_profile(b_type, current_profile_idx, port=cdp_port):
            logger.critical(f"[CDP] Failed to launch browser '{b_type}' with profile {current_profile_idx}.")
            sys.exit(1)
        return connect_cdp(playwright, port=cdp_port)


def prepare_browser_context(
    browser: Browser,
    permissions: list[str] | None = None,
) -> BrowserContext:
    """Obtains the primary browser context and configures required system permissions."""
    if browser.contexts:
        context = browser.contexts[0]
    else:
        context = browser.new_context()

    granted = permissions if permissions is not None else ["clipboard-read", "clipboard-write"]
    if granted:
        try:
            context.grant_permissions(granted)
        except Exception as e:
            logger.warning(f"[CDP] Could not grant context permissions {granted}: {e}")

    return context


def clean_context_tabs(context: BrowserContext) -> None:
    """Prunes orphaned, blank, or transient pages to keep context clean."""
    for existing_p in list(context.pages):
        try:
            if existing_p.url in ("about:blank", ""):
                existing_p.close()
        except Exception:
            pass


def get_or_create_page(
    context: BrowserContext,
    url_pattern: str,
    fallback_url: str | None = None,
    timeout_ms: int = 60000,
) -> Page:
    """Finds an existing tab matching url_pattern or creates a new one, optionally navigating to fallback_url."""
    for page in context.pages:
        try:
            if url_pattern in page.url:
                return page
        except Exception:
            continue

    new_p = context.new_page()
    if fallback_url:
        try:
            new_p.goto(fallback_url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception as e:
            logger.warning(f"[CDP] Initial navigation warning for {fallback_url}: {e}")
    return new_p


def safe_failover_teardown(browser: Any = None, context: Any = None, port: int | str = DEFAULT_CDP_PORT) -> None:
    """Gracefully detaches Playwright CDP handles BEFORE killing the browser PID.

    Prevents TargetClosedError / orphaned port bindings on 9222 during failover.
    """
    print("  \U0001f50c Detaching CDP handles gracefully...")
    try:
        if context:
            context.close()
    except Exception as e:
        print(f"  \u26a0\ufe0f CDP context close failed (non-fatal): {e}")

    try:
        if browser:
            browser.close()
    except Exception as e:
        print(f"  \u26a0\ufe0f CDP browser close failed (non-fatal): {e}")

    time.sleep(1.0)
    # Now safe to kill process at OS level
    rotate_profile_index()
    kill_cdp_chrome(port)
    time.sleep(2.0)


def capture_debug_state(page: Any, step_name: str, subfolder: str | None = None) -> None:
    """Takes a debug screenshot and logs the current URL/title when a step stalls."""
    try:
        debug_dir = os.path.join(subfolder or ".", "debug_snapshots")
        os.makedirs(debug_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(debug_dir, f"{step_name}_{ts}.png")

        page.screenshot(path=screenshot_path)
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}]   \U0001f4f8 [DEBUG SNAPSHOT] Saved visual state to: {screenshot_path}", flush=True)
        print(f"[{timestamp}]   \U0001f310 [DEBUG URL]: {page.url}", flush=True)
        try:
            print(f"[{timestamp}]   \U0001f3f7\ufe0f [DEBUG TITLE]: {page.title()}", flush=True)
        except Exception:
            pass
    except Exception as e:
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}]   \u26a0\ufe0f Could not take debug snapshot: {e}", flush=True)


class CDPClient:
    """High-level object-oriented CDP browser manager."""

    def __init__(
        self,
        port: int | str = DEFAULT_CDP_PORT,
        host: str = DEFAULT_CDP_HOST,
        profile_index: str = "1",
        browser_type: str = "chrome",
    ) -> None:
        self.port = int(port)
        self.host = host
        self.profile_index = profile_index
        self.browser_type = browser_type
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None

    def connect(self, playwright: Playwright) -> tuple[Browser, BrowserContext]:
        """Ensures browser process is alive, connects over CDP, and initializes clean context."""
        self.browser = ensure_cdp_browser(
            playwright,
            port=self.port,
            profile_index=self.profile_index,
            browser_type=self.browser_type,
        )
        self.context = prepare_browser_context(self.browser)
        clean_context_tabs(self.context)
        return self.browser, self.context

    def teardown(self) -> None:
        """Detaches handles and performs safe failover."""
        safe_failover_teardown(self.browser, self.context, port=self.port)
        self.browser = None
        self.context = None
