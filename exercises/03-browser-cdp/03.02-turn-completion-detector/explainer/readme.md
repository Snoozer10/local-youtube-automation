# Explainer: 3-Factor DOM Stability Handshake

## 1. The Pitfalls of Streaming LLM UIs
Automating browser interfaces like Gemini Web involves asynchronous DOM mutations:
1. **Thinking Phase**: Gemini renders a thinking indicator or spinner (`.thinking-indicator`, `mat-progress-spinner`). The response container might already be mounted in the DOM, but contain only empty or transient strings ("Thinking...", "Analyzing").
2. **Streaming Bursts**: Tokens arrive in chunks over WebSockets. A naive check (`text != ""` or single-interval comparison) will capture partial text during a brief 200ms inter-chunk pause.
3. **Stop Button Latency**: The Stop button (`button[aria-label*='Stop' i]`) may remain in the DOM for several frames after generation ends, or conversely disappear slightly before all tokens are flushed into the rich-text editor.

## 2. The 3-Factor Handshake Invariants
To guarantee that a turn is 100% complete without false positives:
- **Factor 1: Indicator Deactivation**: Stop button, cancel button, and thinking spinners must be confirmed non-existent or invisible.
- **Factor 2: Threshold Gating**: The response must belong to the *new* turn (`current_count > initial_count`) and exceed `min_length`.
- **Factor 3: Temporal Stability Window**: The text must remain completely unchanged across multiple polling cycles (typically 5 consecutive checks) with transient placeholders explicitly rejected:
  ```python
  TRANSIENT_PLACEHOLDERS = {
      "analyzing",
      "thinking",
      "thinking...",
      "visualizing the scenes",
      "structuring the narrative",
  }
  ```

## 3. Multi-Lingual Assistant Prefix Sanitization
Gemini's web UI wraps output in localized labels depending on system locale or conversation language:
- English: `Gemini said: ...`
- Arabic: `قال Gemini: ...` or `رد Gemini: ...`
- French: `Gemini a dit: ...`
- German: `Gemini hat gesagt: ...`

Before delivering the extracted response, the completion detector applies a regular expression strip:
```python
prefix_pattern = r"^(?:Gemini\s+said|قال\s+Gemini|رد\s+Gemini|Gemini\s+a\s+dit|Gemini\s+hat\s+gesagt)[:\s]*"
cleaned = re.sub(prefix_pattern, "", text, flags=re.IGNORECASE).strip()
```
