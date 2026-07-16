# Implementation Plan: Post-Production Automations (P1)

**Branch**: `001-video-post-automations` | **Date**: 2026-07-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-video-post-automations/spec.md`

## Summary

Add Arabic script refinement (`refine_script.py`) as step 1b in the YouTube automation pipeline, extract 5 shared Gemini UI helpers into `gemini_utils.py` (FR-008), wire refinement into `run_agency.py` (FR-007), and add thumbnail generation (`generate_thumbnail.py`) with Nano Banana Pro prompts and a self-critique loop. All AI interactions use Playwright CDP against Gemini Web UI — no API SDKs.

## Technical Context

**Language/Version**: Python 3.10+ (Windows-only)

**Primary Dependencies**: Playwright (CDP browser automation), python-docx (Word document generation), youtube_transcript_api (transcript fetching — existing)

**Storage**: Filesystem only — JSON checkpoints under `youtube_runs/<Title>/`, no database

**Testing**: Manual verification — no test framework in use. Validation via spot-check of refined script output and thumbnail images.

**Target Platform**: Windows 10/11 (hardcoded Chrome/Opera/Audacity paths, ctypes clipboard, CREATE_NEW_CONSOLE flags)

**Project Type**: CLI automation scripts (pipeline of standalone Python scripts orchestrated by `run_agency.py`)

**Performance Goals**: Each paragraph refinement completes in <60s (Gemini response time). Thumbnail pipeline (5 concepts + critique + 2 generations) completes in <10 minutes.

**Constraints**: Browser must be manually signed into Gemini before running. CDP on port 9222. Account rotation 1→3 (Default/Profile 1/Profile 2). Max retries per FAILOVER_RETRY_LIMIT.

**Scale/Scope**: Single channel, one video at a time. Typical script: 10-30 paragraphs. Thumbnail pipeline: 5 variants → 2 winners.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design. Each bullet is a concrete, review-checkable assertion against the ratified constitution (image_generation/.specify/memory/constitution.md, v1.0.0).*

- [x] **I. Browser-Automation-Only AI** — `refine_script.py` and `generate_thumbnail.py` will use `gemini_utils.py` helpers (extracted from `automate_all.py`). All Gemini interactions use Playwright CDP. No AI API SDK imported. `find_input_box`, `find_send_button` use prioritized fallback selector lists (5-6 selectors each). `wait_for_gemini_response` uses growth monitoring + send button state — not blind sleep.
- [x] **II. Checkpoint & Resume Safety** — `refine_checkpoint.json` written under `youtube_runs/<Title>/`. Rerun resumes from last paragraph. Checkpoint deleted on completion. `thumbnail_prompts.json` and `thumbnail_critique.json` also under run folder.
- [x] **III. Orchestrator Discipline** — `run_agency.py` is the orchestrator. `refine_script.py` added as step 1b. `IMAGE_GENERATOR_TYPE` not affected (thumbnail is separate from storyboard flow).
- [x] **IV. Account Rotation & Profile Mapping** — `refine_script.py` and `generate_thumbnail.py` use `rotate_profile_index()` and `kill_cdp_chrome()` from `utils.py`. Profile cycles 1→3.
- [x] **V. Windows-Only Hardcoded Constraints** — No new hardcoded paths. Browser launch delegated to `utils.py:launch_browser_with_profile()`. New scripts follow existing pattern.
- [x] **VI. UTF-8 / Arabic Correctness** — Both new scripts call `sys.stdout.reconfigure(encoding='utf-8')`. JSON written with `ensure_ascii=False`. Arabic text in `refined_script.txt`, `refined_script.docx`, `thumbnail_prompts.json`.
- [x] **VII. Secrets & Security (NON-NEGOTIABLE)** — No new secrets. `THUMBNAIL_MODEL` added to `gemini_model.txt` (already in .gitignore). No API keys used.
- [x] **VIII. Idempotent Rerun / Stateless Skip** — `generate_thumbnail.py` skips if `thumbnails/` has ≥2 files. `refine_script.py` resumes from checkpoint. Both safe to rerun.
- [x] **IX. Simplicity / Preferred Paths** — No unrequested features. `THUMBNAIL_MODEL` is the only new config field. Thumbnail generation is separate from storyboard (no interference with existing image flow).

## Project Structure

### Documentation (this feature)

```text
specs/001-video-post-automations/
├── spec.md              # Feature specification (created by /speckit.specify)
├── plan.md              # This file (/speckit.plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── checklists/
│   └── requirements.md  # Requirements checklist
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
image_generation/
├── gemini_utils.py          # NEW — 5 shared Gemini UI helpers (FR-008)
├── refine_prompt.txt        # NEW — Two-turn refinement prompt
├── refine_script.py         # NEW — Paragraph-level Arabic refinement (US1)
├── generate_thumbnail.py    # NEW — Thumbnail pipeline with self-critique
├── utils.py                 # EXISTING — Config, browser launch, Telegram
├── automate_all.py          # EXISTING — Source of extracted helpers
├── run_agency.py            # MODIFIED — Add refine step 1b (FR-007)
├── gemini_model.txt         # MODIFIED — Add THUMBNAIL_MODEL
├── prompt_phase3.txt        # EXISTING — Translation prompt (reference)
├── prompt.txt               # EXISTING — Paragraph breaking prompt (reference)
└── youtube_runs/<Title>/    # Output directory
    ├── final_output.txt         # Input to refinement
    ├── refined_script.txt       # Output from refinement
    ├── refined_script.docx      # Word document copy
    ├── refine_checkpoint.json   # Resume state (deleted on completion)
    ├── thumbnails/              # Thumbnail output directory
    │   ├── variant_1.png
    │   └── variant_2.png
    ├── thumbnail_prompts.json   # Nano Banana Pro prompts
    └── thumbnail_critique.json  # Gemini critique scores
```

**Structure Decision**: Flat single-directory structure matching existing codebase convention. No subdirectories for source — all scripts live at project root alongside `utils.py`. New files (`gemini_utils.py`, `refine_script.py`, `generate_thumbnail.py`, `refine_prompt.txt`) follow the same pattern as existing scripts.

## Complexity Tracking

> No Constitution Check violations. All 9 principles pass without justification needed.
