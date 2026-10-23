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

## Session guidance

- Follow root AGENTS.md for project workflow and DOX. Read docs/sessions/HANDOFF.md for current session state and the task-specific brief under docs/sessions/ for any delegated work.

- Before tackling a task or investigating a problem, follow [Research before execution](AGENTS.md#research-before-execution): targeted web research, version checks, alternatives and an evidence receipt; explicit offline restrictions take precedence.

## Adaptive multi-channel production: current opt-in contract

- Adaptive visual budgets count images, not video frames: twenty stills per minute, minimum twenty, absolute maximum400, reached only at twenty minutes. Saved visual_budget.json can lower this allowance. The Professor pilot uses twenty with require_review=true. Flow runs at1x; every send, uncertain retrigger and retry consumes the durable visual_spending.json budget. All compiler-owned blank graphics and Schulte shots share the deterministic diagram_canvas_v1 substrate, preserving earlier provider receipts and the approved semantic plan. Before advancing past visuals, require an audit of every ordered shot bound to current plan, asset bytes and inspected rendered proof hashes, with all four visual scores at least4. Human preview approval remains separate.

- `adaptive_production.py` and `src/youtube_automation/production/` own the staged adaptive path. [Plan](tasks/adaptive-visual-plan.md), [checklist](tasks/adaptive-visual-tasks.md), [usage](tasks/adaptive-visual-usage.md).
- Explicit saved-channel identity precedes raw-script analysis, restructuring, translation and refinement. Topics cannot replace channel audience, language/dialect, voice, host policy or style. ASR uses the channel language code or audio detection.
- A profile update limited to the schema version, positive visual directives and forbidden motifs may rebind an existing brief without changing verified words, source narration or canonical timing. The rebind invalidates planning and every visual publication; identity, audience, language, dialect, voice, tone, style, host policy, treatments, humor or zoom changes require the normal full analysis boundary.
- Episode analysis classifies its claim basis as factual, fictional or mixed. External `evidence_needs` are fact-check questions, never image requests; source-stated fictional identities, relationships, settings and visible states belong in `continuity_anchors`. Figurative phrases remain non-literal unless the source separately establishes the depicted event.
- Adaptive shot plans replace legacy roadmap camera cycles. They reference canonical narration spans with contiguous integer frames; they never rewrite speech timing. Holds are valid, motion is selective, and typography/annotations are rendered locally. Version 2 keeps the legacy full-shot request and `shot_plan.partial.json`. Version 3 asks Gemini only for compact semantic intents and deterministically compiles timing, IDs, references, treatments, camera defaults and local graphics into the existing `Shot` contract. Record-level patches replace only rejected beats and may split one beat while retaining its original ID on the first replacement. Hook-duration repair computes an exact valid unit partition and keeps it binding through follow-up coverage corrections. Python owns replacement targets, shot count/order, beat IDs and unit ranges for hook repair and for ordinary content-only repair after any required coverage split; only ID, coverage or duration defects that mechanically require new topology remain model-authored. Gemini returns one `SemanticRepairContent` record per compiler-owned slot. Every compiler-owned slot exposes current continuity/reference/framing/entity IDs, available references, cumulative earlier entity IDs, admissible framing choices and the exact new/reuse/edit invariants; Gemini still selects semantic content, and Python revalidates it before binding. Missing or invalid content is repaired inside the same transaction before Python binds it to the immutable topology. A later semantic record cannot repeat an established entity ID with `continuity="new"`; that beat must reuse/edit an established reference or choose a genuinely distinct entity ID before compilation. After compilation, a channel-forbidden visual family becomes a `SEMANTIC_RECORD_INVALID` issue addressed to its originating beat before checkpoint or plan validation, while final-plan validation retains both family and entity-scene prohibitions as defense-in-depth. Accepted v3 intent batches resume from `shot_plan.semantic.partial.json`, which is bound to planner/compiler versions and brief/timeline/window lineage without consuming the legacy checkpoint. Planning requests are bounded by narration time, not just ASR span count. One Gemini chat is bound to each planning window. Schema and semantic repairs remain in that exact chat as monitored, content-addressed UTF-8 attachments containing the first rejected baseline, latest candidate, validation error and exact schema; Gemini sees only a short request wrapper, and the source request is not re-uploaded. Before repair, the recorded rejected-turn chat URL must still match the active stable conversation. Every transport failure, including a provider soft refusal, preserves its receipt, abandons the failed conversation and retries the exact full request in a fresh clean chat. An explicit Gemini App usage-quota message instead journals `quota_exhausted`, ends the current durable attempt, switches only the verified pipeline-owned CDP browser to the next profile index, recomputes the profile-bound stage recipe and retries the exact request within a bounded non-repeating ring. Persistent planning defaults to a content-addressed UTF-8 request attachment. Gemini sees a plain short instruction and a friendly filename with only a short Base32 request ID; the full digest remains in local receipts. Before file interaction, the transport requires a stable bound route, complete document, mounted navigation and composer, unchanged conversation counts and no visible main-surface loading state. It then searches only the active composer and requires exactly one matching chip plus several stable observations with no scoped upload progress, spinner, busy state or processing status. Attempts are journaled before Send with exact user-turn/response ordinals, and recovery accepts only the response paired to that turn. Recovered refusals follow the same fresh-chat transport path. Atomic receipts preserve preparing, attachment-ready, submission-pending, submitted, uncertain, interrupted, timed-out, quota-exhausted, provider-refusal, rejected and completed states so late valid responses are recovered and invalid responses are never replayed as success. Recovery requires the stable `/app/<conversation-id>` route; the transient blank `/app` route is never a recovery target.
- Semantic compiler validation uses one initial pass plus at most five targeted corrections. Corrections that reveal a later deterministic constraint retain a bounded repair opportunity; the sixth failed compile ends the transaction rather than looping indefinitely.
- Episode-owned `visual_strategy.characters` defines explicit source-grounded or illustrative identities. Shots and semantic repair records reference them through `character_ids`; ordinary `entity_ids` remain scene-local. A declared recurring person can return in a new setting without moving a scene-image reference. Empty cast fields preserve existing fingerprints; nonempty casts bind their immutable definitions and canonical character receipts. Never invent a presenter for a host-free channel or assume every anonymous human beat is one person. Use actual Flow Characters registration and exact identity verification, not a scene image or generic provider card as a substitute.
- Human repair feedback is typed and canonical-source-bound. Gemini receives only rating, reasons and correction targets; critic receipts bind that sanitized feedback hash. A cached model approval predating new feedback cannot advance generation. Empty feedback fields preserve old receipt fingerprints. The current strict Characters adapter still needs live provider control/identity proof; unsupported controls stop before spending, and offline tests do not prove artistic consistency.
- Semantic-planner lineage 24, shot-compiler lineage 15, and renderer lineage 14 govern native planning, timing and rendering. Renderer14 invalidates renderer12/13 cached proofs and requires fresh complete proof, critic and human review. Shared overlay passes preserve ASS stacking and generic timing; above 100 fps only running timers use doubled timestamps/PTS before restoring the original timeline. Optional paired pictogram destination/arrival fields preserve legacy fingerprints when omitted. Renderer changes require fresh current proofs and complete review.
- Repeated adaptive failures are a versioned regression corpus. Preserve raw receipts/checkpoints unchanged, derive only minimal sanitized fixtures with stable failure codes, responsible layer and expected corrected behavior, then replay the full corpus offline before another costly Gemini or Flow run. The readiness report combines corpus replay, final-validator audit and sanitized live metrics; it may report readiness for at most one bounded live request; current user authorization and a concrete bounded action packet govern any action when both offline gates are green. Rules decidable from canonical narration, timing, topology, entities or local-overlay contracts belong to Python preflight/compiler logic and must become beat- or slot-addressable before final validation; do not compensate by endlessly enlarging prompts.
- Model exercise-specific graphics as generic narration-bound visual-event obligations carrying their source span, event kind/preset, permitted timing, deterministic data and affected semantic slots. Activate an obligation only from explicit source narration or the content-bound episode strategy, never from the saved channel or broad topic alone. `schulte_6x6` is the first preset, not a universal Professor Yashrah template.
- A saved channel profile is the stable brand constitution, not an episode template. Every new source URL must compile a versioned episode visual strategy before translation: exact topic and promise, evidence mode, emotional arc, 8-15-second hook, visual-mode palette, local UI kit, pacing, motion grammar and repetition limits. Every planned shot must bind its exact narration excerpt, viewer takeaway and semantic link, then pass a separate editorial-critic review before Flow.
- Technical preview success does not imply editorial acceptance. Structured review scores semantic match, hook strength, attractiveness, progression, continuity, readability and motion. Historical preview SHA-256 15ec1c7dfc01764665e84a5941c076fb8e3cc980b3e6b2e9874ea370f4b1b782 has seven 4/5 scores bound only to that artifact. Current preview SHA-256 ca8e6c98d381729654b08d2c987537af78c15a5d2b1c3b2386ea4e93d0e154f0 was accepted by the user at raw 4.1–5; integer score bookkeeping is separate, and the user already approved recording 4/5 for each dimension. Do not transfer scores from the older preview. The user deferred proposed improvements until after merge. Explicit human rejection still supersedes earlier approval intent and model scores: bind it to verified hashes, preserve evidence and revoke its active visual audit. A replacement needs a fresh complete review. Apply the reference playbook (tasks/professor-visual-playbook.md); passing tests cannot establish artistic acceptance.
- Do not send framing coordinate literals to image generation. No automatic decorative telemetry or literal idiom props. Exact references and complete validated assets are required; missing references block rather than becoming independent generations.
- Accepted asset copies and hashes outlive provider scratch paths. Asset publication journals the content-bound receipt intent before copying accepted bytes; restart recovery activates only a complete image matching the current recipe, reference, hash, pixels and geometry. Flow counts only visible chips inside the active prompt composer. When the receipt-bound project reloads without provider cards, restore only the exact content-addressed accepted PNG and verify its provider identity or pixel digest both after attachment and immediately before submission; standalone shots require an empty prompt reference set. Never substitute a recent card. Full-frame background OCR must actually run. Technical verification is separate from human editorial approval.
- Adaptive asset and thumbnail OCR explicitly use English and Arabic Tesseract data. `pytesseract` alone is insufficient; the local engine may be found through `TESSERACT_CMD`, PATH or the ignored `.runtime/tesseract/tesseract.exe` project runtime.
- Browser, clipboard, Audacity and encoder entrypoints share installation-wide leases across adaptive and legacy paths. Adaptive CLI stages are durable run-bound SQLite jobs: unchanged successful recipes skip only after output validation, missing/corrupt outputs repair automatically, content-bound existing outputs may be adopted, changed content/config creates new attempt lineage, expired workers are reclaimed with a higher fence, and three consecutive failures open a circuit until explicit `--force-retry`. Changed stage recipes journal and archive mutable downstream activations while preserving content-addressed accepted bytes and immutable renders. A plan-recipe change may preserve a current or explicitly migratable semantic checkpoint only after recompiling it against the current brief, timeline and narration-event boundaries; unsupported or unsafe checkpoints remain invalidation evidence. Stage and distinct device claims nest and jointly fence publication. Adaptive TTS uses an owned tab in an existing CDP session; it does not launch, rotate or terminate the user's browser. Browser rotation may terminate only the exact registered CDP listener PID. Immutable final filenames precede atomic activation pointers; byte-verified clip caches include render/tool recipes.
- A master requires a current preview and explicit approval bound to plan, assets, audio and render settings. Preview/master publication journals permit restart activation of an already encoded orphan only after its complete input lineage, path, bytes, frame rate, frame count and audio stream revalidate. `active_master.json` identifies the accepted file. Three reviewed 60–90 second pilots precede full episodes.
- `run_agency.py` excludes adaptive runs. Use the staged CLI through the remaining Professor Yashrah and Soldier's Sledger pilots. Live UI behavior, Arabic readability, crop semantics and artistic quality still require direct pilot review.
- Adaptive narration partitions the validated refined script into exact, content-bound chapters using the selected channel voice. It does not apply the legacy Egyptian comedy TTS rewrite; completed WAVs require their recorded MD5 on resume. Manifest write failures must propagate.
- Offline voice direction is a script- and channel-bound candidate stage that validates a supplied response without invoking a model. Acceptance stays separate, names a reviewer and binds the exact current candidate SHA-256. This offline stage does not satisfy or waive the required automated model-generation step. TTS restart recovery derives retry eligibility from durable per-chapter spend/signature history; malformed or contradictory state fails closed before browser submission.
- Browser UI overlay guards inspect every matching DOM overlay with bounded count/nth checks (maximum 32): a hidden first match cannot hide a visible later one. Negative, over-cap, failed or unreadable visibility probes block with `overlay visibility probe failed`; only confirmed absence passes. When an overlay is visible, a missed text selector remains blocked.
- Source-narrated pilots use `source-audio` after brief analysis: local owner media is trimmed to the caption window, the original words remain unchanged in the writing outputs, and a byte-checked WAV receipt is required. Imported runs cannot invoke TTS. The three selected profiles are in `channels/`; Professor Yashrah retains Achird, and new Soldier's Sledger narration uses the user-delegated Charon selection. Historical source-narrated pilots preserve their published narration. Snoozer Anime's unselected synthesis voice remains null and blocks TTS.
- New Soldier's Sledger episodes start with current/trending topic research, Gemini original script creation and Gemini refinement; a copied video URL is not required. Preserve the selected topic and dated research sources with the original draft, then use channel-bound analysis before downstream refinement/narration/planning. Owner backup videos are comparison references; see channels/AGENTS.md for their location. The older caption-derived pilot remains historical evidence. Null synthesis voices still block TTS.
- Adaptive Audacity polishes verified chapters before stitching, refuses an unrelated open Audacity session, and preserves checkpoints on incomplete work. Every adaptive pipe exchange has a deadline and response-size limit and requires an explicit success response and the checked-in optimizer preset; stalled or failed DSP cannot silently publish a WAV. Polished offsets reflect actual gapless WAV frames; the raw voice checkpoint is not rewritten by DSP. Stitching verifies that the saved polished manifest still matches the chapter bytes, rejects partial polish, and atomically replaces the master after frame validation. Voice generation is blocked once polishing or stitching has begun, preventing raw timing from overwriting physical offsets.
- Adaptive thumbnails consume the selected brief, use a shared browser lease, require a real full-frame OCR pass, preserve content-addressed accepted images, and verify an input-bound receipt before skipping work. Generated images reserve space for optional local typography. Legacy thumbnails retain their existing webcomic path.
- Adaptive rendering now applies the shot focal point during source aspect-ratio cropping and constrains pans to keep that focal point in view. A camera recipe change requires new cached clips, preview and approval. Geometry tests do not prove semantic subject recognition; review actual preview frames.
- File-backed FFmpeg filter graphs use `-/filter_complex`; `-filter_complex_script` is removed in FFmpeg 9 and must not re-enter either render path.
- No DNS, network-adapter or system network configuration changes are part of this workflow. The browser launcher must not pin AI Studio to a hard-coded resolver address.

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
| `.codex/` | [.codex/AGENTS.md](.codex/AGENTS.md) | Branch-local Codex skill configuration and verification |

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
- **Intel QSV Compositing**: `QSV_LOOKAHEAD=0` (no lookahead with sw frames); `format=nv12` filter required for `h264_qsv` (yuv420p crashes); CFR frame math (`round(dur * fps)`); CLI >1000 chars use the file-backed `-/filter_complex` contract.
- **Playwright CDP**: Bind strictly `127.0.0.1:9222`; terminate a browser only after verifying the owned-registry PID, creation time, native image, profile and listener; prompt injection via `keyboard.insert_text` (fires React SyntheticEvents); turn handshake (stop button gone + 3x 500ms stable); 25-row roadmap pages (`ROADMAP_WINDOW_SIZE=25`). Treat an overlay as dismissible only when current task state identifies the expected transient overlay; unknown or recovery dialogs fail closed and remain untouched. Card-spawn handshake: record card count before submit, wait ≤20s for count increase before entering generation watchdog.
- **Flow Generation Watchdog**: Scoped to `active_card` (last card only); 120s stall ceiling → reload + re-inject; 360s hard ceiling → dump diagnostics + rotate account; error regex MUST include `reached your usage limit|you have not been charged`; always dump paired `.png` + `.html` on any stall.
- **Data & Subprocess Safety**: Canonical `timeline.json` SSOT; zero cloud SDKs (local CDP loopback only); subprocess args as `list` with `shell=False`; UTF-8 streams (`sys.stdout.reconfigure`); atomic disk writes (`NamedTemporaryFile` + `os.replace` + `fsync`).

## 🛠️ Common Workflows & CLI Commands
- Run unit test suite when required: python -m pytest -q --tb=short tests/unit
- Run full test suite at the frozen-tree closeout: python -m pytest -q --tb=short tests/
- Run hardware/daemon pre-flight drills: `python -m pytest exercises/ -v -m drill`
- Validate exercise pedagogy scaffold: `python tools/lint_exercises.py`
- Run pre-flight drills via wrapper: `run.bat test-drills`
- Run exercise linter via wrapper: `run.bat lint-exercises`
- Code linting (read-only): ruff check .; do not use --fix as a gate command.
- Static type checking: mypy --strict src/
- Run supervisor batch: `python run_agency.py`
- Run individual phases: `python automate_all.py` / `python compile_video.py`

### Agent Orchestration and Quality Gates
- **Coordinator:** Owns scope, sequencing, cross-lane decisions, final diff review and the single shared master/ledger.
- **Task capsules:** State task ID, exact file ownership, observable acceptance, constraints and required evidence. Assign implementation to an executor and documentation to an archivist; use explorers/investigators for read-only discovery, testers for focused/final checks, and reviewers for independent diff review. Workers do not edit shared status or commit.
- **Codex worker roles:** explorer uses GPT-6 Luna/medium; investigator GPT-6 Luna/xhigh; default_executor, tester and archivist GPT-6 Luna/high; senior_executor GPT-6.1 Sol/xhigh; reviewer GPT-6.1 Sol/high. The coordinator uses its current configured model. These role settings are fixed by the harness; do not edit agent TOMLs or rely on obsolete model rankings.
- **Parallelism:** Use few non-overlapping tasks only when parallel work reduces rerun risk. Serialize shared browser, audio, database, provider and Git/GitHub actions. Stop each worker when its evidence is complete.
- **Verification:** Run focused tests after implementation, then required full tests, lint, build and replay gates once against the frozen exact tree. Record commands and raw results in the chronological ledger; one coordinator updates the task master.
- **Quota and side effects:** Follow the registered role and task fit; never infer quota from token, cost or context estimates. Follow current user authorization with concrete per-action limits and stop conditions; earlier spent caps do not reset.

## Current Workstream Status

The former status table is preserved as a historical, unverified snapshot in [ACTIVE_WORKSTREAMS_VERIFICATION_HISTORY.md](docs/sessions/GEMINI_WORKSTREAM_HISTORY_20261016.md). Consult [BRANCH_COMPLETION_MASTER.md](tasks/BRANCH_COMPLETION_MASTER.md) for current work and verification state.

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
- [LEARNING-030]: Generated backgrounds contain no typography. Diagrams require a narrative purpose and supported evidence; never add compulsory decorative telemetry. Render labels, arrows, highlights, deterministic data grids and timers locally, and inspect Arabic shaping and numeric legibility in the actual preview.
- [LEARNING-031]: Legacy feed attachment only (adaptive mode uses receipt URL plus pixel identity): in Google Flow Mode B previous image attachment, NEVER slice primary cards from the bottom of the feed (`primary_cards[-count:]`); Google Flow prepends newly generated cards to the top of the feed (`lowest Y`). ALWAYS slice from the top (`primary_cards[:count]`) and reverse to attach true chronological previous frames.
- [LEARNING-032]: In Gemini web Markdown table parsing, NEVER assume table rows are pipe-delimited (`|`); Gemini SPA renders tables into native HTML `<table>` elements where browser `innerText` converts cells to tab-delimited (`\t`) strings. ALWAYS support both `|` and `\t` row delimiters in table line parsers.
- [LEARNING-033]: In Gemini web prompt construction for text-only tasks (e.g. storyboards and roadmaps), NEVER include diffusion model hex codes, pixel coordinates (`X: 180 to 1740`), or render specs; Gemini web's multi-modal safety filter misinterprets them as image generation/manipulation requests and responds with refusal cards ("I am just a text-based AI and cannot help with that." / "I seem to be encountering an error.").
- [LEARNING-034]: Unresponsive Chrome renderers can hang CDP attachment. Use bounded connection timeouts, clean up only pipeline-owned tabs, and terminate a browser only when its exact CDP listener PID is recorded in the owned-process registry. Never prune unrelated user tabs or kill an unregistered listener.
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
- [LEARNING-046]: A mounted Gemini input with zero response cards does not prove a new chat is clean; saved history can hydrate later and be mistaken for the submitted turn. ALWAYS request the exact `New chat` control, require the blank `/app` route, zero responses and empty input to remain stable, and verify that the newly mounted user-query text matches both ends of the submitted prompt before waiting for a response. Never use a generic SVG button as Send.
- [LEARNING-047]: Gemini model selection must match the complete displayed model label after removing only a numeric version prefix; `Flash` and `Flash-Lite` are different models. Project `.env` values are defaults and must not overwrite an explicit process-level setting.
- [LEARNING-048]: A schema-valid still-video shot plan is not editorially valid by itself. Adaptive plans require resolved cadence limits, framing diversity, selective motion, visible stable entity IDs, reference chaining for recurring entities, and rejection of literalized figurative transformations before any image generation starts.






- Fixed diagram tails must meet framing diversity in the last editable window. Migration from 17/8 recompiles across the event boundary, archives an insufficient prefix, and reopens only its affected suffix; older migrations retain the pre-event restriction.

- Repair slots exclude prefix references whose non-grid scene budget is exhausted; binding rejects their reuse/edit before compilation. Fresh scenes require distinct entities. Rejected post-event 19/9 checkpoints require explicit archived regeneration.

- Schulte templates compile to challenge_ui. Mandatory continuous grid shots and their preceding prefixes reset consecutive mode/beat-kind budgets in semantic and final validation; local copy must still progress. The episode palette must include challenge_ui. Python owns this rendered-mode canonicalization.

- Rejected critic feedback persists with its exact reviewed plan under editorial_rejections/plans. Recover it only when review hash, ordered shot coverage, brief and timeline match; archived feedback never replaces a fresh active approval. Capture compatible legacy rejections before plan-recipe invalidation. Critic coverage failures must mark the browser receipt through reject_last_response before requesting a correction, with the required ordered shot IDs explicit.

- Planner21/10 supplies compact rejected-only correction targets with exact source ranges, prior visible states and reasons. Unchanged non-grid assets rejected for overlapping narration raise SEMANTIC_CRITIC_REJECTED_REUSE inside bounded repair; slots expose the forbidden reuse references. Edits that change meaning remain available. Compiler10 is unchanged, so20/10 checkpoints migrate across events before reopening the critic-rejected suffix. Critic review evaluates rendered overlays and valid static holds while retaining strict narration matching.
