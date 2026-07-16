# Feature Specification: Post-Production Automations (P1)

**Feature Branch**: `001-video-post-automations`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Build three post-production automations: Arabic script refinement, metadata + title contest, and thumbnail generation. P1: refine_script.py + gemini_utils.py extraction + run_agency.py wiring. P2: generate_metadata.py (title tournament) + generate_thumbnail.py (Flow + Pillow overlay)."

## User Scenarios & Testing

### User Story 1 — Arabic Script Refinement (Priority: P1)

As the channel owner, after `automate_all.py` translates the script to Arabic, I want an automation that refines and enhances the script so it reads more fluently, maintains dialect consistency, and adds a strong opening hook and compelling outro — without altering the original meaning.

**Why this priority**: Refinement is the foundation for all downstream steps (metadata, thumbnails). It's a single Gemini turn per paragraph — simple, low failure surface, and validates the checkpoint/resume pattern before layering more complex automations.

**Independent Test**: Running `refine_script.py` on a run folder with `final_output.txt` produces `refined_script.txt` (+ `.docx`) that is longer/cleaner than the source, with a visible hook and outro. A rerun resumes from checkpoint and does not re-process completed paragraphs.

**Acceptance Scenarios**:
1. **Given** a run folder with `final_output.txt`, **When** `refine_script.py` runs, **Then** `refined_script.txt` is written with improved fluency, a hook, and an outro.
2. **Given** a partially-completed refinement (checkpoint present), **When** the script reruns, **Then** it resumes from the last checkpoint paragraph without re-processing completed ones.
3. **Given** no `final_output.txt` exists, **When** the script runs, **Then** it exits with a clear error message.

---

### User Story 2 — Metadata & Title Contest (Priority: P2 — future scope)

As the channel owner, I want Gemini to research high-CTR title writing for my niche, generate many candidate titles, run a tournament to select the 4 best, pit them in pairwise battles that auto-declare the #1 winner, and produce a YouTube title/description/tags bundle — all captured in a ranked leaderboard markdown file.

**Why this priority**: 4 sequential Gemini interactions create a large failure surface. The tournament has the most prompt-engineering risk (bracket logic, <4 candidate edge cases, leaderboard formatting). Deferred to P2 after refinement validates the checkpoint/resume pattern.

**Independent Test**: Running `generate_metadata.py` yields `title_leaderboard.md` (research notes, full candidate list, tournament rounds, pairwise battle results, final ranked #1–#4, declared winner) plus `metadata.json` (title, description, tags).

---

### User Story 3 — Thumbnail Generation (Priority: P2 — future scope)

As the channel owner, I want a thumbnail image generated from the script context and the winning #1 title, with the winning title overlaid as text, ready to upload.

**Why this priority**: Depends on metadata tournament output (winning title). Deferred to P2 alongside the tournament.

**Independent Test**: Running `generate_thumbnail.py` yields `thumbnail.png` with the declared #1 title visible; rerun skips if file already exists and is valid.

---

### Edge Cases

- Gemini safety-block or empty response on any turn → fallback clean-chat + re-frame (pattern from `automate_all.py` lines 673-728).
- No `final_output.txt` present → script exits with clear error.
- Flow image gen fails → fallback to Gemini-direct image path (Principle IX preference, not hard requirement).
- Arabic title overlay rendering (RTL/font) → use an Arabic-capable font in Pillow.

## Requirements

### Functional Requirements

- **FR-001**: System MUST refine `final_output.txt` into `refined_script.txt` via Playwright CDP browser automation against Gemini Web UI. No AI API SDK may be imported.
- **FR-002**: Refinement MUST preserve original meaning and dialect (Egyptian/Khaleeji Arabic per `prompt_phase3.txt`). MUST add a strong opening hook (viewer retention, first 15 seconds) and a compelling outro (CTA: subscribe/comment/next). MUST fix translation artifacts and awkward phrasing.
- **FR-003**: Refinement MUST be paragraph-level, resumable via `refine_checkpoint.json` under `youtube_runs/<Title>/`. A rerun MUST NOT re-process completed paragraphs.
- **FR-004**: The script MUST use `REFINE_MODEL=Pro` from `gemini_model.txt` and MUST use Playwright CDP browser automation (no AI API SDK).
- **FR-005**: The script MUST use resilient selector fallbacks (Principle I) — a prioritized list of locators, not a single hard-coded path. `RESPONSE_SELECTOR` is last-resort only.
- **FR-006**: The script MUST write progress JSON only under `youtube_runs/<Title>/` and MUST delete checkpoint on successful completion.
- **FR-007**: `run_agency.py` MUST wire `refine_script.py` as step 1b (right after `automate_all.py`), with its own `refine` key in `pipeline.json`. Existing runs with `video=True` and no `refine` key MUST auto-skip (treat as complete).
- **FR-008**: The `find_input_box`, `find_send_button`, `wait_for_gemini_response`, `start_clean_gemini_chat`, and `select_gemini_model` helpers MUST be extracted into a shared `gemini_utils.py` module importable by all scripts.

### Key Entities

- **Run Folder** (`youtube_runs/<Title>/`): holds `final_output.txt` (input), `refined_script.txt` (output), `refine_checkpoint.json` (resume state).
- **Refined Paragraph**: {index, original_text, refined_text, status}.
- **Refinement Checkpoint**: {refined_paragraphs: [string], model: string, timestamp: string}.

## Success Criteria

- **SC-001**: Refined script is ≥95% of original length and free of obvious translation artifacts (human spot-check).
- **SC-002**: Refined script contains a visible opening hook (first 2 sentences) and a visible outro CTA (last 2 sentences).
- **SC-003**: Refined script preserves all factual content — no information added or removed.
- **SC-004**: A rerun after interruption resumes from the last checkpoint paragraph without re-processing completed work.
- **SC-005**: `gemini_utils.py` exports all 5 helpers; existing scripts can import them without breaking.

## Assumptions

- Refinement prompt: Gemini receives instructions to (a) improve fluency and dialect consistency (Egyptian/Khaleeji Arabic per `prompt_phase3.txt`), (b) add a strong opening hook that grabs viewer attention in the first 15 seconds, (c) add a compelling outro CTA (subscribe/comment/next video), (d) preserve all factual content and meaning, (e) fix translation artifacts and awkward phrasing.
- `REFINE_MODEL=Pro` — Pro for dialect nuance. Configurable via `gemini_model.txt`.
- `gemini_utils.py` is extracted from existing copy-pasted helpers across `automate_all.py`, `generate_voice.py`, `script_image_generator.py`, `flow_image_generator.py`. No new logic — pure mechanical extraction.
- `run_agency.py` wiring: step 1b after step 1, with `refine` key in `pipeline.json`. Existing runs with `video=True` and no `refine` key auto-skip.
- P2 (metadata tournament + thumbnail) deferred — not in scope for this spec.
