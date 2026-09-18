# Note: Imperative Translation Armor and Conversational Chatter Sanitization

**Category:** Prompt Engineering  
**Date Logged:** 2026-09-17  
**Relevant Code Files:** `automate_all.py`, `tests/unit/test_phase1_sanitizer.py`  
**Audit Reference:** Phase 1 Transcreation & Phase 2 Refinement  

### 1. Core Rule in Plain English
Sequential LLM transcreation prompts must use strict imperative command framing and negative prohibition directives, coupled with an automated post-response Arabic character ratio validation gate ($\ge 35\%$) and regex conversational chatter sanitization to prevent chat models from replacing source text with conversational review commentary or wrapping translations in English meta-text.

### 2. The Failure Mode It Prevents
When injecting paragraphs with passive framing (e.g. `paragraph 1 outof 19...`), chat LLMs often mistake the prompt for a writing critique request and return conversational review praise (e.g. "That is a fantastic hook... how would you like to proceed?") rather than translating. Without language ratio validation, the pipeline saves the English chat commentary, permanently dropping source paragraphs from `final_output.txt`.

### 3. Implementation Specification
```python
# 1. Imperative command framing
formatted_prompt = (
    f"DIRECTIVE: Transcreate Paragraph {i} of {total_paragraphs} into the Al-Daheeh Egyptian Arabic persona.\n"
    "CRITICAL: Output ONLY the Arabic transcreated text. Do NOT include any English preamble, greetings, commentary, review feedback, or questions:\n\n"
    f"{paragraph}"
)

# 2. Arabic script density gate
def is_valid_arabic_transcreation(text: str) -> bool:
    if not text or len(text.strip()) < 15:
        return False
    arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
    total_chars = len(re.sub(r"\s+", "", text))
    return total_chars > 0 and (arabic_chars / total_chars) >= 0.35

# 3. Conversational chatter stripping
def sanitize_gemini_chatter(text: str) -> str:
    ...
```

### 4. Verification Check
Run `python -m pytest tests/unit/test_phase1_sanitizer.py -v` (5/5 PASS).
