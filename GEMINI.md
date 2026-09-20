---
project_name: "youtube-automation-pipeline"
version: "4.4.0"
tech_stack:
  - "python"
  - "playwright"
  - "faster-whisper"
  - "ffmpeg"
  - "audacity"
  - "pydantic"
rules:
  - "qsv-lookahead-zero"
  - "nv12-hardware-format"
  - "cdp-loopback-binding"
  - "timeline-canonical-truth"
  - "zero-cloud-sdks"
  - "atomic-disk-writes"
exclude_paths:
  - "youtube_runs"
  - "venv"
  - "legacy_and_utilities"
  - "assets"
  - ".agents"
  - "debug_snapshots"
  - "docs/implementation_plans"
  - "docs/security_analysis"
last_indexed: "2026-09-09"
generator: "gemini-context-engineer/v4.0.0"
---

# Project Context: youtube-automation-pipeline

## 🎯 Project Overview
Autonomous, broadcast-grade educational YouTube studio producing high-retention explainer videos powered by a dynamic multi-niche engine (`GENERAL_EXPLAINER`, `SCIENCE_TECH`, `FINANCE_ECONOMICS`, `HISTORY_GEOPOLITICS`, `PHILOSOPHY_ESSAY`, `CULTURE_COMEDY`). Transcreates transcripts with engaging conversational dialect and sentence cadence, synthesizes neural voiceovers with multi-account quota failover, applies Audacity DSP via Win32 Named Pipes, aligns speech via Faster-Whisper, orchestrates Gemini prompts via CDP loopback, harvests visuals via Google Flow with Two-Substrate Studio grounds, and renders broadcast video with procedural Ken Burns kinematics via FFmpeg. Features PEP 517/518 packages in `src/youtube_automation/`, backward-compatible `_FacadeProxy` root shims, and pre-flight diagnostic drills in `exercises/`.

## Adaptive multi-channel production: current opt-in contract

- `adaptive_production.py` and `src/youtube_automation/production/` own the staged adaptive path. [Plan](tasks/adaptive-visual-plan.md), [checklist](tasks/adaptive-visual-tasks.md), [usage](tasks/adaptive-visual-usage.md).
- Explicit saved-channel identity precedes raw-script analysis, restructuring, translation and refinement. Topics cannot replace channel audience, language/dialect, voice, host policy or style. ASR uses the channel language code or audio detection.
- Adaptive shot plans replace legacy roadmap camera cycles. They reference canonical narration spans with contiguous integer frames; they never rewrite speech timing. Holds are valid, motion is selective, and typography/annotations are rendered locally.
- Do not send framing coordinate literals to image generation. No automatic decorative telemetry or literal idiom props. Exact references and complete validated assets are required; missing references block rather than becoming independent generations.
- Accepted asset copies and hashes outlive provider scratch paths. Full-frame background OCR must actually run. Technical verification is separate from human editorial approval.
- Browser and encoder leases fence short publication operations. Immutable final filenames precede atomic activation pointers; byte-verified clip caches include render/tool recipes. These are primitives, not a finished durable stage scheduler; legacy/audio tools do not all participate.
- A master requires a current preview and explicit approval bound to plan, assets, audio and render settings. `active_master.json` identifies the accepted file. Three reviewed 60–90 second pilots precede full episodes.
- `run_agency.py` excludes adaptive runs. Use the staged CLI until the remaining scheduler/audio ownership/reference restoration gates pass. Live UI behavior, Arabic readability, crop semantics and artistic quality are not established by offline tests.
- No DNS, network-adapter or system network configuration changes are part of this workflow.

## 🏗️ Architecture & Component Mapping

```text
[Phase 1-2 Transcreation & Polish] ──► [Phase 3-5 TTS & Audacity DSP]
                  │                                   │
[Phase 8 Timeline SSOT & Fix]      ◄── [Phase 6-7 Whisper ASR & Spellcheck]
                  │
[Phase 9-10 Storyboard & Flow Visuals] ──► [Phase 11-13 Video & Thumbnail]
```

| Domain / Subsystem | Package Location | Facade / Entrypoint | Key Responsibility |
| :--- | :--- | :--- | :--- |
| Audio Synthesis & DSP | [audio/](src/youtube_automation/audio/) | [generate_voice](generate_voice.py), [audacity](automate_audacity.py), [stitch](stitch_chapters.py) | AI Studio TTS, Win32 Named Pipes DSP, lossless WAV stitch |
| Speech & Lexical Sync | [speech/](src/youtube_automation/speech/) | [transcribe](faster_whisper_transcribe_audio.py), [spellcheck](correct_transcript_spelling.py) | Faster-Whisper ASR, Silero VAD pause snap, monotonic spellcheck |
| Timeline SSOT | [timeline/](src/youtube_automation/timeline/) | [timeline_engine](timeline_engine.py), [fix_timestamps](fix_timestamps.py) | Canonical timeline.json, SHA-256 sidecars, timestamp repair |
| Visual Generation | [visuals/](src/youtube_automation/visuals/) | [flow_generator](flow_image_generator.py), [text_gate](text_gate.py) | Google Flow UI automation, continuity studio, OCR text gate (upper-80% safe zone) |
| Hardware Video Render | [video/](src/youtube_automation/video/) | [compile_video](compile_video.py) | FFmpeg compositor, QSV (lookahead=0, nv12), Ken Burns, ASS |
| Browser CDP Engine | [browser/](src/youtube_automation/browser/) | [cdp_client](src/youtube_automation/browser/cdp_client.py), [gemini_utils](gemini_utils.py) | Port 9222 loopback binding, tab hygiene, Gemini web controls |
| Core Primitives | [core/](src/youtube_automation/core/) | [utils](utils.py) | Atomic disk writes, process lifecycle, profile rotation |
| Prompt & NLP Engines | [nlp/](src/youtube_automation/nlp/), [prompts/](src/youtube_automation/prompts/) | [json_sanitizer](json_sanitizer.py), [validator](validator.py) | Multi-tier LLM JSON repair, 8-part prompt validation |
| Adaptive Production | [production/](src/youtube_automation/production/) | [adaptive_production](adaptive_production.py) | Channel briefs, editorial shots, asset receipts, local render and review gates |
| Pipeline Orchestrator | [orchestrator/](src/youtube_automation/orchestrator/) | [run_agency](run_agency.py), [roadmap](roadmap_orchestrator.py) | Batch scheduling, 25-row paged visual storyboard, 5-shot scale cycle |
| Pedagogy & Diagnostics | [exercises/](exercises/) | [lint_exercises](tools/lint_exercises.py), [run.bat](run.bat) | 3-tier pedagogy drills (01-audio, 03-browser, 05-video) |

> **Visual Engines Architecture & Ownership**:
> - `flow_image_generator.py` (and `src/youtube_automation/visuals/flow_generator.py`) is the primary visual engine. Prompts are governed by `roadmap_orchestrator.py`, `prompt_planner.py`, and `asset_studio.py` (`FLOW_ASSET_PRESETS`, `STYLE_DNA_TEXT`).
> - `script_image_generator.py` is the legacy alternative generator, exclusively owning `prompts/visual_style.txt` and `prompts/visuals_plan.txt`.

### Domain Lexicon & Ubiquitous Language
| Term | Canonical Meaning | Forbidden Synonyms / Overloaded Usage |
| :--- | :--- | :--- |
| `Timeline` | SSOT (`timeline.json`) via `timeline_engine.py` | "Word list", "Subtitles" |
| `VisualPrompt` | 8-part diffusion schema conforming to ADR 0004 | "Image prompt", "Description" |
| `Ken Burns` | Dynamic smoothstep pan-and-zoom in FFmpeg | "Zoom effect", "Slide" |
| `CDP Session` | Chrome DevTools Protocol bound to 127.0.0.1:9222 | "Browser tab", "Selenium" |
| `Transcreation` | 30/70 Egyptian/Khaleeji educational rewrite | "Machine translation" |
| `Facade Shim` | Root proxy (`_FacadeProxy`) syncing monkeypatches | "Wrapper hack", "Mock" |
| `Pre-flight Drill` | Diagnostic test (`@pytest.mark.drill`) for hardware | "Smoke test", "Dummy" |
| `Pedagogy Scaffold` | 3-tier structure (explainer/problem/solution) | "Sample code", "Sandbox" |

### Architectural Health & Deep Modules
| Module / Subtree | Interface Count | Implementation LOC | Leverage | Classification |
| :--- | :--- | :--- | :--- | :--- |
| [src/youtube_automation/timeline/fix_timestamps.py](src/youtube_automation/timeline/fix_timestamps.py) | 1 | 93 | 93.0 | Deep Module |
| [src/youtube_automation/nlp/json_sanitizer.py](src/youtube_automation/nlp/json_sanitizer.py) | 2 | 137 | 68.5 | Deep Module |
| [src/youtube_automation/speech/spelling_corrector.py](src/youtube_automation/speech/spelling_corrector.py) | 6 | 282 | 47.0 | Deep Module |
| [src/youtube_automation/video/ken_burns.py](src/youtube_automation/video/ken_burns.py) | 4 | 181 | 45.25 | Deep Module |
| [src/youtube_automation/visuals/text_gate.py](src/youtube_automation/visuals/text_gate.py) | 6 | 236 | 39.33 | Deep Module |

### Child Context Index
| Subtree / Scope | Context Path | Ownership & Purpose |
| :--- | :--- | :--- |
| `src/youtube_automation/` | [AGENTS.md](AGENTS.md) | Modular domain packages conforming to PEP 517/518 |
| `exercises/` | [AGENTS.md](AGENTS.md) | Pedagogy scaffold and pre-flight diagnostic drills |
| `.agents/skills/gemini-context-engineer/` | [.agents/skills/gemini-context-engineer/GEMINI.md](.agents/skills/gemini-context-engineer/GEMINI.md) | Context engineer skill specification |

## 🛑 Mandatory Engineering Constraints

### FerroxLabs Cognitive Non-Negotiables
- **Anti-Sycophancy**: Disagree with false user premises; never offer performative agreement.
- **Surgical Changes Only**: Modify strictly what is requested; avoid unrequested style churn.
- **Plausibility Is Not Correctness**: Untested code is assumed broken; verify with compiler, linter, or tests.

### Directives on User Examples & Open Scopes

1. **Illustrative Baselines:** When the user provides examples, treat them as directional seeds rather than an exhaustive or binding list.
2. **Critical Evaluation:** Do not assume the user's proposed tools, libraries, or patterns are optimal. If a suggestion introduces anti-patterns, latency, or unnecessary complexity, explicitly challenge the premise and suggest the superior industry standard.
3. **Controlled Exploration:** When the user indicates an open-ended goal, identify the governing category or core objective. Propose the top 2–3 best-fit solutions ranked by reliability and simplicity, clearly stating the trade-offs of each.
4. **No Silent Drift:** Never use open-ended prompts as permission to add unrequested dependencies or modify out-of-scope files. Expand the concept, but keep the operational blast radius strictly bounded.

### Technical & Environmental Invariants
- **Intel QSV Compositing**: `QSV_LOOKAHEAD=0` (no lookahead with sw frames); `format=nv12` filter required for `h264_qsv` (yuv420p crashes); CFR frame math (`round(dur * fps)`); CLI >1000 chars written to `-filter_complex_script`.
- **Playwright CDP**: Bind strictly `127.0.0.1:9222`; kill port PID via `utils.kill_cdp_chrome`; prompt injection via `keyboard.insert_text` (fires React SyntheticEvents); turn handshake (stop button gone + 3x 500ms stable); 25-row roadmap pages (`ROADMAP_WINDOW_SIZE=25`). Angular CDK overlay menus portal to `div.cdk-overlay-container` (NOT children of trigger button); always dismiss `cdk-overlay-backdrop` before pointer interaction. Card-spawn handshake: record card count before submit, wait ≤20s for count increase before entering generation watchdog.
- **Flow Generation Watchdog**: Scoped to `active_card` (last card only); 120s stall ceiling → reload + re-inject; 360s hard ceiling → dump diagnostics + rotate account; error regex MUST include `reached your usage limit|you have not been charged`; always dump paired `.png` + `.html` on any stall.
- **Data & Subprocess Safety**: Canonical `timeline.json` SSOT; zero cloud SDKs (local CDP loopback only); subprocess args as `list` with `shell=False`; UTF-8 streams (`sys.stdout.reconfigure`); atomic disk writes (`NamedTemporaryFile` + `os.replace` + `fsync`).

## 🛠️ Common Workflows & CLI Commands
- Run unit test suite: `python -m pytest tests/unit -v`
- Run full test suite: `python -m pytest tests/ -v`
- Run hardware/daemon pre-flight drills: `python -m pytest exercises/ -v -m drill`
- Validate exercise pedagogy scaffold: `python tools/lint_exercises.py`
- Run pre-flight drills via wrapper: `run.bat test-drills`
- Run exercise linter via wrapper: `run.bat lint-exercises`
- Code formatting & linting: `ruff check src/ exercises/ tools/ --fix`
- Static type checking: `mypy src/`
- Run supervisor batch: `python run_agency.py`
- Run individual phases: `python automate_all.py` / `python compile_video.py`

### OpenCode Multi-Agent Orchestration & Quality Gates
- **Coordinator (Tier 1)**: Claude 3.7 Sonnet / Gemini Pro — spec design, refactor strategy.
- **Executor (Tier 2)**: Gemini Flash / DeepSeek V3 — fast TDD, linting, regression tests.
- **Quality Gates**: Unit tests green (`python -m pytest tests/unit`), clean lint (`ruff check`), exercise lint clean, drills green.

## 🔄 Active Workstreams & Verification Status
| ID | Workstream Slice | Status | Blocked By | Proof Command |
| :--- | :--- | :--- | :--- | :--- |
| `#1` | Audio DSP & Lossless Stitching | Done | - | `python -m pytest tests/unit/test_audacity_pipe_protocol.py` |
| `#2` | ASR Alignment & Timeline Sync | Done | `#1` | `python -m pytest tests/unit/test_timeline.py` |
| `#3` | Paged Storyboard & Prompts | Done | `#2` | `python -m pytest tests/unit/test_roadmap_orchestrator.py` |
| `#4` | Flow Visuals & Text Gate | Done | `#3` | `python -m pytest tests/unit/test_text_gate.py` |
| `#5` | Video Compositing & Ken Burns | Done | `#4` | `python -m pytest tests/unit/test_encoder.py` |
| `#6` | Post-Encode Validation & Sync | Done | `#5` | `python -m pytest tests/unit/test_post_encode_validation.py` |
| `#7` | Pedagogy Scaffold & Drills | Done | `#6` | `python tools/lint_exercises.py && python -m pytest exercises/ -v -m drill` |
| `#8` | DOX Docs & Quality Gate Audit | Done | `#7` | `python tools/lint_exercises.py && python -m pytest tests/ -v` |
| `#9` | Repo Cleanup & Consolidation | Done | `#8` | `python tools/lint_exercises.py && python -m pytest tests/ -v` |
| `#10` | Flow Generator Hardening v2 | Done | `#9` | `python -m py_compile src/youtube_automation/visuals/flow_generator.py && python -m pytest exercises/03-browser-cdp/03.03-flow-hydration-recovery/solution/test_exercise.py -v` |
| `#11` | Full Production Run (293 frames) | Done | `#10` | 293 PNGs in `generated_images/` + `youtube_ready_video.mp4` (1334.50s, 0.01s A/V drift) |
| `#12` | Creative Refinement (Plan v4) | Done | `#11` | `python tools/lint_exercises.py && python -m pytest tests/unit -v` (414 passed) |
| `#13` | NotebookLM Discover & Socratic Curation | Done | `#12` | `python -m pytest tests/unit/test_notebooklm_discover.py tests/unit/test_socratic_engine.py -v` (424 passed) |
| `#14` | Socratic Prompt Operationalization & Canary Benchmark | Done | `#13` | `python tools/lint_exercises.py && python -m pytest tests/unit -v` (445 passed) |
| `#16` | Socratic Visual Studio Phase 2 Rollout (Chunk 1: Frames 1-50) | Done | `#15` | `python tools/run_canary_benchmark.py --frames 1-50 --output-dir "youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/chunk_1_images"` (50/50 PASS, 0 collisions) |
| `#17` | Socratic Visual Studio Phase 2 Rollout (Chunk 2: Frames 51-100) | Done | `#16` | `python tools/run_canary_benchmark.py --frames 51-100 --output-dir "youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/chunk_2_images"` (50/50 PASS, 0 collisions) |
| `#18` | Socratic Visual Studio Phase 2 Rollout (Chunk 3: Frames 101-150) | Done | `#17` | `python tools/run_canary_benchmark.py --frames 101-150 --output-dir "youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/chunk_3_images"` (50/50 PASS, 0 collisions) |
| `#19` | Socratic Visual Studio Phase 2 Rollout (Chunk 4: Frames 151-200) | Done | `#18` | `python tools/run_canary_benchmark.py --frames 151-200 --output-dir "youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/chunk_4_images"` (50/50 PASS, 0 collisions) |
| `#20` | Socratic Visual Studio Phase 2 Rollout (Chunk 5: Frames 201-250) | Done | `#19` | `python tools/run_canary_benchmark.py --frames 201-250 --output-dir "youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/chunk_5_images"` (50/50 PASS, 0 collisions) |
| `#21` | Socratic Visual Studio Phase 2 Rollout (Chunk 6: Frames 251-293) | Done | `#20` | `python tools/run_canary_benchmark.py --frames 251-293 --output-dir "youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/chunk_6_images"` (43/43 PASS, 0 collisions) |
| `#22` | Socratic Visual Studio Phase 2 Rollout (Full Episode Master Studio: 293/293) | Done | `#21` | All 6 chunks (Frames 1-293) complete on disk, 293/293 unique SHA-256 hashes, 100% OCR text gate pass |
| `#23` | Socratic Master Video Compilation (1080p, 22.24m) | Done | `#22` | `python compile_video.py` (232.62 MB, 1334.50s, 0.01s A/V drift, 1080p & 720p proxies verified) |
| `#24` | Studio Viewer Baseline Collision Fix & Chunk Scaffolding | Done | `#23` | `python -m pytest tests/unit/test_viewer_generator.py -v` (11/11 viewers regenerated & verified) |
| `#25` | Long-Form 16:9 Broadcast Refactoring (Tiers 1, 2, 3) | Done | `#24` | `python -m pytest tests/unit -v` (500/500 PASS), `python tools/lint_exercises.py` (35/35 PASS), `compile_video.py` (40,035 frames, 1334.50s, 0.01s drift) |
| `#26` | Option B Disambiguated 7-Frame Rollout | Done | `#25` | `python tools/run_canary_benchmark.py --force-overwrite --frames 16,18,20,33,34,44,49 --output-dir "youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/canary_disambiguated_7"` (7/7 PASS, 0 collisions, 0 text leaks) |
| `#27` | Phase 7B Full Visual Production (What Do Animals Think Of Humans) | Done | `#26` | 139 PNGs in `generated_images/` (100% complete, 139 unique SHA-256 hashes, 0 collisions, `studio_viewer.html` generated, 520 tests passing) |

| `#28` | Hardware Video Compilation (What Do Animals Think Of Humans) | Done | `#27` | `compile_video.py` (161.4 MB master, 1080p proxy 86.1 MB, 720p proxy 43.7 MB, 602.27s duration, 0.00s A/V drift, 211 synchronized clips) |
| `#29` | High-CTR YouTube Thumbnail Packaging (What Do Animals Think Of Humans) | Done | `#28` | `python generate_thumbnail.py` (2 winning variants on disk, 100% OCR text gate pass, MSER collision self-healing verified) |
| `#30` | Adaptive Multi-Channel Prompt Engineering & Loader Core | Done | `#29` | `python -m pytest tests/unit/test_prompt_loader.py tests/unit/test_prompt_contracts.py -v` (571/571 PASS, 35/35 drills clean) |

### Known Failure Modes & Project Learnings
- [LEARNING-001]: NEVER enable `look_ahead` on Intel QSV (`h264_qsv`) with sw-decoded frames; ALWAYS enforce `QSV_LOOKAHEAD=0`.
- [LEARNING-002]: NEVER feed `yuv420p` to `h264_qsv` (driver requires `nv12`); ALWAYS append `format=nv12` to filtergraph.
- [LEARNING-003]: NEVER assume Gemini SPA DOM mounts immediately; ALWAYS poll with 8s deadline & soft-fail fallback.
- [LEARNING-004]: NEVER use cloud AI SDKs; ALWAYS automate via Playwright CDP loopback (`127.0.0.1:9222`).
- [LEARNING-005]: NEVER run bare `pytest`; ALWAYS run `python -m pytest` so `tests/conftest.py` configures `sys.path`.
- [LEARNING-006]: NEVER use plain re-export shims; ALWAYS use `_FacadeProxy` with bidirectional monkeypatching sync.
- [LEARNING-007]: NEVER omit trailing commas in FFmpeg argument lists; ALWAYS assert explicit token boundaries.
- [LEARNING-008]: NEVER use `time.sleep()` inside Playwright polling loops; ALWAYS use `page.wait_for_timeout(ms)` to keep the CDP WebSocket transport pumped.
- [LEARNING-009]: NEVER query Angular CDK menu items as children of the trigger button; ALWAYS query `div.cdk-overlay-container [role='menuitem'], div.cdk-overlay-container button` — CDK portals menus to the document root.
- [LEARNING-010]: NEVER use a generic error regex in the generation watchdog; ALWAYS include `reached your usage limit|you have not been charged` — Flow quota errors render as card text, not `[role='alert']`, causing 120s silent stalls if undetected.
- [LEARNING-011]: NEVER check for progressbar immediately after pressing Enter; ALWAYS use a Card-Spawn Handshake (record pre-submit card count, poll ≤20s for count increase) to distinguish queue latency from true stall — prevents false double-submission re-triggers.
- [LEARNING-012]: NEVER scope `.animate-pulse` / skeleton checks globally; ALWAYS scope to `active_card` (last card locator) to avoid false "still loading" signals from historical generation cards re-animating on scroll.
- [LEARNING-013]: NEVER attempt to query a modal-closing element while submitting in NotebookLM Web Discover; ALWAYS monitor the Sources panel where candidate cards stage for `+ Import` and verify count increments atomically.
- [LEARNING-014]: ALWAYS use `-X utf8` and set `PYTHONIOENCODING=utf-8` on Windows when invoking subprocess runners to avoid charmap codec `UnicodeEncodeError` on emoji/Unicode status logs.
- [LEARNING-015]: NEVER rely on in-page canvas fallbacks (`ctx.drawImage`) when extracting cross-origin images in Google Flow; ALWAYS prioritize Playwright's `page.request.get()` network stream (inheriting browser session cookies and bypassing CORS), and validate that `img.getextrema()` is not all zeros to reject blank/tainted canvas artifacts.
- [LEARNING-016]: NEVER match card-level transient errors (`تعذَّر إكمال المعالجة`, `failed to generate`) globally across the page DOM in Flow; ALWAYS scope card checks to `active_card` via `target_locator` to prevent historical failed tiles from causing false-positive quota crashes on subsequent frames. Global checks must strictly target fatal account strings (`الحدّ الأقصى للاستخدام`, `reached your usage limit`).
- [LEARNING-017]: NEVER sort candidate images with `candidates[-1]` in Google Flow; Google Flow prepends new cards to the TOP of the feed (lowest `y`). ALWAYS sort ascending by `y` and select `candidates[0]` to avoid selecting stale historical cards at the bottom of the feed.
- [LEARNING-018]: ALWAYS dismiss sticky Google cookie consent banners (`.glue-cookie-notification-bar__accept`) before prompt submission; otherwise the banner overlays the bottom input bar and intercepts pointer events.
- [LEARNING-019]: NEVER extract bare `subject_details` fragments for Mode A prompts in dual-mode builders; ALWAYS call `enhance_diffusion_prompt(raw_dict)` to guarantee the full 2D vector style DNA, isolated white canvas directive (`#FFFFFF`), and negative token filters are submitted to the diffusion model.
- [LEARNING-020]: NEVER submit raw character constant identifiers (e.g. `CHARACTER_SKEPTIC_ABO_HMEED`) in diffusion prompts; ALWAYS expand them via `expand_asset_tokens()` into explicit 2D cartoon animation descriptions to prevent models from generating photorealistic street/person photos from token strings.
- [LEARNING-021]: In Google Flow, every generation prompt produces a pair of 2 candidate variants side-by-side in the top row (`y: 59`, `x: 32` and `x: 680.5`). When scraping the newly rendered image, ALWAYS sort ascending by `(y, x)` and pick `candidates[0]`, ensuring `pre_image_srcs` captures all visible tiles to avoid selecting unconsumed variant siblings on subsequent frames.
- [LEARNING-022]: In Google Flow's Angular CDK drawer, character asset lists are virtualized (cards unmount outside active scroll window) and clicking an asset card can auto-dismiss the overlay while directly attaching the chip to the prompt bar. ALWAYS pump bidirectional wheel scrolls (-600, +600) to mount assets, and verify destination chip presence before and after clicking char_btn rather than strictly waiting for a secondary detail confirmation button.
- [LEARNING-023]: In Chrome DevTools Protocol tab selection, NEVER use broad parent domains (e.g. "google.com") to locate application tabs; ALWAYS match specific subdomains ("flow.google", "/flow") to avoid inadvertently binding to sibling Google tabs (gemini.google.com, aistudio.google.com).
- [LEARNING-024]: In Google Flow, NEVER inject prompts while conversational "Agent" mode is active; ALWAYS ensure Agent mode is toggled OFF (dismiss agent side-panel and ensure the Agent pill button is inactive/grey) to prevent conversational video approval modals from intercepting direct image generation.
- [LEARNING-025]: In batch image generation runners, NEVER allow account quota saturation ("الحدّ الأقصى للاستخدام") to cause cascading per-frame reload attempt failures across pending frames; ALWAYS halt the batch immediately or invoke multi-account profile rotation (rotate_profile_index), preserving existing completed frames on disk.
- [LEARNING-026]: Legacy preset workflow only (adaptive reference edits must block if the exact accepted reference cannot be restored): in multi-account rotation architectures, Google Flow Character Presets are strictly account- and project-scoped; ALWAYS implement autonomous fallback to Mode A Master Setup with expanded character visual DNA (expand_asset_tokens) when summon_character_chip reports FAILED/SKIPPED.
- [LEARNING-027]: In comparison viewer generators, NEVER hardcode baseline image URLs (e.g. `../generated_images/{fname}`); when videos are compiled, `generated_images/` contains consolidated candidate assets while baselines reside in `generated_images_baseline/`. ALWAYS dynamically resolve `generated_images_baseline/` priority and compute relative image links via `os.path.relpath(target, html_dir)`.
- [LEARNING-028]: In procedural Ken Burns linear push drift filters, NEVER use unconstrained interpolation like `((on-1)/(d-1))`; ALWAYS use zero-safe clamped evaluation `min(1.03, 1.0 + 0.03 * (clip(on, 0, N) / max(1, N)))` to prevent fatal negative pops at `on=0` and division-by-zero crashes when duration `d=1`.
- [LEARNING-029]: Keep static holds genuinely static, including long and single-frame clips. Camera movements and cuts must be explicit editorial decisions; do not add automatic reaction punches or a fixed upper-third focal target in adaptive mode. Preserve integer frame budgets and encoder invariants.
- [LEARNING-030]: Generated backgrounds contain no typography. Diagrams require a narrative purpose and supported evidence; never add compulsory decorative telemetry. Render labels, arrows and highlights locally and inspect Arabic shaping in the actual preview.
- [LEARNING-031]: Legacy feed attachment only (adaptive mode uses receipt URL plus pixel identity): in Google Flow Mode B previous image attachment, NEVER slice primary cards from the bottom of the feed (`primary_cards[-count:]`); Google Flow prepends newly generated cards to the top of the feed (`lowest Y`). ALWAYS slice from the top (`primary_cards[:count]`) and reverse to attach true chronological previous frames.
- [LEARNING-032]: In Gemini web Markdown table parsing, NEVER assume table rows are pipe-delimited (`|`); Gemini SPA renders tables into native HTML `<table>` elements where browser `innerText` converts cells to tab-delimited (`\t`) strings. ALWAYS support both `|` and `\t` row delimiters in table line parsers.
- [LEARNING-033]: In Gemini web prompt construction for text-only tasks (e.g. storyboards and roadmaps), NEVER include diffusion model hex codes, pixel coordinates (`X: 180 to 1740`), or render specs; Gemini web's multi-modal safety filter misinterprets them as image generation/manipulation requests and responds with refusal cards ("I am just a text-based AI and cannot help with that." / "I seem to be encountering an error.").
- [LEARNING-034]: Unresponsive Chrome renderers can hang CDP attachment. Use bounded connection timeouts and clean up only pipeline-owned tabs; do not prune unrelated user tabs. Broader legacy cleanup ownership remains tracked work.
- [LEARNING-035]: In high-volume Google Flow image generation batches (100+ frames), NEVER treat transient card-spawn queue timeouts (>45s) as fatal account quota exhaustion; ALWAYS log as `TRANSIENT_ERROR`, preserve active account profiles, recycle the workspace into a fresh project, and execute an automated single-pass gap backfill sweep (`if os.path.exists(save_path): continue`) after the main sequential pass.
- [LEARNING-036]: In AI thumbnail generation, NEVER ingest raw diffusion outputs without an automated OCR text collision check; ALWAYS verify bitmaps via `check_text_collision`, purge contaminated images on Attempt 1, and retry with `STRENGTHENED_NEGATIVE_PROMPT` to prevent distorted pseudo-Latin typography leaks.
- [LEARNING-037]: In automation CLI entrypoints, NEVER rely exclusively on directory modification timestamps (`get_latest_run_folder`); ALWAYS support explicit target directory arguments via `sys.argv[1]` to prevent race conditions when running concurrent or historical batch jobs.
- [LEARNING-038]: In CI and PR release readiness, NEVER assume local checks are sufficient without reading `.github/workflows/*.yml`; ALWAYS inspect the exact CI workflow commands (e.g. `ruff check tests/unit` before `pytest`) and replicate the full CI matrix locally before creating or updating a PR.
- [LEARNING-039]: In repository static analysis, NEVER scope linting only to a subset of directories (e.g. `src/`, `exercises/`, `tools/`); ALWAYS execute `ruff check .` across the entire workspace (including `tests/unit/` and root `.py` facade shims) to catch latent formatting and typing violations before CI.
- [LEARNING-040]: In Python modules using `from __future__ import annotations`, NEVER assume code without import errors is cleanly typed; delayed evaluation strings (`dict[str, Any]`) will NOT fail at import time even if `Any` is undefined (`F821`), but will crash during runtime reflection (`typing.get_type_hints`). ALWAYS run static analysis (`ruff check .` / `mypy`) to verify all referenced types are explicitly imported.
- [LEARNING-041]: In multi-file version releases, NEVER bump the version in `CHANGELOG.md` in isolation; ALWAYS atomically synchronize version numbers across all package manifests and project descriptors (`pyproject.toml`, `GEMINI.md`, `CHANGELOG.md`) in the same commit.
- [LEARNING-042]: In GitHub PR workflows, NEVER push speculative follow-up commits to an active PR branch before verifying the prior commit's status check; ALWAYS monitor `gh pr checks <id>` or `gh run list` to ensure the current commit is green to avoid generating consecutive red `x` commit status badges on GitHub.
- [LEARNING-043]: In `CHANGELOG.md` version maintenance, NEVER prepend a new release section without verifying historical version boundary integrity; ALWAYS validate with `tools/extract_release_notes.py <tag>` to prevent version bleed (omitting intermediate version headers like `## [4.3.0]`) and duplicate section headers.
- [LEARNING-044]: In comparison and studio viewers, NEVER iterate solely over an optional prompt dictionary (e.g. `socratic_map.keys()`); ALWAYS implement a 5-tier cascade with index unioning across Socratic prompts, baseline prompts, roadmaps, timeline spans, and disk files, normalizing 0-based timeline spans to 1-based prompt arrays to prevent empty viewers or off-by-one desync.
- [LEARNING-045]: In web media synchronization suites pairing video proxies with uncompressed master WAV audio, NEVER allow both media tags to play unmuted; ALWAYS enforce single-source audio with `videoProxy.muted = true` to prevent phase-delayed acoustic flange and echo.





