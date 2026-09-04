# Design Specification: `gemini-context-engineer` Skill

**Date**: 2026-09-03  
**Status**: Proposed (Awaiting User Approval)  
**Target Installation**: `C:\Users\Snoozer\.gemini\config\skills\gemini-context-engineer\` (User-Global)

---

## 1. Overview & Objectives

The `gemini-context-engineer` skill empowers the agent as an elite Project Context Engineer specializing in repository mapping, maintenance, and contextual lifecycle management. Its sole objective is to create, update, fix, and optimize the `GEMINI.md` workspace context file for any codebase.

### Core Deliverables
1. **Strict 5-Tier Anatomy Enforcement**:
   - YAML Frontmatter (`project_name`, `version`, `tech_stack`, `rules`, `exclude_paths`, `last_indexed`).
   - Exact 5 H1 Sections with mandatory emojis:
     1. `# 🎯 Project Overview`
     2. `# 🏗️ Architecture & Component Mapping`
     3. `# 🛑 Mandatory Engineering Constraints`
     4. `# 🛠️ Common Workflows & CLI Commands`
     5. `# 🔄 Current State & Feature Roadmap`
2. **Zero-Dependency Python Automation Tooling (Stdlib-only)**:
   - `scripts/repo_indexer.py`: Deterministically inspects root configs (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, etc.), builds gitignore-filtered file trees, and extracts verified build/test commands.
   - `scripts/validate_gemini_md.py`: Validates YAML frontmatter, header names/emojis, link targets (relative + absolute + line anchors), and token density budget (<350 lines).
3. **Smart Merge & Migration Strategy**:
   - Backs up existing files to `GEMINI.md.bak`.
   - Preserves bespoke engineering invariants and domain rules while restructuring into the strict 5-tier anatomy.
4. **Token Efficiency & Cognitive Behaviors**:
   - High-density technical writing without filler.
   - Read-first, write-second policy.
   - Zero hallucination via verified config extraction.

---

## 2. Directory & Package Anatomy

```text
C:\Users\Snoozer\.gemini\config\skills\gemini-context-engineer/
├── SKILL.md                          # Main instructions, triggers, workflow protocol & prompts
├── assets/
│   └── gemini_template.md            # Golden 5-tier template with structural guidance
├── references/
│   ├── token_budget_heuristics.md    # Density constraints & context hygiene rules
│   └── migration_guide.md            # Smart merge, .bak backup, and invariant preservation rules
└── scripts/
    ├── repo_indexer.py               # Stdlib polyglot config & gitignore tree scanner (JSON output)
    └── validate_gemini_md.py         # Stdlib schema, link check, and token density validator
```

---

## 3. Detailed Component Specifications

### 3.1 `SKILL.md`
- **Frontmatter**:
  ```yaml
  ---
  name: gemini-context-engineer
  description: >-
    Elite Project Context Engineer for creating, updating, fixing, and refactoring GEMINI.md
    workspace context files. Trigger whenever the user asks to create, update, audit, fix, or optimize
    GEMINI.md, setup project context, or map repository architecture.
  license: Apache-2.0
  metadata:
    version: v1
    publisher: user
  ---
  ```
- **Execution Protocol**:
  1. *Kick-off Hook*: "Begin by asking me to provide the current directory tree or configuration files of my project, and let me know if we are creating a brand new GEMINI.md or optimizing an existing one."
  2. *Scanning*: Run `python <skill>/scripts/repo_indexer.py --root .` to harvest ground-truth data.
  3. *Anatomy Synthesis*: Follow `assets/gemini_template.md` adhering to the strict 5-tier format.
  4. *Validation Gate*: Run `python <skill>/scripts/validate_gemini_md.py GEMINI.md` before concluding.

### 3.2 `scripts/repo_indexer.py` (Stdlib Only)
- Inspects:
  - Node: `package.json` (name, version, dependencies, devDependencies, scripts, workspaces)
  - Python: `pyproject.toml`, `setup.cfg`, `requirements.txt`
  - Rust: `Cargo.toml`
  - Go: `go.mod`
  - Git: `.gitignore` parsing + internal ignore list (`.git`, `node_modules`, `venv`, `dist`, `__pycache__`)
- Generates structured JSON output (`--json`) and console summary.
- Max tree depth limit (default 2-3) to prevent context flooding.

### 3.3 `scripts/validate_gemini_md.py` (Stdlib Only)
- Validates:
  - Frontmatter presence and required keys (`project_name`, `version`, `tech_stack`, `rules`, `exclude_paths`, `last_indexed`).
  - Exact 5 H1 section titles with designated emojis.
  - Line count budget: Warning if >350 lines, error if >500 lines.
  - Markdown link resolution: Validates target file existence for both relative and `file:///` links, handling line anchors (`#L1-L10`).
- Returns exit code `0` on valid, `1` on schema/link violation, and JSON output with `--json`.

### 3.4 `assets/gemini_template.md` & `references/`
- Golden standard 5-tier template.
- `migration_guide.md` providing explicit patterns for extracting legacy rules into the new `# 🛑 Mandatory Engineering Constraints` section without losing tribal knowledge.

---

## 4. Verification & Testing Plan

1. **Unit Test Suite**:
   - Test `repo_indexer.py` against Python, Node, and multi-package fixtures.
   - Test `validate_gemini_md.py` with valid template, missing frontmatter, wrong emojis, broken links, and oversized files.
2. **End-to-End Validation**:
   - Run `validate_gemini_md.py` on the workspace's own `GEMINI.md` to verify live adherence.
   - Validate that the skill package is recognized under `~/.gemini/config/skills/`.
