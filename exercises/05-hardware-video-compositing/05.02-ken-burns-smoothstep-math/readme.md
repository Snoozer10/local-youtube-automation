# Drill 05.02: Ken Burns Cubic Hermite Smoothstep Math & Speech Pacing

## Objectives
- Master the mathematical foundations of the **Cubic Hermite Smoothstep** easing function:
  $$S(t) = 3t^2 - 2t^3 = t^2(3 - 2t)$$
- Enforce $C^1$ continuity: prove boundary zero-derivative conditions ($S'(0) = 0$, $S'(1) = 0$) that eliminate jarring initial and terminal velocity jolts in camera pans and zooms.
- Implement **speech-paced zoom limits**: dynamically adjust camera motion intensity based on words-per-second (WPS) cadence clamped between $[0.75, 1.35]$ and maximum zoom ceiling $1.15$.
- Construct production FFmpeg `zoompan` filter strings with Lanczos chroma interpolation and BT.709 color accuracy.

## Architectural Context
In the video rendering engine ([`ken_burns.py`](file:///C:/Users/Snoozer/Downloads/Antigravity/Youtube%20Automation%202/buckup/Version%204%20before%20deepseek%20implementation%20plan/image_generation/src/youtube_automation/video/ken_burns.py)), static images are animated to create a documentary aesthetic. Linear camera motion causes noticeable robotic "snap" transitions at the start and end of clips.
The pipeline applies smoothstep easing to the normalized frame index $t = \frac{on - 1}{frames - 1}$:

```
Normalized Frame Progress t ──► [Smoothstep S(t) = t^2*(3-2t)]
                                           │
Speech Cadence (WPS) ─────────► [Pace Modulation Ratio]
                                           │
                                           ▼
               [Effective Zoom & Bounded Center Coordinates]
                                           │
                                           ▼
             FFmpeg 'zoompan' Expression (z, x, y, d, fps, bt709)
```

## Input/Output Contracts
- `cubic_hermite_smoothstep(t: float) -> float`:
  - Input: Normalized progress $t \in \mathbb{R}$.
  - Clamps $t$ to $[0.0, 1.0]$ and evaluates $3t^2 - 2t^3$.
- `calculate_pace_modulated_zoom(duration: float, words_per_second: float = 3.0, zoom_min: float = 1.0, zoom_max: float = 1.10, dynamic_enabled: bool = True) -> float`:
  - Input: Audio segment duration, words-per-second, and zoom boundaries.
  - Output: Modulated maximum zoom float rounded to 4 decimal places, capped at $1.15$.
- `build_filter_expression(config: dict[str, Any], frame_count: int, camera_action: str, words_per_second: float = 3.0) -> str`:
  - Output: Complete FFmpeg video filter expression starting with `scale=...` and ending with `format=...`.

## Drill Variants
- [Detailed Architectural Explainer](explainer/readme.md)
- [Problem Workspace (Student)](problem/exercise.py)
- [Solution Reference](solution/exercise.py)
- [Solution Verification Tests](solution/test_exercise.py)
