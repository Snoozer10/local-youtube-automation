# Note: Compound-Aware Regex Mutation and Active Surface Telemetry

**Category:** Prompt Engineering  
**Date Logged:** 2026-09-16  
**Relevant Code Files:** `src/youtube_automation/prompts/prompt_enhancer.py`, `tests/unit/test_prompt_enhancer.py`  
**Audit Reference:** Section 2.1, Section 4.1, Section 4.4  

### 1. Core Rule in Plain English
Text surface neutralization must never perform naive unbounded word-boundary substitutions on solitary nouns (`board`, `screen`, `book`). High-precision compound phrases (`circuit board`, `split-screen`, `open book`) must be matched first with active non-linguistic data telemetry, solitary nouns must be guarded by strict negative lookbehinds, and all replacement patterns must be mathematically idempotent ($\text{neutralize}(\text{neutralize}(x)) == \text{neutralize}(x)$).

### 2. The Failure Mode It Prevents
Naive regex replacement transforms technical terms into nonsensical corruptions (`circuit board` becomes `circuit blank unmarked wooden board with zero writing`; `split-screen` becomes `split-blank dark glass monitor without display`; `open book` becomes the antonymous state collision `open retro blank closed book with unmarked plain cover`). Furthermore, suppressing text by inserting dead blank boards and black glass monitors violates Mayer's Signaling Principle by silencing the visual channel during dense explanations. Successive passes also trigger exponential recursive duplication on tokens like `schematics` and `telemetry`.

### 3. Implementation Specification
Implemented a 4-tier regex substitution architecture in `src/youtube_automation/prompts/prompt_enhancer.py`:
1. **Priority 0 (`LEGACY_CORRUPTION_REPAIR_RULES`)**: Fixes pre-existing corrupted dataset strings.
2. **Priority 1 (`COMPOUND_SURFACE_RULES`)**: Replaces compound terms with active non-linguistic telemetry (e.g. `circuit board` $\to$ `printed circuit schematic board with copper trace paths and glowing micro-nodes`; `split-screen` $\to$ `split-screen dual composition with bilateral comparative panels`; `open book` $\to$ `open technical reference ledger with abstract non-textual proportion charts`).
3. **Priority 2 (`GUARDED_SOLITARY_SURFACE_RULES`)**: Solitary nouns protected by negative lookbehinds (e.g. `(?<!\bsplit-)(?<!\bsplit\s)...(screens?|monitors?)` $\to$ `digital telemetry display with abstract waveform traces and glowing coordinate nodes`).
4. **Idempotence Guards**: Replacements guarded against self-matching (e.g. `(?!\s+dual\s+composition)`, `(?<!\bdark\smatte\s)`, `(?<!\bwax\s)`, `(?<!\bvector\s)`), guaranteeing $\text{neutralize}(\text{neutralize}(x)) == \text{neutralize}(x)$.

```python
def neutralize_surfaces(text: str) -> str:
    if not text:
        return ""
    result = text
    for pattern, repl in LEGACY_CORRUPTION_REPAIR_RULES:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)
    result = re.sub(r"['\"][^'\"]*['\"]", "", result)
    for pattern, repl in COMPOUND_SURFACE_RULES:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)
    for pattern, repl in GUARDED_SOLITARY_SURFACE_RULES:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)
    result = re.sub(r"\b(clean 2D vector schematics\s*){2,}", "clean 2D vector schematics ", result)
    result = re.sub(r"\b(digital telemetry display\s*){2,}", "digital telemetry display ", result)
    result = re.sub(r"\s+", " ", result).strip()
    result = re.sub(r"\s+([,.:;])", r"\1", result)
    return result
```

### 4. Verification Check
Run targeted test suite:
```bash
python -m pytest tests/unit/test_prompt_enhancer.py -v
```
Verifies:
- `test_neutralize_surfaces`: Asserts active telemetry tokens (`dark matte chalkboard with clean geometric diagrams`, `drafting placard displaying abstract non-textual ratio diagrams`, `stylized wax seal emblem`) and Latin text quarantine.
- `test_neutralize_surfaces_preserves_compound_nouns`: Asserts `circuit board`, `split-screen`, and `open book` preserve technical semantics and avoid antonymous state inversions.
- `test_neutralize_surfaces_idempotence`: Asserts triple-pass execution yields identical string outputs with zero recursive phrase duplication.
