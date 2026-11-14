# Set up your first workspace

This guide uses Windows PowerShell. The complete browser and Audacity workflow is Windows-oriented. Python 3.11 is recommended for local development; Python 3.10 is compatibility-tested in CI, and Python package metadata allows Python 3.10 or newer. Use Python 3.11 for the starting path below. A GPU is optional for supported local CPU rendering and transcription paths, but performance depends on your machine.

If you would prefer an AI agent to perform setup and teach you how to use the project, copy the prompt in the [project README](../README.md#copy-and-paste-to-your-ai-agent). The [full agent guide](agents/setup.md) defines what it should check and report.

## 1. Choose what you want to do

You can work on individual stages, or prepare a complete video. Your choice determines which applications and accounts you need. Required baseline components support local installation and video rendering, while stage features require external services, application daemons, or separate grants.

| Task | Requirement category | Additional requirements |
|---|---|---|
| Install and inspect the project | **Required baseline** | Git, Python 3.11 (`py -3.11`), disk space, and package access |
| Render video locally | **Required for video compilation** | FFmpeg and FFprobe on `PATH` (`winget install Gyan.FFmpeg`) are rendering prerequisites; accepted inputs |
| Run test suite and offline audits | **Development / QA** | `requirements-dev.txt` (`pytest`, `mypy`, `ruff`, type stubs) |
| Translate or refine a script through Gemini | Optional stage feature | An authenticated, dedicated browser profile (see [CONTRIBUTING.md](../CONTRIBUTING.md#configuring-local-debugging-profiles)) and CDP loopback port check (port 9222) |
| Generate narration | Optional stage feature | AI Studio access and a channel with a configured synthesis voice |
| Polish audio through Audacity | Optional stage feature | Audacity 3.x+ with `mod-script-pipe` enabled (`\\.\pipe\ToSrvPipe`) |
| Transcribe audio locally | Optional stage feature | Faster-Whisper dependencies and disk space for a downloaded model |
| Generate images | Optional stage feature | Google Flow access and an approved image budget |
| Validate adaptive generated images or thumbnails | Optional stage feature | Tesseract OCR engine with English and Arabic language data |
| Send progress notifications | Optional stage feature | Privately configured Telegram bot token and chat ID |

Service access, subscriptions and limits vary. Local execution still uses your disk, CPU and possibly GPU. Installing the project does not establish access to every external service.

## 2. Download the repository

Open PowerShell in a folder where you want to keep the project:

```powershell
git clone https://github.com/Snoozer10/local-youtube-automation.git
Set-Location local-youtube-automation
```

If you already have a checkout, use it rather than cloning over it. Preserve any existing changes, configuration and output folders.

## 3. Install into a virtual environment

A virtual environment keeps the project's Python packages separate from other projects. These commands use its interpreter directly, so activating a shell script is unnecessary.

```powershell
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip install --no-deps -e .
.\venv\Scripts\python.exe -m pip check
```

If `py` is unavailable, install Python 3.11 or select a verified compatible Python interpreter. If `venv` already exists, check its interpreter and packages before reusing it. Stop after any failed command and resolve the reported error before proceeding.

The requirements include audio and machine-learning packages. Downloads can take time and substantial disk space. An editable install makes the root command wrappers resolve the source in this checkout and writes `.dist-info` package metadata for this installation. If package dependencies change in `pyproject.toml`, re-running `.\venv\Scripts\python.exe -m pip install --no-deps -e .` refreshes the installed metadata. Installing only `-e .` without `-r requirements.txt` does not reproduce every dependency in `requirements.txt`.

For development and running tests, install the test and linting tooling:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

For browser stages, download the Playwright Chromium runtime when needed:

```powershell
.\venv\Scripts\python.exe -m playwright install chromium
```

This download does not sign you in to Chrome or configure your production browser profile. The repository also has [setup.ps1](../setup.ps1), which automates installation, can copy a missing `.env`, and probes local Audacity and browser readiness. Review those actions before using it; it is more than a dependency check.

## 4. Configure only what your workflow needs

Review [.env.example](../.env.example). Create `.env` only if it is absent:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

Edit required values privately. Keep existing working values, and leave secrets out of chat, screenshots and Git. A template copied to `.env` is not a configured installation. Already-set process environment variables can override values loaded from the file.

Other configuration has separate owners:

| File or directory | Purpose |
|---|---|
| [channels/](../channels/) | Saved channel identity, language, voice and visual policy |
| [daheeh_config.json](../daheeh_config.json) | Legacy writing and pronunciation configuration |
| [video_config.txt](../video_config.txt) | Default video rendering settings |
| [transcribe_config.txt](../transcribe_config.txt) | Local transcription settings |

The adaptive workflow can use a run-local `video_config.txt`. Inspect the selected run's configuration rather than assuming the repository default will apply.

Browser stages use authenticated web sessions through Chrome DevTools Protocol (CDP) communicating over a local loopback port (default 127.0.0.1:9222). Diagnostic setup scripts include a port check to probe whether this loopback port is listening. Before connecting, launch Chrome with a dedicated user data profile following the [dedicated browser profile instructions in CONTRIBUTING.md](../CONTRIBUTING.md#configuring-local-debugging-profiles). Sign in yourself when prompted; keep your everyday browser profile separate. Dated session notes and historical allowances in reference documents do not authorize actions on your machine.

## 5. Verify installation before production

```powershell
.\venv\Scripts\python.exe -m pip check
.\venv\Scripts\python.exe -m pip show youtube-automation-pipeline
```

`pip check` should report no broken requirements. `pip show` should identify the installed package and this checkout's editable location. These checks establish dependency consistency and package installation. They do not prove that a browser, model, voice, application, channel or video is ready.

Do not use `python run_agency.py` as an installation test. It begins real pipeline work.

## 6. Choose a production mode

### Legacy batch mode

The legacy supervisor takes source URLs from `youtube_urls.txt`, translates them, then processes run folders through its configured stages. Inspect that file and existing run folders before starting, because the batch can include more than one video.

After configuring applications, account access and the intended scope, start it with:

```powershell
.\venv\Scripts\python.exe run_agency.py
```

This command can contact services and perform media work. Outputs and per-run state are stored under `youtube_runs/`. It is not a tutorial-sized dry run.

### Adaptive staged mode

Follow [the public adaptive mode guide](usage/adaptive-mode.md) for explicit run and channel selection. It separates analysis, writing, narration, shot planning, assets, preview, review and rendering. Read the current command requirements before invoking a stage.

Channel identity and episode subject are separate. The supplied profiles illustrate different languages and content styles. A source-audio channel with a null synthesis voice must not be sent through TTS. New niches need their own suitable profile and output review; broad configurability does not establish validation of every niche.

The bundled profiles below are optional examples for trying the system. Use a suitable profile with your own prepared inputs, or follow [the channel bundle guide](usage/channel-bundles.md) to create and validate your own:

| Profile | Example content | Language and narration |
|---|---|---|
| [professor-yashrah.json](../channels/professor-yashrah.json) | Psychology, attention and human behavior | Arabic; configured synthesis voice |
| [soldiers-ledger.json](../channels/soldiers-ledger.json) | Military history | English profile; configured synthesis voice |
| [snoozer-anime.json](../channels/snoozer-anime.json) | Anime story recaps | Arabic; no synthesis voice selected |

These profiles have their own editorial policies. For a different niche, prepare and validate a suitable saved profile rather than assuming an existing channel fits. Consult the [channel contract](../channels/AGENTS.md) before changing a profile.

## 7. Review results and resume carefully

Find the selected run folder and inspect its scripts, audio, generated assets and preview. Technical validation does not replace your review of factual accuracy, pacing, pronunciation, readability and visual relevance. Adaptive master activation requires its explicit human review steps.

To pause, stop initiating new stages and use the running tool's normal interruption path. Allow owned in-flight work to settle when possible. Keep checkpoints, receipts and generated files. Before resuming, identify the same run, its last completed stage, remaining allowance and any request whose outcome is uncertain. Resume through that workflow's supported entrypoint instead of deleting state or regenerating accepted assets.

For an error, save a redacted message and the failed stage. Start with the [error register](error-solving/understood-errors.md) and [engineering diagnosis route](agents/workflows.md#debugging). Do not delete browser workspace files, recovery data or checkpoints as a generic troubleshooting step.
