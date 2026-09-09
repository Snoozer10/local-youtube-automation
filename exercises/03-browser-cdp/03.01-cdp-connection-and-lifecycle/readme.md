# Drill 03.01: Chrome DevTools Protocol (CDP) Connection & Lifecycle

## Objectives
- Master the Chrome DevTools Protocol (CDP) remote debugging loopback binding on TCP port 9222 (`127.0.0.1:9222`).
- Implement pre-flight port occupancy checks (`is_port_in_use`) and HTTP JSON version health probes (`/json/version`).
- Implement browser tab hygiene: detecting and pruning blank, orphaned, or transient tabs (`about:blank`) to prevent memory leaks and context corruption.
- Implement failover teardown sequencing: gracefully detaching Playwright CDP handles *before* killing the operating system process to avoid `TargetClosedError` and orphaned port locks.
- Annotate hardware and browser diagnostic tests with `@pytest.mark.drill`.

## Architectural Context
The pipeline automates Google Gemini and AI Studio via Playwright attached to an existing Chrome browser process ([`cdp_client.py`](file:///C:/Users/Snoozer/Downloads/Antigravity/Youtube%20Automation%202/buckup/Version%204%20before%20deepseek%20implementation%20plan/image_generation/src/youtube_automation/browser/cdp_client.py)):
```
[Playwright Sync API]
       │
       ▼ (CDP over WebSocket / HTTP)
[127.0.0.1:9222] ──► [Google Chrome / Opera Instance]
                           │
                 [Active Browser Context]
                 ├── Tab 1: Gemini Chat
                 ├── Tab 2: AI Studio Audio
                 └── Tab 3: about:blank (Pruned by Tab Hygiene)
```

## Input/Output Contracts
- `is_port_in_use(port: int = 9222, host: str = "127.0.0.1") -> bool`:
  - Returns `True` if local TCP socket binds or connects, `False` otherwise.
- `verify_cdp_port(port: int = 9222, host: str = "127.0.0.1", timeout_seconds: float = 2.0) -> bool`:
  - Returns `True` if `http://{host}:{port}/json/version` responds with HTTP 200, `False` on timeout or connection refusal.
- `clean_context_tabs(context: Any) -> int`:
  - Iterates over `context.pages`, closes any page whose URL is `about:blank` or `""`, and returns the count of closed tabs.
- `safe_failover_teardown(browser: Any = None, context: Any = None, port: int = 9222, kill_callback: Any = None) -> None`:
  - Closes context, closes browser handle, and then invokes process teardown / profile rotation.

## Drill Variants
- [Detailed Architectural Explainer](explainer/readme.md)
- [Problem Workspace (Student)](problem/exercise.py)
- [Solution Reference](solution/exercise.py)
- [Solution Verification Tests](solution/test_exercise.py)
