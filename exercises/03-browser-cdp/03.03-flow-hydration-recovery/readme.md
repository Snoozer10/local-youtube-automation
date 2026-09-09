# 03.03 — Google Flow SPA Hydration Recovery

This drill teaches you to build a resilient Playwright automation loop that survives
post-reload SPA hydration race conditions, Angular CDK overlay interception, and
quota/rate-limit errors in Google Flow's React frontend.

## Production Case Study

> **293 consecutive frames generated — 1 self-healing recovery at Frame 264.**

During a live 22-minute video pipeline run (1334.49s of audio, 40,030 timeline frames),
all 293 storyboard images were generated via Google Flow automation. At Frame 264, the
queue stalled mid-generation (`"No generation card/progress appeared after 120s"`). The
hardened code automatically detected the stall, reloaded the workspace, re-injected the
prompt, and completed the frame on Attempt 2 — with zero human intervention.

Key resilience mechanisms that enabled this result:
- Hydration-safe poller (`wait_for_flow_input_box`) waiting up to 15s post-reload
- Card-spawn handshake tracking new card count before watchdog enters
- Guarded modal dismissal (never blindly presses Escape)
- Expanded quota/rate-limit error regex (`"reached your usage limit"`)
- Paired `.png` + `.html` diagnostic dumps on any stall

## What You Will Learn

- Why `domcontentloaded` fires before React has hydrated the `contenteditable` prompt bar
- How `page.wait_for_timeout()` keeps the Playwright CDP event loop pumped (unlike `time.sleep`)
- Why Angular Material CDK overlay menus portal to `div.cdk-overlay-container` (not the trigger button)
- How to detect and clear a `cdk-overlay-backdrop` that intercepts all pointer events
- How the **Card-Spawn Handshake** distinguishes "stalled before generation" from "generating but no % indicator yet"
- How to detect quota/rate-limit errors early (`"You've reached your usage limit"`) and rotate accounts
- How to scope generation card activity watching to the **newest** card only
- How to save paired `.png` + `.html` diagnostic artifacts on any stall

## Drill Variants

| Variant | Path | Purpose |
| :--- | :--- | :--- |
| Explainer | [explainer/readme.md](explainer/readme.md) | Architecture deep-dive |
| Problem | [problem/exercise.py](problem/exercise.py) | Student TODO scaffold |
| Solution | [solution/exercise.py](solution/exercise.py) | Reference implementation |
| Tests | [solution/test_exercise.py](solution/test_exercise.py) | Deterministic pytest suite |

## Prerequisites

- Playwright Python (`pip install playwright && playwright install chromium`)
- `pytest` for the deterministic fixture-based test suite
- A running Chrome instance with CDP on `127.0.0.1:9222` (for live tests only — not required for the drill suite)
