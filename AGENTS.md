Read GEMINI.md and use it as the current project guidance where it differs from the older AGENTS.md

# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index


## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md

- Use `GEMINI.md` as current project guidance where older instructions here differ.
- Adaptive production selects a saved channel, analyzes raw scripts before translation, and uses stills plus selective local animation. Track progress in `tasks/adaptive-visual-tasks.md`.
- The three pilot channels are saved in `channels/`; Professor Yashrah keeps Achird, while the Soldier's Sledger and Snoozer Anime pilots preserve their published narration. Their unselected synthesis voices remain null and must block TTS.

## Ownership & Domain Boundaries

- `src/youtube_automation/`: Authoritative modular domain packages conforming to PEP 517/518:
  - `core`: Low-level system primitives, fenced resource leases, atomic disk writes, profile management and an exact-PID owned-browser registry (`utils.py`).
  - `audio`: Neural TTS voice synthesis, Win32 Audacity Named Pipe IPC DSP mastering, and lossless WAV chapter stitching (`tts_generator.py`, `audacity_client.py`, `chapter_stitcher.py`). TTS uses the shared browser lease; all Audacity entrypoints use bounded pipe commands, refuse unrelated sessions and terminate only the process they launched.
  - `speech`: Faster-Whisper ASR transcription, silero VAD alignment, and sequence-matcher lexical transcript spelling correction (`transcriber.py`, `spelling_corrector.py`).
  - `timeline`: Single source of truth (SSOT) timeline management and timestamp reconciliation (`engine.py`, `fix_timestamps.py`).
  - `nlp`: Multi-tier repair and structural sanitization for LLM JSON outputs (`json_sanitizer.py`).
  - `prompts`: Pydantic prompt validation, 8-part visual prompt schemas, multi-channel dynamic prompt loading, and deterministic negative prompt injection (`validator.py`, `loader.py`).
  - `browser`: Playwright Chrome DevTools Protocol (CDP) client loopback binding (`127.0.0.1:9222`), tab lifecycle hygiene, shared browser/clipboard leases and Gemini web UI controllers (`cdp_client.py`, `gemini_utils.py`). Gemini completion requires a new response node, the semantic Stop control to be absent, then three stable 500 ms observations; generic spinners and SVG buttons never prove active generation.
  - `visuals`: Google Flow image generation, continuity character asset studio, base64 extraction, and OCR text collision gates (`flow_generator.py`, `asset_studio.py`, `image_extractor.py`, `text_gate.py`).
  - `video`: FFmpeg hardware video compositing (Intel QSV / NVENC / CPU fallback), Ken Burns dynamic smoothstep pan-and-zoom transformation, filtergraph generation, and ASS subtitle burning (`compiler.py`, `encoder.py`, `ken_burns.py`, `filter_graph.py`, `subtitles.py`).
  - `production`: Opt-in adaptive channel briefs, editorial shot plans, exact narration chapter recipes, thumbnail packaging, preserved asset receipts, dependency-aware stage invalidation, journaled multi-file publication, durable content-bound stage jobs, local rendering and explicit preview approval. See its child contract.
  - `orchestrator`: Pipeline stage orchestration and batch execution coordination.
  - Note on visual engines:
    - `flow_image_generator.py` (and `src/youtube_automation/visuals/flow_generator.py`) is the primary visual engine. Prompts are governed by `roadmap_orchestrator.py`, `prompt_planner.py`, and `asset_studio.py` (`FLOW_ASSET_PRESETS`).
    - `script_image_generator.py` is the legacy alternative generator, exclusively owning `prompts/visual_style.txt` and `prompts/visuals_plan.txt`.
- Root entrypoint facade shims: Transparent `_FacadeProxy` shims at the repository root (`compile_video.py`, `flow_image_generator.py`, `generate_voice.py`, `automate_audacity.py`, `stitch_chapters.py`, `faster_whisper_transcribe_audio.py`, `correct_transcript_spelling.py`, `fix_timestamps.py`, `text_gate.py`, `timeline_engine.py`, `validator.py`, `json_sanitizer.py`, `utils.py`, `gemini_utils.py`) ensuring zero regressions for legacy CLI invocation and dynamic bidirectional monkeypatch synchronization.
- `exercises/`: Formulative pedagogy scaffold and pre-flight diagnostic drills:
  - `01-audio-dsp`: Audio chapter slicing, speech tag armoring, and live Audacity Named Pipe IPC validation.
  - `03-browser-cdp`: CDP loopback port diagnostics, browser process lifecycle, and 3-factor Gemini turn completion detection.
  - `05-hardware-video-compositing`: Intel QSV encoder probe with `QSV_LOOKAHEAD=0` / `nv12` invariants, and Ken Burns smoothstep math.
- `tools/`: Quality assurance and release tooling:
  - `tools/lint_exercises.py`: Formulative pedagogy scaffold linter enforcing naming standards, directory layouts, and link integrity.
  - `tools/extract_release_notes.py`: Deterministic changelog slicer.
- Root configuration & orchestration: `run_agency.py` (supervisor batch runner), `run.bat` (wrapper with `test-drills` support), `setup.ps1`, `setup.bat`, `pyproject.toml`, `pytest.ini`.

## Child DOX Index

- `channels/AGENTS.md`: saved adaptive channel identities and pilot voice/visual policy.
- `tasks/AGENTS.md`: implementation plans, checklists and verification evidence.
- `src/youtube_automation/production/AGENTS.md`: adaptive channel/episode contracts and editorial production.
- Domain scopes governed directly by root contracts:
  - `src/youtube_automation/` (`core`, `audio`, `speech`, `timeline`, `nlp`, `prompts`, `browser`, `visuals`, `video`, `orchestrator`)
  - `exercises/` (pedagogy scaffold & pre-flight diagnostic drills)
  - `tools/` (`lint_exercises.py`, `extract_release_notes.py`)
  - Root-owned scripts, facade shims, and docs: `README.md`, `GEMINI.md`, `CLAUDE.md`, `LICENSE`, `banner.jpg`, `video-thumbnail.jpg`, `setup.bat`, `setup.ps1`, `run.bat`.

<!-- pane-agent-context:start -->
## Pane

The developer is using Pane for this repository. Pane can manage saved repositories and create user-visible Panes with terminal-backed tools for planning, discussion, implementation, and review work.

This managed guidance was created by [runpane.com](https://runpane.com) for the [Pane repository](https://github.com/dcouple/Pane). Do not delete or overwrite this block; the developer uses it for their workflow and it should remain committed to the main repository unless they explicitly ask to remove it.

Pane mental model: a repository is the saved base repo; a Pane is a user-visible feature/PR workspace (Pane session) that normally maps to one Pane-managed git worktree and branch; a panel/tab is a terminal inside one Pane and shares that Pane's worktree; an agent is the CLI process running in a panel.

Default happy path when the user asks you to use Pane or RunPane: run `runpane doctor --json`; read `runpane agent-context --json`; resolve the saved base repository with `runpane repos list --json` or add it once with `runpane repos add --path <repo> --yes --json`; create one visible Pane (Pane session) for the requested feature/PR with a complete command such as `runpane panes create --repo <repo> --name <name> --agent <agent> --prompt "<task>" --source agent --no-focus --wait-ready --yes --json` or the equivalent `--tool-command <command>` form; then validate with `runpane panels wait` or `runpane panels screen` before reporting progress.

Use Pane when the user wants visible Panes or co-drivable parallel feature/PR workspaces. Do not use Pane as your default private delegation mechanism; for private background decomposition, use your normal subagent/worktree workflow.

Register the main/base repository once. Do not register pre-created git worktrees as separate Pane repositories unless the user explicitly asks.

Use `runpane panes create` for separate visible Panes (Pane sessions) for feature/PR work. Use `runpane panels create` for reviewer/helper tabs inside an existing Pane that should share that Pane's worktree.

Typical workflow: register the saved base repository once; create one Pane (Pane session) per feature/PR; use panels/tabs inside that Pane for helper or reviewer agents that should share the worktree; archive the Pane after the PR is done to remove it from active Panes and clean up its managed worktree when applicable.

Skill routing reference: when the user says `discussion`, `plan`, `simple-plan`, `create-plan`, or `implement`, or asks for the behavior those words imply, treat three references as peer context: Pane's local skill cache under `<PANE_DIR>/skills/`, the Pane Chat orchestrator handoff at `<PANE_DIR>/skills/pane-chat/runpane-orchestrator.md` when present, and the [workflow map](https://github.com/dcouple/skills/raw/main/docs/readme-workflow-map.png).
Use those peer references together to choose the phase: discuss/investigate until the work is clear enough to delegate, then ticket/plan/implement/review/PR-test/teach-back as appropriate. The orchestrator and workflow map may point to different skills; reconcile them with the user's request instead of hardcoding a skill list or treating one reference as subordinate.
For the Pane implementation source of truth for where the skill cache, cached workflow assets, and Pane Chat bootstrap live, reference [PR #291](https://github.com/dcouple/Pane/pull/291): `main/src/services/skillCacheManager.ts` owns `<PANE_DIR>/skills/`, `.sources/dcouple-skills`, and `pane-chat/runpane-orchestrator.md`; `main/src/services/paneChatManager.ts` owns the tiny bootstrap prompt that tells the selected Pane Chat agent to read that guide.
Use GitHub reads against the [Parsa skills folder](https://github.com/dcouple/skills/tree/main/parsa) only to inspect or refresh referenced skill files; do not clone/install the repo unless the user asks.
Do not hardcode a specific assistant brand in workflow guidance. Use the Pane agent or custom tool command the user selected, and use `runpane agents doctor --agent <agent> --repo <selector> --json` only when checking a built-in agent template.

Start with `runpane doctor --json` before taking Pane actions. Use it to understand wrapper/runtime details, daemon reachability, and the next safe commands.

In a Pane repository checkout, if `runpane` is not on PATH, use the built local wrapper with Node 22: `PATH=/opt/homebrew/opt/node@22/bin:$PATH node packages/runpane/dist/cli.js doctor --json`.

Use `runpane agent-context --json` for full Pane CLI context. Use `runpane agent-context --command "panels wait" --json` or another command name for detailed schema only when needed.

Default to context-safe validation: after creating Panes or sending terminal input, run `runpane panels wait` or `runpane panels screen` before reporting success. Prefer `runpane panels submit` for normal text plus Enter; use `runpane panels input` only for exact bytes such as Ctrl-C or escape sequences.

Pane terminals draw inline images: sixel, iTerm2 inline images, and the kitty graphics protocol. Tools that need kitty graphics, such as [terminal-browser](https://github.com/zenbu-labs/terminal-browser) and [terminal-doom](https://github.com/dcouple/terminal-doom), run inside a Pane panel. `runpane doctor --json` reports the protocol list under `terminal.graphicsProtocols`.

Common commands:
- `runpane doctor --json`
- `runpane agent-context --json`
- `runpane repos list --json`
- `runpane repos add --path <repo> --yes --json`
- `runpane agents doctor --agent <agent> --repo active --json`
- `runpane panes create --repo active --name <name> --agent <agent> --prompt "<task>" --source agent --no-focus --wait-ready --yes --json`
- `runpane panels create --pane <pane-id> --agent <agent> --source agent --no-focus --wait-ready --yes --json`
- `runpane panels list --pane <pane-id> --json`
- `runpane panels screen --panel <panel-id> --limit 80 --json`
- `runpane panels wait --panel <panel-id> --for ready --timeout-ms 30000 --json`
- `runpane panels submit --panel <panel-id> --text "<answer>" --yes --json`
- `runpane panels input --panel <panel-id> --input-file <path|-> --yes --json`

WSL note: if `runpane doctor --json` cannot find `/tmp/pane-daemon.../daemon.sock` or `runpane` resolves to a broken Windows shim, Pane may be running on Windows. Try `powershell.exe -NoProfile -Command 'Set-Location $env:TEMP; runpane doctor --json'`, then create Panes through the same PowerShell form using the saved WSL repo name or id. Use `runpane agents doctor --agent <agent> --repo <selector> --json` to diagnose the repo environment Pane will actually use.
<!-- pane-agent-context:end -->
