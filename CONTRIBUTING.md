# Contributing to YouTube Video Automation Pipeline

Thank you for your interest in contributing! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Code Style & Standards](#code-style--standards)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)
- [Architecture Decisions](#architecture-decisions)
- [Getting Help](#getting-help)

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

### Prerequisites

- **Windows 10/11** (hard requirement — hardcoded paths, `ctypes.windll`, `CREATE_NEW_CONSOLE`)
- **Python 3.10+**
- **FFmpeg** (in PATH, with QSV hardware acceleration support)
- **Audacity 3.x** with `mod-script-pipe` enabled
- **Chrome or Opera** browser (for CDP automation)
- **Git** for version control

### Quick Setup

```bash
# 1. Clone the repository
git clone https://github.com/YOUR-USERNAME/Youtube-Automation.git
cd Youtube-Automation

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
# - Create gemini_model.txt from template (see README.md)
# - Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
# - Configure ACTIVE_PROFILE_INDEX, BROWSER_TYPE, etc.

# 5. Prepare browsers
# - Open Chrome/Opera, sign into gemini.google.com AND aistudio.google.com
# - Create 3 browser profiles for account rotation
```

## How to Contribute

### Types of Contributions Welcome

- **Bug fixes** — Pipeline failures, edge cases, regression fixes
- **Feature enhancements** — New pipeline steps, improved prompts, better error handling
- **Documentation** — README updates, inline comments, workflow guides
- **Testing** — Unit tests, integration tests, test infrastructure
- **Refactoring** — Code simplification, removing duplication, performance improvements
- **Platform support** — Linux/macOS compatibility (major undertaking)

### Before You Start

1. **Check existing issues** — Search [Issues](../../issues) for related work
2. **Open an issue** — Discuss significant changes before implementing
3. **Keep it focused** — One PR per logical change

## Development Setup

### Environment

```bash
# Recommended: Use the same Python version as production
python --version  # 3.10+

# Install dev dependencies
pip install -r requirements-dev.txt  # if exists, else:
pip install pytest pytest-cov black ruff mypy
```

### Project Structure

```
├── run_agency.py              # Main orchestrator (ENTRY POINT)
├── *_step*.py                 # Pipeline steps (1-9)
├── utils.py                   # Shared: browser, config, Telegram
├── gemini_utils.py            # Shared: Gemini UI helpers
├── compile_video.py           # FFmpeg Ken Burns compiler
├── compile_video_with_moviepy.py  # MoviePy SRT compiler
├── tests/                     # Unit & integration tests
├── youtube_runs/              # Runtime output (gitignored)
├── legacy_and_utilities/      # Reference only
└── Implementation plans/      # Future specs
```

### Running the Pipeline

```bash
# Full pipeline (recommended)
python run_agency.py

# Single steps (idempotent, safe to rerun)
python automate_all.py
python refine_script.py
python generate_voice.py
# ... etc (see README.md for full list)
```

### Running Tests

```bash
# Full test suite
python -m pytest tests/ -v

# Single test file
python -m pytest tests/unit/test_timeline.py -v

# With coverage
python -m pytest tests/ --cov=. --cov-report=html
```

## Code Style & Standards

### Python Style

- **Formatter:** `black` (line length 100)
- **Linter:** `ruff` (replaces flake8, isort, pyupgrade)
- **Type checker:** `mypy` (strict mode preferred)

```bash
# Format
black .

# Lint
ruff check .

# Type check
mypy .
```

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Files/modules | snake_case | `generate_voice.py` |
| Classes | PascalCase | `VideoCompiler` |
| Functions/variables | snake_case | `rotate_profile_index` |
| Constants | UPPER_SNAKE_CASE | `FAILOVER_RETRY_LIMIT` |
| Config keys | UPPER_SNAKE_CASE | `IMAGE_GENERATOR_TYPE` |

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`

Examples:
```
feat(pipeline): add timestamp validation in step 8
fix(audacity): handle named pipe reconnection
docs(readme): update troubleshooting table
refactor(utils): extract browser cleanup to helper
```

### Architecture Principles

1. **Idempotency** — Every pipeline step must be safely rerunnable
2. **Checkpoint/Resume** — Long operations save JSON checkpoints to `youtube_runs/<Title>/`
3. **No API keys** — All AI via browser automation (Playwright CDP)
4. **Windows-first** — Hardcoded paths, `ctypes`, `CREATE_NEW_CONSOLE` acceptable
5. **Dual-path design** — Audacity (PyAutoGUI + named pipes), Image gen (Gemini UI + Flow), Video compile (FFmpeg + MoviePy)
6. **Emoji logging** — `✅` `⏭️` `❌` `🔄` for parseable output

### Configuration

- **Root config files** (`gemini_model.txt`, `video_config.txt`, etc.) — project-wide defaults
- **Per-run overrides** — `youtube_runs/<Title>/<config>.txt` takes precedence
- **Secrets** — `gemini_model.txt` is gitignored; never commit tokens

## Testing

### Test Organization

```
tests/
├── unit/           # Pure function tests, no browser/FFmpeg
│   ├── test_timeline.py
│   ├── test_utils.py
│   └── ...
├── integration/    # Requires browsers, FFmpeg, Audacity
│   ├── test_pipeline_steps.py
│   └── ...
└── fixtures/       # Test data, mock transcripts, sample configs
```

### Writing Tests

```python
# tests/unit/test_timeline.py
import pytest
from utils import parse_timestamp

def test_parse_timestamp_mm_ss():
    assert parse_timestamp("1:30") == 90.0
    assert parse_timestamp("12:05") == 725.0

def test_parse_timestamp_hh_mm_ss():
    assert parse_timestamp("1:02:03") == 3723.0
```

- Use `pytest` fixtures for shared setup
- Mock external dependencies (Playwright, FFmpeg, Telegram)
- Integration tests marked with `@pytest.mark.integration`

### Test Coverage

Target: **≥80% coverage** for core utilities (`utils.py`, `gemini_utils.py`, pipeline orchestration).

```bash
python -m pytest tests/ --cov=. --cov-report=term-missing
```

## Pull Request Process

### Before Submitting

- [ ] All tests pass (`pytest tests/ -v`)
- [ ] Code formatted (`black . && ruff check .`)
- [ ] Type checking passes (`mypy .`)
- [ ] Documentation updated if behavior changed
- [ ] CHANGELOG.md updated (if applicable)
- [ ] No secrets in diff (`git diff --check`)

### PR Template

```markdown
## Description
Brief summary of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Refactoring
- [ ] Documentation
- [ ] Test

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass locally
- [ ] Manual pipeline run verified

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] No secrets committed
- [ ] Related issues linked
```

### Review Process

1. **Automated checks** — CI runs tests, lint, type check
2. **Code review** — At least one maintainer approval
3. **Merge** — Squash and merge to `main`

## Reporting Bugs

Use the [Bug Report template](../../issues/new?template=bug_report.md) and include:

- **Environment** — Windows version, Python version, browser version
- **Pipeline step** — Which script failed (Step 1-9)
- **Error output** — Full traceback + emoji-prefixed logs
- **Config** — Relevant `gemini_model.txt` values (redact tokens)
- **Reproduction** — Minimal steps to reproduce
- **Expected vs actual** — What should happen vs what happened

### Common Debug Info to Include

```bash
# Run the failing step with verbose output
python failing_step.py 2>&1 | head -100

# Check checkpoint state
cat youtube_runs/"<Title>"/pipeline.json

# Browser inspection
# Attach Chrome DevTools to localhost:9222 during run
```

## Requesting Features

Use the [Feature Request template](../../issues/new?template=feature_request.md):

- **Problem statement** — What pipeline limitation are you hitting?
- **Proposed solution** — How should it work?
- **Alternatives considered** — Why this approach?
- **Impact** — Which steps/configs affected?
- **Priority** — Nice-to-have / needed for production / blocking

## Architecture Decisions

Significant changes should be documented as **Architecture Decision Records (ADRs)** in `docs/adr/`:

```
docs/adr/
├── 001-browser-automation-over-api.md
├── 002-dual-audacity-paths.md
├── 003-checkpoint-resume-pattern.md
└── ...
```

See [ADR template](docs/adr/template.md) if it exists.

## Getting Help

- **Issues** — [GitHub Issues](../../issues) for bugs/features
- **Discussions** — [GitHub Discussions](../../discussions) for questions/ideas
- **Documentation** — `Project-workflow.md` for deep architecture details

## Recognition

Contributors are recognized in:

- `AUTHORS.md` (or GitHub contributors graph)
- Release notes for significant contributions

---

*Thank you for contributing to YouTube Video Automation Pipeline!*