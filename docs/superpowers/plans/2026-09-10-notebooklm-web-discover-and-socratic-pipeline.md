# NotebookLM Web Discover, Deep Research Ingestion & Socratic Curation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate NotebookLM's Web Discover / Deep Research engine to research modern visual prompt engineering, stylized game art aesthetics, and audience retention visual pedagogy across 4 structured queries (2 Fast, 2 Deep). Programmatically select the top 10 recommended high-quality web sources per query, auto-import them directly into the active studio notebook (`https://notebook.google.com/notebook/9c7ccbcc-18ba-4789-9efc-893523ee744f`), and execute 5-round Socratic cross-examination queries against the populated notebook to curate and improve the visual prompting of `flow_image_generator.py`.

**Architecture:** 
1. **Interactive/Headless Browser Session Manager**: Leverages `patchright` persistent contexts with hybrid authentication recovery, handling Google account re-authentication and session storage persistence.
2. **Web Discover & Deep Research Controller** (`src/youtube_automation/prompts/notebooklm_discover.py`): Automates opening the Add Source modal, switching to Web Discover / Search, toggling Fast vs Deep mode, injecting structured research queries via React/Angular-safe typing, and monitoring scan completion with an adaptive deadline watchdog.
3. **Programmatic Top-10 Ingestion & Verification Engine**: Selects the top 10 recommended sources from the results grid, clicks Insert/Add, and enforces count-based increment verification (asserting $\Delta \text{sources} \ge 1$ and total $\le 300$).
4. **Dialectical Socratic Bridge**: Hooks into `SocraticCurationEngine` (`socratic_engine.py`) to execute the 5-round cross-examination protocol against the newly indexed sources, updating `research_cache` and generating grounded 8-part `VisualPrompt` payloads.

**Tech Stack:** Python 3.11, Patchright / Playwright, Pydantic v2, Google NotebookLM Web UI, pytest.

**Spec:** [notebooklm_auth_consolidation_and_socratic_integration_plan.md](file:///C:/Users/Snoozer/.gemini/antigravity-cli/brain/cbcbd149-4e25-4b4f-859c-ccc5e0a5f9fe/notebooklm_auth_consolidation_and_socratic_integration_plan.md) and [notebooklm_socratic_visual_prompt_taxonomy_blueprint.md](file:///C:/Users/Snoozer/.gemini/antigravity-cli/brain/cbcbd149-4e25-4b4f-859c-ccc5e0a5f9fe/notebooklm_socratic_visual_prompt_taxonomy_blueprint.md).

## Global Constraints
- **Zero Cloud SDKs**: Automation must interface strictly via local browser session / CDP loopback using saved authentication state.
- **Source Count Ceiling**: Strict adherence to NotebookLM source capacity (50 sources for standard tier, 300 maximum for studio workspace).
- **PEP 517/518 Compliance**: All new production code resides under `src/youtube_automation/prompts/`.
- **Atomic Operations**: All state changes, caches, and manifest updates must write atomically via temporary files and `os.replace`.
- **Anti-Sycophancy & Evidence-First**: Verification commands and assertions must pass before claiming completion.

---

## 4 Approved Research Queries Spectrum (Visual Prompt Engineering & Aesthetics)

Formatted specifically for NotebookLM Web Discover / Deep Research engine:

| ID | Mode | Focus Domain | Seed Reference | Formatted NotebookLM Discover Query | Expected Ingestion |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `Q1` | **Fast** | Diffusion Prompt Architecture & Control | *Nano Banana prompt engineering* | `"Explore advanced generative AI prompt engineering techniques for diffusion models with a focus on Nano Banana frameworks: structural prompt anatomy, precise lighting terminology, focal length and camera framing syntax, volumetric rendering keywords, and methods to prevent visual artifacts and token bleeding."` | Top 10 prompt engineering articles & documentation |
| `Q2` | **Fast** | Stylized Game Art Direction & Staging | *House of Shinobi game visual & art style* | `"Analyze the visual style and art direction of stylized cinematic games such as House of Shinobi: key art composition, atmospheric chiaroscuro lighting, ink-wash and neo-feudal aesthetics, environmental storytelling props, high-contrast character silhouettes, and color scripting for dramatic visual tension."` | Top 10 game art breakdowns & visual design guides |
| `Q3` | **Deep** | Cognitive Visual Semiotics & Retention | *Explaining visuals for audience retention* | `"Investigate how visual storytelling and graphic explainers maximize audience retention in high-pacing educational videos: cognitive load optimization in visual analogies, effective split-screen comparisons, dynamic infographic staging, prop semiotics, and visual hooks that maintain viewer engagement throughout complex concept explanations."` | Top 10 media psychology & video explainer studies |
| `Q4` | **Deep** | Systematic 8-Part Storyboard Translation | *End-to-End Pipeline Synthesis* | `"Examine systemic methodologies for translating spoken voiceover scripts into sequential visual storyboards for automated video pipelines: maintaining character and style continuity across hundreds of frames, safe-zone spatial composition for lower-third graphics, 8-part prompt schemas, and balancing pedagogical clarity with stylized cinematic illustration."` | Top 10 storyboard production & AI visual direction frameworks |

---

## Task 1: Auth Verification & Interactive Re-Authentication Handshake

**Files:**
- Modify: `src/youtube_automation/prompts/notebooklm_client.py`
- Modify: `C:\Users\Snoozer\.gemini\skills\notebooklm\scripts\browser_utils.py`
- Modify: `C:\Users\Snoozer\.gemini\skills\notebooklm\scripts\auth_manager.py`

**Interfaces:**
- Consumes: `state.json`, Chrome persistent profile directory.
- Produces: `ensure_active_session(page, timeout=30)` ensuring landing URL matches `https://(notebook|notebooklm).google.com/notebook/<uuid>` without account chooser stalls.

- [ ] **Step 1: Write diagnostic test for auth challenge detection**
  Create test verifying that when an account chooser URL (`accounts.google.com/v3/signin/accountchooser`) or "Signed out" status is detected, the session manager intercepts it cleanly rather than failing with element timeouts.

- [ ] **Step 2: Enhance `BrowserFactory` and `auth_manager.py` with Headful Fallback**
  Update `browser_utils.py` and `auth_manager.py` so that if headless launch lands on `accounts.google.com` or indicates signed out status, it can prompt or cleanly launch `--show-browser` / `headless=False` for one-time interactive login completion, dumping refreshed cookies and `sessionStorage` to `state.json`.

- [ ] **Step 3: Verify auth handshake passes against active notebook**
  Run `python -X utf8 C:\Users\Snoozer\.gemini\skills\notebooklm\scripts\auth_manager.py status` and verify authentication is active and the notebook URL resolves directly to the editor canvas.

---

## Task 2: NotebookLM Web Discover & Deep Research Engine (`notebooklm_discover.py`)

**Files:**
- Create: `src/youtube_automation/prompts/notebooklm_discover.py`
- Create: `notebooklm_discover.py` (Root facade shim)
- Test: `tests/unit/test_notebooklm_discover.py`

**Interfaces:**
- Consumes: `BrowserFactory`, `AuthManager`, `ResearchCache`.
- Produces:
  ```python
  class NotebookLMDiscoverEngine:
      def __init__(self, notebook_url: str, headless: bool = True): ...
      def open_discover_modal(self, page: Page) -> bool: ...
      def submit_research_query(self, page: Page, query: str, mode: Literal["fast", "deep"]) -> bool: ...
      def wait_for_scan_completion(self, page: Page, mode: Literal["fast", "deep"], timeout_seconds: int = 180) -> bool: ...
      def select_top_sources(self, page: Page, max_sources: int = 10) -> int: ...
      def commit_import(self, page: Page, expected_increment: int) -> bool: ...
      def execute_batch(self, queries: list[dict[str, Any]]) -> dict[str, Any]: ...
  ```

- [ ] **Step 1: Implement modal navigation and mode toggling**
  - Locate Add Source trigger: `button.add-source-button`, `button:has-text("Add source")`, or `?addSource=true`.
  - Switch to Web Discover / Search tab: `button:has(mat-icon:text-is("search"))`, `button:has-text("Search the web")`, `button:has-text("Web")`, or `button:has-text("Discover")`.
  - Implement Fast vs Deep mode switch (toggling the Fast/Deep pill or segmented button in the NotebookLM UI).

- [ ] **Step 2: Implement query injection and submission**
  - Inject query string using human-like typing or `element.fill()` followed by `Enter` or clicking the search submit button (`button.actions-enter-button`, `button.submit-button`).
  - Capture initial source count before submission (`countSources(page)`).

- [ ] **Step 3: Implement Deep Research scan watchdog**
  - Watchdog states: `SCANNING` $\rightarrow$ `COMPILING` $\rightarrow$ `READY`.
  - Detection anchors:
    - Active progress indicator: `mat-spinner`, `[role="progressbar"]`, `.scanning-indicator`, `.loading-spinner`.
    - Completion sentinel: Results list hydrated with candidate checkboxes (`mat-checkbox`, `[role="checkbox"]`, `.source-card`, `.web-result-item`).
    - Timeout budget: 60s for Fast Research, 180s for Deep Research.
    - Dual diagnostic dump (`.png` + `.html`) on unexpected stall.

- [ ] **Step 4: Implement Top-10 selection and auto-import commit**
  - Query all candidate source checkboxes within the modal: `modal.query_selector_all("mat-checkbox, [role='checkbox'], input[type='checkbox']")`.
  - Programmatically check the first $\min(10, \text{len(candidates)})$ unchecked checkboxes.
  - Click primary Insert/Add button (`button.mdc-button--raised:has-text("Insert")`, `button:has-text("Add to notebook")`).
  - Wait for modal to close (`waitFor({ state: "hidden" })`).
  - Verify source count increases by the imported amount.

---

## Task 3: Unit Tests and Mock DOM Harness

**Files:**
- Create: `tests/unit/test_notebooklm_discover.py`

**Interfaces:**
- Consumes: `NotebookLMDiscoverEngine`, Playwright fake/mock page fixtures.
- Produces: 100% unit test coverage for query execution, watchdog polling, selection math, and error recovery.

- [ ] **Step 1: Test modal opening and tab switching**
  Verify proper selector fallbacks when primary buttons are hidden or animating.

- [ ] **Step 2: Test Fast vs Deep mode selection**
  Verify correct DOM attributes are inspected and toggled for both modes.

- [ ] **Step 3: Test scan watchdog timeout and success states**
  Simulate progressbar disappearance, results list appearance, and timeout handling.

- [ ] **Step 4: Test top-10 checkbox selection logic**
  Verify that exactly $\min(10, N)$ sources are selected, ignoring already-selected items, and verifying insert button activation.

- [ ] **Step 5: Run unit test suite**
  Execute `python -m pytest tests/unit/test_notebooklm_discover.py -v` to ensure zero regressions across all tests.

---

## Task 4: Ingestion Execution Across the 4 Visual Research Queries

**Files:**
- Execute: `python notebooklm_discover.py --notebook-url "https://notebook.google.com/notebook/9c7ccbcc-18ba-4789-9efc-893523ee744f"`

- [ ] **Step 1: Execute Fast Query 1 (Diffusion Prompt Architecture & Control)**
  - Input formatted prompt: `"Explore advanced generative AI prompt engineering techniques for diffusion models with a focus on Nano Banana frameworks: structural prompt anatomy, precise lighting terminology, focal length and camera framing syntax, volumetric rendering keywords, and methods to prevent visual artifacts and token bleeding."`
  - Select and import top 10 sources.
  - Verify notebook source count reaches 10.

- [ ] **Step 2: Execute Fast Query 2 (Stylized Game Art Direction & Staging)**
  - Input formatted prompt: `"Analyze the visual style and art direction of stylized cinematic games such as House of Shinobi: key art composition, atmospheric chiaroscuro lighting, ink-wash and neo-feudal aesthetics, environmental storytelling props, high-contrast character silhouettes, and color scripting for dramatic visual tension."`
  - Select and import top 10 sources.
  - Verify notebook source count reaches 20.

- [ ] **Step 3: Execute Deep Query 1 (Cognitive Visual Semiotics & Retention)**
  - Input formatted prompt: `"Investigate how visual storytelling and graphic explainers maximize audience retention in high-pacing educational videos: cognitive load optimization in visual analogies, effective split-screen comparisons, dynamic infographic staging, prop semiotics, and visual hooks that maintain viewer engagement throughout complex concept explanations."`
  - Wait for Deep Research web scan to complete.
  - Select and import top 10 sources.
  - Verify notebook source count reaches 30.

- [ ] **Step 4: Execute Deep Query 2 (Systematic 8-Part Storyboard Translation)**
  - Input formatted prompt: `"Examine systemic methodologies for translating spoken voiceover scripts into sequential visual storyboards for automated video pipelines: maintaining character and style continuity across hundreds of frames, safe-zone spatial composition for lower-third graphics, 8-part prompt schemas, and balancing pedagogical clarity with stylized cinematic illustration."`
  - Wait for Deep Research web scan to complete.
  - Select and import top 10 sources.
  - Verify notebook source count reaches 40 sources.

---

## Task 5: Post-Ingestion Socratic Cross-Examination against Enriched Notebook

**Files:**
- Execute: `src/youtube_automation/prompts/socratic_engine.py`
- Test: `tests/unit/test_socratic_engine.py`

**Interfaces:**
- Consumes: Enriched active notebook (`al-daheeh-research`, 40 indexed sources), `NotebookLMClient`.
- Produces: Curated 5-round dialectical dossiers and enhanced 8-part `VisualPrompt` specifications stored in `curated_visual_prompts.json`.

- [ ] **Step 1: Execute live 5-round dialectical interrogation on Visual Prompting**
  Run `SocraticCurationEngine` against the 40 ingested sources to calibrate the visual taxonomy:
  1. Round 1 (`Elenchus & Prompt Failure Modes`): Interrogate the failure modes of generic diffusion prompts, token bleeding, and over-crowded negative prompts based on ingested prompt engineering literature.
  2. Round 2 (`Morphology & Stylized Aesthetic`): Extract morphological principles from the House of Shinobi art direction (chiaroscuro, high-contrast silhouettes, neo-feudal props) to define lighting and color presets.
  3. Round 3 (`Antithesis & Visual Clarity`): Formulate counter-proofs against visually flat educational graphics, establishing rules for dynamic focal points and depth separation.
  4. Round 4 (`Semiotics & Cognitive Retention`): Codify audience retention hooks (e.g., Al-Daheeh pedagogical staging, ahwa prop metaphors, bifurcated comparison desks) from cognitive media studies.
  5. Round 5 (`Synthesis & 8-Part Schema`): Assemble verified, reproducible 8-part `VisualPrompt` specifications with exact subject, environment, lighting, color, composition, and negative prompt fields.

- [ ] **Step 2: Verify prompt compliance with strict visual constraints**
  Validate that all generated prompts:
  - Adhere to `VisualPrompt` schema (Subject, Environment, Lighting, Color Palette, Composition/Camera, Render Style, Dynamic Elements, Negative Prompt).
  - Contain zero forbidden subtitle phrases (`subtitles`, `text in lower 20%`, `closed captions`).
  - Integrate seamlessly into `flow_image_generator.py` and `prompt_planner.py`.

- [ ] **Step 3: Update documentation and Continuity Ledger**
  - Update `docs/short-term-plan/CONTINUITY.md` and `docs/product/product.md` with source ingestion counts and curated prompt metrics.
  - Run `python tools/lint_exercises.py` and `python -m pytest tests/unit -v`.

---

## Verification & Acceptance Criteria
1. **Source Ingestion Verification**: NotebookLM active workspace (`9c7ccbcc-18ba-4789-9efc-893523ee744f`) contains 40 imported web sources (10 per query, under the 300 source ceiling).
2. **Deep Research Watchdog Resilience**: Handles scan durations up to 180s without premature timeouts; captures diagnostic snapshots on unexpected DOM anomalies.
3. **Socratic Engine Synthesis**: Successfully runs all 5 dialectical rounds against the enriched notebook, writing cached answers to `research_cache/`.
4. **Code Quality**: Clean lint via `ruff check src/ tests/`, 100% test pass rate via `pytest tests/unit`, and exercise linter clean.
