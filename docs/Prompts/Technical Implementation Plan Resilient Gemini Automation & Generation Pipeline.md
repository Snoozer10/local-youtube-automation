# Technical Implementation Plan: Resilient Gemini Automation & Generation Pipeline

---

## 1. Root Cause Analysis (RCA)

```
                       ┌────────────────────────────────────────────────────────┐
                       │          GEMINI WEB APP AUTOMATION PIPELINE            │
                       └────────────────────────────────────────────────────────┘
                                                    │
        ┌───────────────────────────────────────────┼───────────────────────────────────────────┐
        ▼                                           ▼                                           ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐   ┌───────────────────────────────┐
│   Phase 1: Output Limit       │   │   Phase 2A: DOM Injection     │   │   Phase 2B: Attention Drift   │
├───────────────────────────────┤   ├───────────────────────────────┤   ├───────────────────────────────┤
│ • Max ~2048-4096 tokens/turn  │   │ • `rich-textarea` buffer drop │   │ • KV-cache dilution (10+ turns│
│ • Markdown table: ~60 tok/row │   │ • Synthetic event throttling  │   │ • Recency bias pushes system  │
│ • Silent cutoff at Row 50-60  │   │ • Monolithic prompt (>15k ch) │   │   rules out of attention focus│
└───────────────────────────────┘   └───────────────────────────────┘   └───────────────────────────────┘
```

### 1.1 Single-Turn Output Token Truncation (Gemini Web App Limit)
* **Underlying Mechanism**: Consumer-facing web interfaces for large language models (including `gemini.google.com`) enforce hard output token generation budgets per turn (typically capped between $2{,}048$ and $4{,}096$ completion tokens depending on runtime load and model tier). 
* **Downstream Impact**: In Phase 1, generating a markdown table covering an entire video transcript requires approximately $50$ to $65$ tokens per row (accounting for Markdown syntax, timestamp brackets, descriptions, and color codes). When a script exceeds $45\text{--}50$ scenes:
  $$\text{Total Tokens} = 60 \text{ rows} \times 60 \text{ tokens/row} \approx 3{,}600 \text{ tokens}$$
  This approaches the output token ceiling. The model stops generating mid-sentence or mid-row without an explicit EOF token or error code, causing silent timeline truncation.

### 1.2 Web UI DOM & Input Buffer Character Injection Limits
* **Underlying Mechanism**: The Gemini Web App input container (`rich-textarea div[contenteditable="true"]`) is powered by an Angular/Lit customized rich-text editor that processes input via custom mutation listeners and synthetic `InputEvent` dispatchers.
* **Downstream Impact**: 
  1. Injecting monolithic payloads ($>15{,}000$ characters, such as the full system prompt plus the entire script/roadmap) via Playwright’s standard `fill()` or `insert_text()` causes dropped keystrokes, event loop starvation, and DOM truncation.
  2. Large text pastes into `contenteditable` nodes often trigger internal sanitize routines that drop trailing markdown syntax or cause text node splitting, corrupting the prompt payload before submission.

### 1.3 Multi-Turn Context Drift & Attention Degradation
* **Underlying Mechanism**: As a single chat session progresses past 8–10 turns, the cumulative context window expands rapidly with bulky raw JSON responses. Transformer self-attention undergoes **KV-cache dilution** and **"Lost in the Middle" degradation**.
* **Downstream Impact**: 
  - Recency bias causes the model to prioritize matching the *structure* of recent assistant turns rather than the *system constraints* defined in Turn 1.
  - Negative constraints (e.g., `"DO NOT write for subtitles"`, `"Text overlay must be NONE or Arabic"`) lose attention weight.
  - Image prompt descriptions degrade from high-density, multi-layered visual tokens into generic, repetitive placeholders.

---

## 2. Architectural & Pipeline Solutions

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                REFACTORED WORKFLOW ARCHITECTURE                                 │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                 │
 ┌───────────────────────────────────────────────┴───────────────────────────────────────────────┐
 │                                                                                               │
 ▼                                                                                               ▼
┌─────────────────────────────────────────────────┐   ┌─────────────────────────────────────────────────┐
│     PHASE 1: PAGINATED ROADMAP GENERATOR        │   │       PHASE 2: STATELESS CHUNK PROMPTER         │
├─────────────────────────────────────────────────┤   ├─────────────────────────────────────────────────┤
│ 1. Slice Script into Windows of 25-30 lines     │   │ 1. Extract *Slice-Only* Roadmap (15 items)      │
│ 2. Generate Page K with Anchor = (End of K-1)   │   │ 2. Spin Fresh Session (or Purge History)        │
│ 3. Stream to Disk Checkpoint `roadmap.jsonl`    │   │ 3. Inject Compact Preamble + 15 Target Items    │
│ 4. Deterministic Sequence & Continuity Guard    │   │ 4. Single-Turn JSON Output -> Schema Validator  │
└─────────────────────────────────────────────────┘   └─────────────────────────────────────────────────┘
```

### 2.1 Phase 1 Solution: Roadmap Paging & Incremental Assembly
Instead of requesting a complete roadmap in a single monolithic prompt, we implement a **Paging Orchestrator** using a sliding line-window approach:

1. **Windowing**: Subdivide the parsed transcript into deterministic slices of $N = 25$ sentences.
2. **Anchor Continuation Directive**: For page $K > 1$, feed the *exact last row* of Page $K-1$ as a continuity anchor.
3. **Prompt Envelope**:
   ```text
   [SYSTEM DIRECTIVE: VISUAL ROADMAP ARCHITECT]
   Generate roadmap entries ONLY for Script Indices {start_idx} through {end_idx}.
   CONTINUITY ANCHOR (Index {start_idx - 1}): "{previous_last_row_summary}"
   
   Strict Constraint: Output MUST start at Index {start_idx} and end at Index {end_idx}.
   Output format: Raw Markdown Table rows only (do not repeat headers for subsequent pages).
   ```
4. **On-Disk Streaming**: Append verified rows directly to `master_roadmap.jsonl` or `master_roadmap.md` immediately upon arrival.

---

### 2.2 Phase 2A Solution: Payload Optimization & Direct CDP Injection
To bypass `contenteditable` buffer limits and eliminate prompt bloat:

1. **Context Slicing (De-Monolithing)**: Never inject the full 100+ line roadmap into JSON planning chunks. For Chunk $M$ (covering indices $31\text{--}45$), slice and inject **only Roadmap Rows $30\text{--}46$** (providing 1 item of backward/forward context buffer).
2. **Token-Dense Preamble**: Remove verbose explanations and conversational filler from the system prompt. Encode rules into compact, high-salience symbolic notation:
   ```yaml
   STYLE_DNA: "2D graphic vector animation, 3px black vector outlines, 2-step cel-shading, 16:9"
   CHARACTERS:
     HOST: "Ahmed El-Ghandour (Al-Daheeh), wire glasses, afro curl hair, charcoal hoodie #2B2D42"
     SKEPTIC: "Abo Hmeed, navy jacket #1D3557, grey tee, bewildered expression"
     CLERK: "Science Bureaucrat, beige suit #D4C5A9, messy hair, oversized square glasses"
   FORBIDDEN: ["subtitles", "margin", "watermark", "Latin text", "English overlay"]
   ```
3. **CDP Synthetic Paste Injection**: Instead of slow typing or basic `fill()`, write the payload to the browser's internal clipboard via JavaScript execution and dispatch an OS-level synthetic `Control+V` or use the Chrome DevTools Protocol (`Input.insertText` / `Clipboard.writeText`).

---

### 2.3 Phase 2B Solution: Ephemeral Stateless Session Architecture
To completely eradicate multi-turn attention drift, we transition from a long-lived stateful chat session to an **Ephemeral Stateless Lifecycle**:

```
Stateful Multi-Turn (FLAWED):
[Turn 1: System + Chunk 1] ➔ [Turn 2: Chunk 2] ➔ ... ➔ [Turn 10: Chunk 10 (DRIFT OCCURS)]

Stateless Ephemeral Pattern (REFACTORED):
[Worker Chat 1] ➔ [System + Slice 1] ➔ Extract JSON ➔ Destroy/Reset Chat
[Worker Chat 2] ➔ [System + Slice 2] ➔ Extract JSON ➔ Destroy/Reset Chat
```

* **Execution Flow**:
  1. For each chunk of 15 frames, navigate to `https://gemini.google.com/app` (or click "New Chat").
  2. Send a unified, single-shot payload containing: `[Compact System Preamble] + [Target Roadmap Slice (15 Items)] + [Target Script Slice]`.
  3. Gemini responds in Turn 1 with pristine, high-attention JSON adhering 100% to all formatting rules and visual tokens.
  4. Response is validated and committed to disk; the session is discarded.

---

## 3. State Management, Checkpointing & Fault Tolerance

### 3.1 Local Checkpointing & Manifest Architecture
A persistent, JSON-based state manifest (`pipeline_manifest.json`) tracks the lifecycle of every frame and chunk across unexpected halts or restarts.

```json
{
  "project_id": "youtube_run_2026_08_25_001",
  "script_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "roadmap_phase": {
    "status": "COMPLETED",
    "total_lines": 85,
    "completed_pages": [1, 2, 3, 4],
    "last_processed_index": 85
  },
  "planning_phase": {
    "status": "IN_PROGRESS",
    "chunk_size": 15,
    "total_chunks": 6,
    "chunks": {
      "chunk_1": { "indices": [1, 15], "status": "VERIFIED", "attempts": 1 },
      "chunk_2": { "indices": [16, 30], "status": "VERIFIED", "attempts": 1 },
      "chunk_3": { "indices": [31, 45], "status": "PENDING", "attempts": 0 }
    }
  },
  "rendering_phase": {
    "completed_indices": [1, 2, 3, 4, 5, 6, 7]
  }
}
```

* **Atomic Commits**: All manifest updates and prompt file writes execute via an atomic `.tmp -> os.replace()` pattern to prevent file corruption during sudden terminations.

### 3.2 Resilience & Exponential Backoff State Machine
When rate limits (HTTP 429 / Web UI warning modals) or network disconnects occur, the driver enters an isolated recovery state:

```
                  ┌──────────────────────────────┐
                  │      EXECUTE PROMPT TURN     │
                  └──────────────┬───────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       [Response Received]               [Anomaly Detected]
                 │                               │
        ┌────────┴────────┐             ┌────────┴────────┐
        ▼                 ▼             ▼                 ▼
  (Valid JSON)     (Schema Error)   (DOM Freeze)     (Rate Limit)
        │                 │             │                 │
  [Save Chunk]      [Self-Healing]   [Reload Chat]   [Exp. Backoff]
                      (Max 2 retries)  (CDP Resume)   (Wait 2^k * 15s)
```

---

## 4. DOM Synchronization & JSON Sanitization Pipeline

### 4.1 Tri-Factor Deterministic Completion Handshake
Relying solely on arbitrary sleep timers or single spinner checks results in race conditions. We implement a **Tri-Factor DOM Handshake**:

```python
def wait_for_gemini_turn_completion(page, timeout: float = 120.0) -> str:
    """
    Tri-Factor Handshake:
    1. Check presence/absence of Stop/Progress indicators.
    2. Inter-probe text delta stability over 3.0 seconds (delta == 0).
    3. Structural sentinel verification (detecting closing ``` or ]).
    """
    start_time = time.time()
    last_text = ""
    stable_since = None
    
    # 1. Wait for response generation to mount
    page.wait_for_selector("model-response", timeout=15000)
    
    while time.time() - start_time < timeout:
        # Check active generation indicators
        is_generating = page.locator(
            "mat-progress-spinner, [aria-label*='Stop' i], .thinking-indicator"
        ).count() > 0
        
        response_locator = page.locator("model-response").last
        current_text = response_locator.evaluate("el => el.innerText || ''").strip()
        
        # Check text delta
        if current_text and current_text == last_text and not is_generating:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= 3.0:
                # Structural Sentinel Check: Check if markdown code block or JSON array has closed
                if "```" in current_text or current_text.rstrip().endswith("]"):
                    return current_text
        else:
            last_text = current_text
            stable_since = None
            
        time.sleep(0.5)
        
    raise TimeoutError("Gemini response stream timed out before DOM stabilized.")
```

---

### 4.2 Multi-Tier Industrial JSON Repair Engine
LLMs occasionally generate unescaped double quotes inside visual prompt strings or emit unclosed JSON arrays. The post-processing pipeline uses a 4-tier repair hierarchy:

```python
import json
import re

def clean_and_repair_json(raw_text: str) -> list[dict]:
    """
    Multi-Tier JSON Repair:
    Tier 1: Direct JSON Parse of Markdown codeblock.
    Tier 2: Regex unescaped quote repair inside string literals.
    Tier 3: Trailing comma & missing closing bracket restoration.
    Tier 4: Token stream / Brace matching parser fallback.
    """
    # Strip markdown wrappers
    cleaned = re.sub(r"^.*?```(?:json)?", "", raw_text, flags=re.DOTALL)
    cleaned = re.sub(r"```.*?$", "", cleaned, flags=re.DOTALL).strip()
    
    # Tier 1: Fast direct parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Tier 2: Sanitize internal quotes within visual_prompt fields
    # Fixes unescaped quotes like: "subject_details": "Ahmed holding a "plastic cup" of tea"
    fixed = re.sub(
        r'(?<=:\s")([^"\\]*?)"([^"\\]*?)"(?=[\s,}])',
        r'\1\"\2\"',
        cleaned
    )
    
    # Tier 3: Strip trailing commas before closing braces/brackets
    fixed = re.sub(r",\s*([\]}])", r"\1", fixed)
    
    # Auto-close unclosed array
    if fixed.startswith("[") and not fixed.rstrip().endswith("]"):
        fixed = fixed.rstrip() + "]"
        
    try:
        data = json.loads(fixed)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Tier 4: AST regex object extractor fallback
    extracted_objects = []
    object_matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned)
    for obj_str in object_matches:
        try:
            obj = json.loads(obj_str)
            if "index" in obj and "visual_prompt" in obj:
                extracted_objects.append(obj)
        except Exception:
            continue
            
    if extracted_objects:
        return extracted_objects
        
    raise ValueError("Failed to extract valid JSON structures from model response.")
```

---

## 5. Step-by-Step Refactoring & Task Breakdown

### Component A: Browser Controller (`gemini_controller.py`)
- **Task A1**: Implement `inject_prompt_via_cdp(page, text)` using native clipboard injection (`navigator.clipboard.writeText` + `Control+V`) to bypass character dropping on large prompts.
- **Task A2**: Implement `wait_for_gemini_turn_completion(page)` incorporating the Tri-Factor Handshake.
- **Task A3**: Add an auto-recovery method `reset_chat_session(page)` that navigates cleanly to `https://gemini.google.com/app` and verifies input readiness.

### Component B: Paged Roadmap Generator (`roadmap_orchestrator.py`)
- **Task B1**: Build `split_transcript_into_windows(script_lines, window_size=25)`.
- **Task B2**: Implement `generate_roadmap_page(page, window, page_idx, anchor_row)` with strict continuation instructions.
- **Task B3**: Build `RoadmapValidator` to verify that indices form a continuous sequence $1..N$ and that markdown tables are parsed into typed Python objects.

### Component C: Stateless JSON Planning Engine (`prompt_planner.py`)
- **Task C1**: Implement `extract_roadmap_slice(full_roadmap, start_idx, end_idx)` to slice only relevant context.
- **Task C2**: Construct the `CompactTokenSystemPreamble` eliminating conversational tokens.
- **Task C3**: Implement the stateless execution loop:
  1. Open fresh chat turn.
  2. Send `[Compact System Preamble] + [Roadmap Slice] + [Script Chunk]`.
  3. Extract response with `clean_and_repair_json()`.
  4. Perform self-healing repair prompt if any indices are missing.
  5. Commit chunk to `flow_prompts.json`.

### Component D: Verification & Quality Guard (`validator.py`)
- **Task D1**: Implement strict Pydantic schema validation.
- **Task D2**: Implement the **Anti-Subtitle / Negative Constraint Guard** that flags and auto-cleans terms like `"for subtitles"`, `"lower margin"`, or `"caption area"`.
- **Task D3**: Implement the **Arabic Typography Normalizer** verifying that all text overlays use Arabic Kufic script or strictly `"NONE"`.

---

## 6. Verification, Continuity & Quality Protocols

### 6.1 Mathematical Continuity & Index Validation Contract
Before allowing Phase 2 (Image Rendering in Google Flow) to begin, the pipeline runs an automated suite of verification assertions:

$$\forall i \in [1, N-1]: \quad \text{Index}_{i+1} - \text{Index}_i = 1$$
$$\forall i \in [1, N-1]: \quad \text{Timestamp}_{i} \le \text{Timestamp}_{i+1}$$

```python
def verify_pipeline_integrity(flow_prompts: list[dict], expected_total: int):
    """Executes pre-flight continuity assertions."""
    indices = [p["index"] for p in flow_prompts]
    
    # 1. Zero Missing Index Assertion
    assert len(indices) == expected_total, f"Expected {expected_total} prompts, got {len(indices)}"
    assert sorted(indices) == list(range(1, expected_total + 1)), "Index sequence has gaps or duplicates!"
    
    # 2. Schema Completeness Assertion
    for item in flow_prompts:
        vp = item.get("visual_prompt", {})
        assert "subject_details" in vp and vp["subject_details"], f"Item {item['index']} missing subject_details"
        assert "style_anchor" in vp and vp["style_anchor"], f"Item {item['index']} missing style_anchor"
        assert "composition_layout" in vp, f"Item {item['index']} missing composition_layout"
        
        # 3. Negative Constraint Filter Check
        combined_text = json.dumps(item, ensure_ascii=False).lower()
        assert "subtitle" not in combined_text, f"Item {item['index']} violates subtitle constraint!"
        assert "margin" not in combined_text, f"Item {item['index']} violates margin constraint!"
        
    print(f"✅ All {expected_total} storyboard frames passed 100% of continuity and schema assertions.")
```

### 6.2 Visual Consistency & Invariant Standards Matrix

| Element | Strict Invariant Token / Rule | Verification Check |
| :--- | :--- | :--- |
| **Art Style** | `2D graphic vector animation explainer style, crisp 3px black vector outlines, flat 2-step cel-shading` | Validates that `"style_anchor"` contains 3px vector & cel-shading keywords. |
| **Host Character** | `Ahmed El-Ghandour (Al-Daheeh), thin round glasses, curly afro hair, charcoal hoodie #2B2D42` | Verifies biometrics invariance across all `"HOST"` frames. |
| **Skeptic Character** | `Abo Hmeed, casual navy jacket #1D3557, heather-grey tee, expressive questioning look` | Ensures character consistency in reaction shots. |
| **Bureaucrat Character** | `Science Bureaucrat, oversized vintage beige suit #D4C5A9, crooked striped tie, thick square glasses` | Verifies visual consistency across all diagrammatic / institutional metaphors. |
| **Typography** | Authentic Arabic calligraphy in modern Kufic script, or strictly `"NONE"` | Regex check matches Arabic Unicode range `[\u0600-\u06FF]` or `"NONE"`. Fails on Latin text. |
| **Negative Prompts** | `No 3D CGI, no photorealism, no gradients, no subtitle boxes, no English labels` | Automated regex purge during prompt flattening. |

---

## 7. Recommended Implementation Sequence

```
[Day 1: Foundation]
 ├── Refactor Browser Controller with CDP Clipboard Injection
 └── Implement Tri-Factor Completion Handshake & Multi-Tier JSON Parser

[Day 2: Phase 1 Overhaul]
 ├── Implement 25-line Windowed Roadmap Pager with Continuation Anchors
 └── Add Atomic Manifest Checkpoint Layer (`pipeline_manifest.json`)

[Day 3: Phase 2 Overhaul]
 ├── Implement Ephemeral Stateless Session Lifecycle for JSON Planning
 └── Build Sliced-Roadmap Context Injector (15-line slices)

[Day 4: Quality & End-to-End Validation]
 ├── Deploy Automated Schema & Visual Invariant Integrity Guard
 └── Run full 100+ frame pipeline simulation and stress tests
```