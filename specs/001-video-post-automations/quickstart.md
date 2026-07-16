# Quickstart: Post-Production Automations (P1)

**Date**: 2026-07-11

## Prerequisites

- Python 3.10+ with `playwright`, `python-docx`, `youtube_transcript_api` installed
- Chrome or Opera browser signed into `gemini.google.com` and `aistudio.google.com`
- CDP debugging session running on port 9222
- `gemini_model.txt` configured with `REFINE_MODEL=Pro` and `THUMBNAIL_MODEL=Pro`

## Validation Scenarios

### Scenario 1: Script Refinement (US1)

**Setup**: Ensure a run folder exists with `final_output.txt` (from `automate_all.py`).

```bash
# Check input exists
dir youtube_runs\<Video Title>\final_output.txt

# Run refinement
python refine_script.py
```

**Expected outcome**:
- `youtube_runs/<Title>/refined_script.txt` created with improved Arabic text
- `youtube_runs/<Title>/refined_script.docx` created as Word document
- `refine_checkpoint.json` deleted after completion
- First paragraph has a hook (grab attention in first 15 seconds)
- Last paragraph has an outro CTA (subscribe/comment/next video)
- All factual content preserved (no information added or removed)

**Rerun test**:
```bash
# Simulate interruption: Ctrl+C during first run, then rerun
python refine_script.py
```

**Expected**: Resumes from last checkpoint paragraph, does not re-process completed paragraphs.

### Scenario 2: Gemini Utils Extraction (FR-008)

```bash
# Verify all 5 helpers import correctly
python -c "from gemini_utils import find_input_box, find_send_button, wait_for_gemini_response, start_clean_gemini_chat, select_gemini_model, RESPONSE_SELECTOR; print('All imports OK')"
```

**Expected**: `All imports OK` with no errors.

**Integration test**: Run `automate_all.py` on a new video — it should work identically since `gemini_utils.py` is a mechanical extraction with no logic changes.

### Scenario 3: Thumbnail Generation

**Setup**: Ensure `refined_script.txt` (or `final_output.txt`) exists in the run folder.

```bash
# Run thumbnail pipeline
python generate_thumbnail.py
```

**Expected outcome**:
- `youtube_runs/<Title>/thumbnails/` directory created
- 2 thumbnail images (PNG) in the thumbnails directory
- `youtube_runs/<Title>/thumbnail_prompts.json` with 5 Nano Banana Pro prompts
- `youtube_runs/<Title>/thumbnail_critique.json` with scores and winners

**Rerun test**: Run again — should skip if `thumbnails/` already has ≥2 files.

### Scenario 4: Pipeline Wiring (FR-007)

```bash
# Run full pipeline
python run_agency.py
```

**Expected**:
- After `automate_all.py` completes, `refine_script.py` runs automatically
- `pipeline.json` shows `"refine": true` after refinement
- Voice generation uses the refined script (not raw translation)

**Backward compatibility test**: Take an existing run folder, remove the `refine` key from `pipeline.json`, rerun `run_agency.py`.

**Expected**: Refinement is skipped (existing run treated as complete).

### Scenario 5: Config Readability

```bash
python -c "from utils import get_config_value; print('REFINE_MODEL:', get_config_value('REFINE_MODEL', 'Pro')); print('THUMBNAIL_MODEL:', get_config_value('THUMBNAIL_MODEL', 'Pro'))"
```

**Expected**: Both return `Pro` (or configured values).

## Edge Cases to Verify

1. **No `final_output.txt`**: `refine_script.py` exits with clear error message
2. **Gemini safety block**: `refine_script.py` retries with fresh chat, falls back to account rotation
3. **Empty Gemini response**: `wait_for_gemini_response` returns empty string, script handles gracefully
4. **Partial refinement**: Checkpoint saved, rerun resumes correctly
5. **Arabic text round-trip**: `refined_script.txt` and `.docx` contain correct Arabic without mojibake
