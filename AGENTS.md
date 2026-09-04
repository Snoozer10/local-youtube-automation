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

## Child DOX Index

- No child AGENTS.md files are needed for the current repository structure.
- Root-owned files: `README.md`, `GEMINI.md`, `CLAUDE.md`, `LICENSE`, `banner.jpg`, `video-thumbnail.jpg`, `timeline_engine.py` (canonical timeline sync engine), `text_gate.py` (multi-layer text collision gate for Flow image generation), `tools/extract_release_notes.py` (deterministic changelog slicer), `setup.bat`, `setup.ps1`, `run.bat`, and root-level project documentation.

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
