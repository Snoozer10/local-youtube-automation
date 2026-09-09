# Drill 03.02: 3-Factor DOM Stability Handshake & Turn Completion Detector

## Objectives
- Master the **3-Factor DOM Stability Handshake** for robust scraping of streaming LLM web interfaces (Google Gemini & AI Studio).
- Detect active generation states: verify disappearance of Stop / Cancel / Interrupt buttons in English and Arabic (`button[aria-label*='Stop' i]`, `توقف`, etc.) and progress spinners (`mat-progress-spinner`, `.thinking-indicator`).
- Guard against premature extraction by enforcing minimum response node counts and character lengths.
- Implement streaming text stability tracking across consecutive observation intervals while filtering out transient analysis placeholders ("Analyzing", "Thinking...").
- Clean multi-lingual assistant prefixes (`Gemini said:`, `قال Gemini:`, etc.).

## Architectural Context
In web-based LLM automation ([`gemini_utils.py`](file:///C:/Users/Snoozer/Downloads/Antigravity/Youtube%20Automation%202/buckup/Version%204%20before%20deepseek%20implementation%20plan/image_generation/src/youtube_automation/browser/gemini_utils.py)), token generation is streamed asynchronously over WebSockets. Premature extraction yields broken JSON or incomplete Arabic sentences.
The **3-Factor Handshake** ensures a turn is truly complete before handing the response off to downstream parsers:

```
[Start Turn Extraction]
         │
         ▼
[Factor 1: Generator Active Check]
   ├─ Stop/Cancel button visible? ──► WAIT (still streaming)
   └─ Progress spinner active?    ──► WAIT (thinking phase)
         │ (Both inactive)
         ▼
[Factor 2: Node Mount & Length Threshold]
   ├─ Response elements > initial count?
   └─ Length >= min_length?
         │ (Satisfied)
         ▼
[Factor 3: Observation Stability Window]
   └─ Content identical across N consecutive checks (stable_count >= 5)?
         │ (True)
         ▼
[Strip Multi-lingual UI Prefixes] ──► Return Complete Clean Response
```

## Input/Output Contracts
- `is_generating_indicator_active(has_stop_button: bool, has_spinner: bool) -> bool`:
  - Returns `True` if stop button or spinner is present and visible.
- `clean_response_prefix(text: str) -> str`:
  - Strips prefixes like `Gemini said:`, `قال Gemini:`, `Gemini a dit:` from the response string.
- `evaluate_stability_step(current_text: str, last_text: str, stable_count: int, still_generating: bool, min_length: int = 10, target_stable: int = 5) -> tuple[int, str, bool]`:
  - Returns `(new_stable_count, updated_last_text, is_complete)`:
    - If `still_generating` or text is placeholder: resets `stable_count = 0`.
    - If text unchanged and meets length: increments `stable_count`. If `stable_count >= target_stable`, `is_complete = True`.
    - If text changed: sets `stable_count = 1`.

## Drill Variants
- [Detailed Architectural Explainer](explainer/readme.md)
- [Problem Workspace (Student)](problem/exercise.py)
- [Solution Reference](solution/exercise.py)
- [Solution Verification Tests](solution/test_exercise.py)
