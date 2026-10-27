# Case ID: ERR-005-gemini-thinking-selector

## Overview
- **Title**: Gemini Thinking Indicator Substring False-Positive
- **Responsible Layer**: browser.gemini
- **Status**: resolved
- **Date Recorded**: 2026-10-23
- **Affected Components**: Gemini browser transport, generation idle detection (`is_gemini_generating`)

## 1. Verified Facts
- Using substring matcher `[aria-label*='Thinking' i]` in `is_gemini_generating` caused false-positive generation detections.
- When user prompts contained the word "thinking" (e.g. `<thinking>...</thinking>`), Gemini SPA web UI assigned the entire prompt text to the aria-label of the prompt's "More options" button and sidebar links.
- Because `*=` matches any substring, `is_gemini_generating` returned `True` permanently, causing `wait_for_gemini_response` to time out after 120s despite Gemini having completed its response.

## 2. Hypotheses
- Broad CSS substring selectors on accessibility attributes reflect user-supplied prompt text, triggering permanent false-busy state.
- Confidence: high.

## 3. Attempts and Outcomes
- **Attempt 1**: Replace substring selector `*=` with exact attribute matches:
  `[aria-label='Thinking' i]`, `[aria-label='Thinking...' i]`, `[aria-label='يفكر' i]`, `[aria-label='يفكر...' i]`.
  - *Outcome*: Succeeded. Prompt reflection no longer matches generation indicator; responses detected reliably.

## 4. Remaining Gaps & False-Positive Boundaries
- **Boundaries**: Applies to Gemini web UI DOM structure. Does not apply to direct API transports (`google-genai` SDK).
- **Gaps**: Web UI changes could introduce new localized thinking indicator labels.

## 5. Verified Prevention Check
- **Rule / Guard**: Never use broad substring selectors like `*='Thinking'` on generic DOM elements; use exact attribute matchers.
- **Verification**: `tests/unit/test_gemini_idle_detection.py`

## 6. Evidence Links
- **Legacy Register**: [`docs/error-solving/understood-errors.md#gemini-thinking-indicator-substring-false-positive`](../understood-errors.md)
- **Source Code**: [`src/youtube_automation/production/briefs.py`](../../../src/youtube_automation/production/briefs.py)
