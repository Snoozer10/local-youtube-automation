# Tasks: Post-Production Automations (P1)

**Input**: Design documents from `/specs/001-video-post-automations/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Implementation Reference**: For complete code blocks, see `docs/superpowers/plans/2026-07-11-prompt-designs-implementation.md`
- T001-T002 → Plan Tasks 2, 6 (prompt text + config edits)
- T004 → Plan Task 1 (gemini_utils.py full code)
- T006-T009 → Plan Task 3 (refine_script.py full code)
- T010 → Plan Task 5 (run_agency.py diffs with line numbers)
- T012-T016 → Plan Task 4 (generate_thumbnail.py full code)

**Tests**: Not requested in feature specification. Skipping test tasks.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configuration and prompt files needed by all subsequent tasks

- [ ] T001 Add `THUMBNAIL_MODEL=Pro` to `gemini_model.txt` after `REFINE_MODEL=Pro`
- [ ] T002 [P] Create refinement prompt in `refine_prompt.txt` with 7 rules (dialect, fluency, rhythm, meaning, TTS, hook, outro) and "UNDERSTOOD" acknowledgment trigger
- [ ] T003 [P] Verify `gemini_model.txt` is in `.gitignore` (Constitution Principle VII)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared Gemini utilities that ALL scripts depend on — MUST complete before any user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Create `gemini_utils.py` by extracting from `automate_all.py`: `find_input_box` (lines 222-249, 5 fallback selectors), `find_send_button` (lines 251-270, 6 fallback selectors), `get_last_response` (lines 272-284), `wait_for_gemini_response` (lines 289-351, growth monitoring + send button state), `start_clean_gemini_chat` (lines 84-135, keyboard shortcut fallback), `select_gemini_model` (lines 406-453, active check + menu filter). Include `RESPONSE_SELECTOR = "model-response div.markdown"` constant. Pure mechanical extraction — no new logic.
- [ ] T005 Verify `gemini_utils.py` imports: `python -c "from gemini_utils import find_input_box, find_send_button, wait_for_gemini_response, start_clean_gemini_chat, select_gemini_model, RESPONSE_SELECTOR; print('OK')"`

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Arabic Script Refinement (Priority: P1) 🎯 MVP

**Goal**: Refine translated Arabic script for fluency, dialect consistency, hook, and outro via Gemini CDP

**Independent Test**: Run `refine_script.py` on a run folder with `final_output.txt` → produces `refined_script.txt` (+ `.docx`) with improved Arabic, visible hook in first paragraph, visible CTA in last paragraph. Rerun resumes from checkpoint.

### Implementation for User Story 1

- [ ] T006 [US1] Create `refine_script.py` main structure: imports (`gemini_utils`, `utils`, `playwright`, `docx`, `json`, `os`, `sys`, `re`, `time`, `glob`), `sys.stdout.reconfigure(encoding='utf-8')`, helper functions (`get_latest_run_folder`, `read_refine_prompt`, `read_final_output`, `split_paragraphs`, `load_checkpoint`, `save_checkpoint`, `delete_checkpoint`, `save_refined_script`, `is_safety_blocked`)
- [ ] T007 [US1] Implement `setup_refinement_session(page, model_name)` in `refine_script.py`: calls `start_clean_gemini_chat`, `select_gemini_model`, reads `refine_prompt.txt`, sends via `find_input_box` + `find_send_button`, waits via `wait_for_gemini_response` with `RESPONSE_SELECTOR`, checks for "UNDERSTOOD"/"جاهز"/"مستعد" acknowledgment
- [ ] T008 [US1] Implement `refine_paragraph(page, paragraph_text, index, total)` in `refine_script.py`: formats message as `"Refine paragraph {i} of {total}..."`, sends via input box, waits for response, checks `is_safety_blocked`, returns refined text
- [ ] T009 [US1] Implement `main()` in `refine_script.py`: read config (`REFINE_MODEL`, `FAILOVER_RETRY_LIMIT`, `SWITCH_ACCOUNTS_ENABLED`, `BROWSER_TYPE`, `ACTIVE_PROFILE_INDEX`), connect to CDP, load checkpoint, loop paragraphs with setup-on-first-run, retry logic with account rotation via `rotate_profile_index()` + `kill_cdp_chrome()` + `launch_browser_with_profile()`, save checkpoint after each paragraph, delete checkpoint on completion, save `refined_script.txt` + `.docx`
- [ ] T010 [US1] Wire `refine_script.py` into `run_agency.py`: add `"refine": False` to `default_state` in `get_pipeline_state()` (line 61), add `{"key": "refine", "script": "refine_script.py", "desc": "Phase 1b: Arabic Script Refinement"}` as first entry in `folder_steps` (line 136), add backward-compat skip `if "refine" not in state: state["refine"] = True` after `state = get_pipeline_state(folder)` (line 124)
- [ ] T011 [US1] Verify syntax: `python -c "import py_compile; py_compile.compile('refine_script.py', doraise=True); py_compile.compile('run_agency.py', doraise=True); print('Syntax OK')"`

**Checkpoint**: User Story 1 complete — script refinement works end-to-end

---

## Phase 4: User Story 2 — Thumbnail Generation (Priority: P2)

**Goal**: Generate 3-5 thumbnail variants with Nano Banana Pro prompts and Gemini self-critique, pick top 2 winners

**Independent Test**: Run `generate_thumbnail.py` → produces `thumbnails/variant_1.png` + `variant_2.png`, `thumbnail_prompts.json`, `thumbnail_critique.json`. Rerun skips if thumbnails exist.

### Implementation for User Story 2

- [ ] T012 [P] [US2] Create `generate_thumbnail.py` constants: `THUMBNAIL_COUNT = 5`, `TOP_N = 2`, `THUMBNAIL_SETUP_PROMPT` (concept extraction prompt with EMOTION/SCENE/TEXT_OVERLAY/STYLE fields, JSON array output), `CRITIQUE_PROMPT_TEMPLATE` (scoring with click_appeal/emotional_impact/visual_clarity, top N selection, improvement suggestions)
- [ ] T013 [P] [US2] Implement `build_nano_banana_prompt(concept, index)` in `generate_thumbnail.py`: map style → camera body/lens/lighting/mood (cinematic=Sony A7III/85mm/golden hour, dramatic=Canon EOS R5/50mm/spotlight, mysterious=Hasselblad X1D/45mm/low-key, confrontational=Sony A7III/35mm/hard flash, emotional=Kodak Portra 400/50mm/soft diffused), build structured prompt with subject/camera_specifications/environment/mood/text_overlay/negative/aspect_ratio/resolution
- [ ] T014 [US2] Implement `extract_json_from_response(text)` and `send_and_wait(page, message, timeout)` helpers in `generate_thumbnail.py`: JSON extraction from markdown code blocks, generic send-message-wait-for-response using `gemini_utils` helpers
- [ ] T015 [US2] Implement `generate_images_via_gemini(page, prompts, output_dir)` in `generate_thumbnail.py`: loop prompts, send to Gemini, hover over generated images, find download button (4 fallback selectors), `page.expect_download()` to save, fallback to base64 extraction from response text
- [ ] T016 [US2] Implement `main()` in `generate_thumbnail.py`: read config (`THUMBNAIL_MODEL` with `REFINE_MODEL` fallback), connect to CDP, Phase 1 (concept extraction via `THUMBNAIL_SETUP_PROMPT` + script excerpt), Phase 2 (build Nano Banana Pro prompts via `build_nano_banana_prompt`), Phase 3 (self-critique via `CRITIQUE_PROMPT_TEMPLATE`), Phase 4 (generate images for top 2 winners), save all artifacts to `youtube_runs/<Title>/thumbnails/`
- [ ] T017 [US2] Verify syntax: `python -c "import py_compile; py_compile.compile('generate_thumbnail.py', doraise=True); print('Syntax OK')"`

**Checkpoint**: User Story 2 complete — thumbnail pipeline works end-to-end

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and validation

- [ ] T018 Run quickstart.md validation: test all 5 scenarios (refinement, gemini utils import, thumbnails, pipeline wiring, config readability)
- [ ] T019 Update `AGENTS.md` to document `gemini_utils.py` as shared module and `refine_script.py` / `generate_thumbnail.py` as pipeline steps

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational (Phase 2)
- **US2 (Phase 4)**: Depends on Foundational (Phase 2) — can run in parallel with US1
- **Polish (Phase 5)**: Depends on US1 + US2 completion

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — No dependencies on other stories
- **US2 (P2)**: Can start after Foundational — Independent of US1

### Within Each User Story

- Models/data structures before services/logic
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- T001, T002, T003 (Setup) — all parallelizable
- T006, T007, T008, T009 (US1 implementation) — sequential within story
- T012, T013 (US2 constants + prompt builder) — parallelizable
- US1 and US2 can be worked on in parallel after Foundational phase

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T005) — CRITICAL
3. Complete Phase 3: US1 (T006-T011)
4. **STOP and VALIDATE**: Run `refine_script.py` on a test video
5. Pipeline wiring confirmed working via `run_agency.py`

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Test independently → MVP (script refinement works!)
3. Add US2 → Test independently → Full P1 scope delivered
4. Each story adds value without breaking previous stories

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Tests not requested — skipping test tasks per spec
- Constitution Principle VII: `gemini_model.txt` must be in `.gitignore` (T003)
