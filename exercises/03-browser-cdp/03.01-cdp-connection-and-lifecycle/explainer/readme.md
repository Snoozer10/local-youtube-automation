# Explainer: CDP Lifecycle, Port Probing, & Tab Hygiene

## 1. Remote Debugging over TCP Port 9222
When Chrome is launched with `--remote-debugging-port=9222`, it exposes a loopback HTTP/WebSocket server.
Before attempting a full Playwright CDP attachment (which incurs overhead and spawns background worker threads), the pipeline performs a two-tier pre-flight probe:
1. **Tier 1 (Socket Connect)**: `connect_ex((host, 9222))` confirms if any process is listening on the port.
2. **Tier 2 (HTTP Version Verification)**: GET `http://127.0.0.1:9222/json/version` confirms that the responding process is indeed a Chromium-based CDP daemon returning protocol metadata (`Browser`, `Protocol-Version`, `webSocketDebuggerUrl`).

## 2. Tab Hygiene: Preventing Memory Bloat & Handle Leaks
Automated profile restarts or extension popups frequently spawn `about:blank` tabs. Over long-running 4-hour batch runs:
- Unchecked tabs consume significant V8 heap memory.
- `context.pages` lookups slow down linearly.
- Playwright events can latch onto orphaned tabs.

The tab hygiene sweep iterates through `context.pages` and safely invokes `.close()` on all blank pages:
```python
for p in list(context.pages):
    if p.url in ("about:blank", ""):
        p.close()
```

## 3. Orderly Failover Teardown: Eliminating `TargetClosedError`
A common anti-pattern in browser automation is forcibly killing the browser process (`taskkill /F /IM chrome.exe`) while Playwright is actively communicating over the WebSocket.
This causes:
- Unhandled `TargetClosedError` exceptions in pending event loops.
- Corrupted `Default/Preferences` files in the Chrome User Data Directory.
- Lingering TCP TIME_WAIT states on port 9222.

The **Graceful Teardown Pattern** enforces strict ordering:
1. `context.close()`: Tears down browser tabs and persists session cookies.
2. `browser.close()`: Disconnects the CDP WebSocket client cleanly.
3. OS Process Termination (`kill_cdp_chrome`): Kills any remaining browser PIDs after all handles are detached.
4. Profile Rotation: Updates active profile counter (`ACTIVE_PROFILE_INDEX`).
