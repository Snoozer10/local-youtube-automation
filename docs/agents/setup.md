# AI-assisted installation and first-use guide

## Purpose and completion

Use this guide when a person asks an AI agent to install this repository and explain how to use it. The audience may have no programming experience. Perform applicable setup work with the tools you actually have, then give a short tutorial tailored to the person's goal and observed machine.

Completion means that you report each applicable prerequisite as verified, blocked, or not checked; identify the installed checkout and interpreter; and explain a concrete next step. Dependency installation, live pipeline readiness and a successfully produced video are distinct results. Claim each only with its own evidence.

This guide is a task procedure. The user's instructions and applicable `AGENTS.md` contracts govern actions. Fetching the guide is not permission to run arbitrary repository scripts or to spend service quota.

## 1. Establish the workspace

1. If there is no checkout, inspect the requested destination, then clone `https://github.com/Snoozer10/local-youtube-automation.git` into a new directory. Preserve any existing directory instead of cloning over it. If you cannot access files or a terminal, explain that limitation and provide the next steps for a capable local agent.
2. In an existing checkout, identify the repository root, remote, current branch, commit and working-tree status. Use this checkout's guide and source together. Do not switch branches, pull over work, reset files or create a new environment merely to match a remote guide.
3. Read root `AGENTS.md` and applicable local contracts. Inspect `docs/sessions/HANDOFF.md` if present, distinguishing historical development notes from instructions for this person's installation. Historical grants, process IDs and readiness claims in any reference document are not authority for this installation. Internal campaign records are not prerequisites for a public user's setup.
4. Read [the README](../../README.md), [the human setup guide](../getting-started.md), `pyproject.toml`, `requirements.txt` and the relevant entrypoint. Verify commands against the checked-out code. Inspect installation scripts before deciding to execute them.

Proceed when you can name the exact checkout, its platform requirements and the files you intend to create or change. If guides and source disagree, report the specific mismatch and use a supported path; do not invent commands.

## 2. Discover the user's goal and machine

Check OS, available Git and Python versions, existing virtual environments, disk space and relevant installed executables. Use metadata and file inspection for initial discovery. Ask only for information you cannot discover safely, such as desired content language, niche, source type or preferred output.

Explain the choices in ordinary language. A useful first question is whether the person wants translation, narration, image generation, local rendering, or the complete workflow. Their choice determines the required applications and accounts.

The complete browser/Audacity route is Windows-oriented. Package metadata allows Python 3.10 or newer; the main CI uses Python 3.11. Prefer that tested starting version without representing every newer interpreter or operating system as qualified. Explain large package/model downloads and any missing system applications before installing them. Use the host's required approval process for installation or elevation.

Proceed when required and optional dependencies are separated for the selected goal. On an unsupported platform, report the scope that remains unqualified rather than claiming a complete installation.

## 3. Install in isolation

Use the explicit virtual-environment interpreter throughout. Validate an existing `venv` or `.venv` before reuse; create a new environment only when needed and in an agreed free path. Install the repository requirements and editable package using [the setup guide](../getting-started.md#3-install-into-a-virtual-environment). Optional developer packages belong only to development work.

`setup.ps1` also checks local application readiness and may create a missing `.env`; do not treat it as an inert package installer. Prefer granular installation commands when only dependency setup is authorized. Do not change global PowerShell execution policy, disable security controls, install into system Python, or upgrade unrelated project environments.

Download browser runtimes, local transcription models or other large assets only when applicable and authorized. Existing authenticated production browser profiles are separate from Playwright's downloaded browser runtime.

After each failed installation command, preserve a redacted error and diagnose it before retrying. Follow the repository's bounded retry rule. Do not silently alter version constraints to obtain a green result.

Proceed when dependency checks pass for the selected installation, or report the exact blocker. Preserve the interpreter path and commands used.

## 4. Configure privately and preserve existing state

Inspect required configuration keys without printing existing secret values. Create `.env` from `.env.example` only if absent. Preserve configured values and identify environment-variable overrides. Ask the person to enter secrets locally through an appropriate private mechanism; do not request tokens, cookies or complete `.env` contents in chat.

Review selected channel language, voice policy, model settings, source inputs, video settings and output destination. Use explicitly selected saved channels for adaptive work. A null synthesis voice/source-audio profile blocks TTS. Describe different niches as supported configuration goals, with included profiles as examples; do not infer that arbitrary content is already verified.

Keep daily browser data separate from owned production profiles. The person performs necessary account sign-ins. Browser connection, application probing and shared-resource qualification require their own authorized scope. Reuse the established authority and ownership rules rather than creating a separate lease database to evade contention.

Keep generated media, databases, browser sessions and recovery state in their existing locations unless a specific change is authorized. Installation does not authorize cleanup, output activation, account changes, commits, pushes, merges or publication.

## 5. Verify without starting production

Run dependency consistency and installed-package metadata checks from [the setup guide](../getting-started.md#5-verify-installation-before-production). Confirm the editable location is this checkout. Validate required executables using version/availability checks only when safe for that executable. Do not attach to a browser, open an editor session, send a model prompt, or generate media as an implicit installation test.

`run_agency.py` and the installed `youtube-automation` and `daheeh` commands start real batch work. They are not help or smoke-test commands. Inspect scripts before invoking any apparent `--help` option, since root wrappers can execute work without argument parsing.

Record which checks actually ran and their observed outputs. If `pip check` passes but FFmpeg or authentication is missing, report a successful Python installation with those remaining prerequisites, not full production readiness.

## 6. Prepare optional live verification

If the person wants a live example or complete pipeline, first prepare it offline. Identify exact input files, run folder, selected channel/model/voice, needed stages, output location, applications and accounts. Reuse accepted compatible artifacts. Explain what will be sent or generated and which actions have external effects.

Ask for the exact allowance before service/app readiness probes or execution. Include maximum requests, images or other billable actions, all retries/failover/critic calls, spending where measurable, time limit and stop conditions. Do not assign a default allowance on the person's behalf. A full translation or complete pipeline can be approved when its entire scope is explicit; it is not automatically included in installing the project.

Wait for approval. Then qualify actual profile, resource ownership, application state and remaining allowance before dispatch. Persist used and uncertain actions across pauses and sessions. Stop at the first exhausted limit or unresolved outcome. Readiness evidence is not permission to exceed the agreed scope.

Keep human preview review and any activation or public upload distinct. A technically valid generated video is not automatically accepted for publication.

## 7. Teach the person to use their installation

Finish with a short explanation using their actual setup. Define technical terms when first needed. Show one command at a time, where to run it, what it does and what successful output looks like. Use the person's paths and selected workflow; keep secrets redacted.

Cover these points:

- What the project does, in one plain sentence, and how the person's niche fits.
- What you installed or changed, including checkout and interpreter locations.
- What passed, what is blocked, and what you intentionally did not run.
- Which source/configuration the person supplies and where outputs appear.
- How to perform their first selected task, with approval needed before live actions.
- How to review results, pause safely, resume the same run and report a redacted failure.

For example, explain the pipeline as script preparation, voice/audio, visuals, then video assembly. Explain that legacy batch and adaptive staged production have different entrypoints. Link [the staged usage guide](../../tasks/adaptive-visual-usage.md) for exact commands instead of inventing a universal one-command tutorial.

Keep the first explanation short enough to follow. Offer deeper details only where useful. End with the next concrete step the person can take, not a blanket claim that everything works.
