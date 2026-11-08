# GitHub Actions Runtime Deprecation Warning Triage Report

**Task**: Issue #83 ("ci: review github actions runtime deprecation warning")
**Campaign Context**: Issue #78 (Architecture Renewal Campaign)
**Task Branch**: `ci/actions-runtime-triage-83`
**Base Commit**: `9a0515c96cbe46b620f8a90a83ae3d496f2b4c58` (origin/master)
**Date**: 2026-11-04

---

## 1. Executive Summary

This report documents the triage and resolution of the GitHub Actions runtime deprecation warning observed during CI execution (first recorded in setup PR #82 run 41348841543, and observed on `master` runs 41791130783 and 41795366049).

The warning arose because official GitHub actions `actions/checkout@v4` and `actions/setup-python@v5` originally targeted the Node.js 20 runtime (`node20`). Under GitHub's runner migration policy, Node.js 20 was deprecated and forced to execute on Node.js 24 before full removal from GitHub-hosted runner images.

To resolve the warning without breaking changes, unintended privilege escalation, or scope creep:
1. `actions/checkout` is upgraded from `@v4` to `@v6.0.2` in `.github/workflows/ci.yml` and `.github/workflows/release.yml`.
2. `actions/setup-python` is upgraded from `@v5` to `@v6.2.0` in `.github/workflows/ci.yml` and `.github/workflows/release.yml`.
3. These upgrades reference versioned release tags published by GitHub. Note that both upstream release APIs report `immutable: false` ([checkout v6.0.2](https://api.github.com/repos/actions/checkout/releases/tags/v6.0.2), [setup-python v6.2.0](https://api.github.com/repos/actions/setup-python/releases/tags/v6.2.0)); observed resolved commits are recorded herein (`de0fac2e4500dabe0009e67214ff5f5447ce83dd` and `a309ff8b426b58ec0e2a45f0f869d46889d02405`) without broadening the task into workflow SHA-pinning changes.
4. `softprops/action-gh-release@v2` in `.github/workflows/release.yml` is retained unchanged to preserve existing release publication authority without implied modification.
5. All E02 (PR #86) test-selection flags (`python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" --cov=. --cov-report=xml`), explicit pytest configuration, live-browser exclusion, and isolation guards remain 100% intact.
6. Warning elimination is strictly scoped to the observed CI and onboarding jobs. The release workflow was not executed or qualified in this slice, and unchanged `softprops/action-gh-release@v2` still targets Node.js 20.

---

## 2. Primary Source Receipts

### 2.1 Historical CI Receipt (Run 41348841543)
In the successful CI run on PR #82 (`test` job 124974409531), the `Complete job` step emitted:
```text
2026-11-01T20:59:45.1327683Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
```

### 2.2 Reaffirmed Baseline Receipt (Run 41791130783)
Following the merge of PR #86, the master push run 41791130783 reaffirmed the identical warning:
```text
2026-11-04T07:27:27.3320099Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
```

### 2.3 Documentation Workflow Vetting Receipt (Run 41795366154)
In contrast, `.github/workflows/docs.yml` (run 41795366154 on `master`), which utilizes `actions/checkout@v6.0.2` and `actions/setup-python@v6.2.0`, completed in 12 seconds with clean execution:
```text
onboarding	Set up job	2026-11-04T07:53:17.0825151Z Download action repository 'actions/checkout@v6.0.2' (SHA:de0fac2e4500dabe0009e67214ff5f5447ce83dd)
onboarding	Set up job	2026-11-04T07:53:17.1735220Z Download action repository 'actions/setup-python@v6.2.0' (SHA:a309ff8b426b58ec0e2a45f0f869d46889d02405)
onboarding	Complete job	2026-11-04T07:53:20.1904922Z Cleaning up orphan processes
```
No deprecation warnings or compatibility translations occurred in that run.

---

## 3. Official Action Guidance, Version Matrix & Tag Verification

### 3.1 Node Runtime Targets Across Major Releases
Inspection of official upstream `action.yml` manifests yields:

| Action | Major / Tag | Runtime Target | Status / Notes |
|---|---|---|---|
| `actions/checkout` | `v4` | `node20` | Deprecated; triggers forced execution warning on Node 24 |
| `actions/checkout` | `v5.1.0` | `node24` | Node 24 support; breaking changes to PR checkout defaults |
| `actions/checkout` | `v6.0.2` | `node24` | **Selected**: Vetted in `docs.yml`; input-compatible with our workflows; Node 24 execution |
| `actions/checkout` | `v7.0.1` | `node24` | Breaking changes (fork PR blocking on `pull_request_target`) |
| `actions/setup-python` | `v5` | `node20` | Deprecated; triggers forced execution warning on Node 24 |
| `actions/setup-python` | `v6.2.0` | `node24` | **Selected**: Vetted in `docs.yml`; input-compatible with our workflows; Node 24 execution |
| `actions/setup-python` | `v7.1.0` | `node24` | Breaking changes (removes `pip-install`, ESM migration) |
| `softprops/action-gh-release` | `v2` | `node20` | **Retained**: Third-party release tool; left untouched to preserve publication authority |

### 3.2 Upstream Release Tag Verification & Resolved SHAs
Both selected action versions are published semver release tags under GitHub's official action repositories:
- **`actions/checkout@v6.0.2`**:
  - Official Release: [actions/checkout tag v6.0.2](https://github.com/actions/checkout/releases/tag/v6.0.2)
  - Release API: [api.github.com/repos/actions/checkout/releases/tags/v6.0.2](https://api.github.com/repos/actions/checkout/releases/tags/v6.0.2)
  - Upstream Immutability Status: GitHub Release API reports `"immutable": false`
  - Observed Resolved Git Commit: `de0fac2e4500dabe0009e67214ff5f5447ce83dd`
- **`actions/setup-python@v6.2.0`**:
  - Official Release: [actions/setup-python tag v6.2.0](https://github.com/actions/setup-python/releases/tag/v6.2.0)
  - Release API: [api.github.com/repos/actions/setup-python/releases/tags/v6.2.0](https://api.github.com/repos/actions/setup-python/releases/tags/v6.2.0)
  - Upstream Immutability Status: GitHub Release API reports `"immutable": false`
  - Observed Resolved Git Commit: `a309ff8b426b58ec0e2a45f0f869d46889d02405`

*Audit Note*: While upstream tags report `immutable: false` on the GitHub API, their resolved commit SHAs are recorded here to provide verifiable traceability without broadening the project scope into SHA-pinning changes in repository workflow files.

### 3.3 Scoped Compatibility Assessment of Actual Workflow Inputs
Rather than asserting universal schema equivalence across all possible configurations, compatibility is evaluated against the exact inputs and execution patterns used in this repository:

1. **`actions/checkout` (v4 -> v6.0.2)**:
   - *Workflow usage*:
     - `ci.yml`: default checkout (no custom inputs).
     - `release.yml`: `fetch-depth: 0` (for complete tag history during release packaging).
   - *Credential Storage Migration*:
     - [Checkout v6 Migration Documentation](https://github.com/actions/checkout/blob/v6.0.2/README.md) notes that authentication tokens now default to being stored in `$RUNNER_TEMP` rather than being persisted into `.git/config` within the workspace.
     - *Impact on our workflows*: Neither `ci.yml` nor `release.yml` uses git submodules, git push from non-action scripts, or downstream child processes requiring `.git/config` credentials. `ci.yml` runs offline Python test suites; `release.yml` packages artifacts via Python build and PowerShell compression. Credential storage in `$RUNNER_TEMP` is fully compatible and improves token isolation.
   - *Supported inputs*: `fetch-depth: 0` retains identical syntax and semantics in v6.0.2.

2. **`actions/setup-python` (v5 -> v6.2.0)**:
   - *Workflow usage*: Both `ci.yml` and `release.yml` specify:
     ```yaml
     with:
       python-version: "3.11"
       cache: "pip"
     ```
   - *Compatibility*:
     - [Setup-Python v6 Documentation](https://github.com/actions/setup-python/blob/v6.2.0/README.md) retains full backward compatibility for `python-version` and `cache: "pip"`.
     - Python 3.11 environment resolution, pip cache directory hashing, and tool cache hydration operate identically to v5.

3. **Runner Version Requirement & Non-Container Execution**:
   - *Minimum Runner Version*: Both `actions/checkout@v6.0.2` and `actions/setup-python@v6.2.0` require GitHub Actions runner version >= 2.327.1.
   - *Observed Runner Version*: In exact-head CI execution (runs 41801914949 and 41801914859), GitHub's hosted runner version was `2.338.2`, satisfying the minimum requirement.
   - *Non-Container Execution*: Both workflows execute directly on the host VM (`windows-latest` / Windows Server 2025) using native PowerShell and shell steps. They do not run inside containerized action steps (which require container runner daemon mapping for Node 24). Non-container execution remains fully compatible.

---

## 4. Preservation of Invariants

1. **Test Selection & Pytest Configuration (PR #86 / E02)**:
   In `.github/workflows/ci.yml`:
   ```yaml
   - name: Run unit tests
     run: python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" --cov=. --cov-report=xml
   ```
   This invocation remains unchanged. The explicit `-c pyproject.toml` configuration, `-m "not live_browser"` marker filter, and coverage flags are preserved.
2. **System Dependencies & Environment Paths**:
   Chocolatey installation of `ffmpeg` and `audacity`, along with PATH propagation (`"C:\ProgramData\chocolatey\bin" | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append`), remains unchanged.
3. **Release & Publication Boundaries**:
   `softprops/action-gh-release@v2` is explicitly preserved. No release dispatch or token elevation is introduced.

---

## 5. Byte & Preimage Archival Evidence

Preimages of modified workflow files were archived prior to edits into ignored storage:
- Storage path: `.runtime/ci_warning_triage_83_20261104/`
- Archive ledger: `.runtime/ci_warning_triage_83_20261104/ARCHIVES.json`

| File | Preimage Archive | SHA256 (Before = After) | Line Endings |
|---|---|---|---|
| `.github/workflows/ci.yml` | `.runtime/.../ci.yml.orig` | `079b73b1ffa719dded656387b8ee9e5ce51524321ea30dc783889c1d32838725` | Pure LF (`\n`) |
| `.github/workflows/release.yml` | `.runtime/.../release.yml.orig` | `d671cba3a95264fee69b5578db3bb6f39b0429c02528cd9120f54e9a36435ae3` | Pure LF (`\n`) |

Edits were applied in binary mode with strict LF line ending enforcement, resulting in zero whitespace warnings under `git diff --check`.

---

## 6. Exact-Head Verification Receipts & Warning Elimination Scope

### 6.1 Exact-Head CI Results (PR #88)
- **CI Test Suite**: [Run 41801914949](https://github.com/Snoozer10/local-youtube-automation/actions/runs/41801914949), [Job 126479485224](https://github.com/Snoozer10/local-youtube-automation/actions/runs/41801914949/job/126479485224)
  - Runner Version: `2.338.2`
  - Action Downloads:
    - `actions/checkout@v6.0.2` (SHA: `de0fac2e4500dabe0009e67214ff5f5447ce83dd`)
    - `actions/setup-python@v6.2.0` (SHA: `a309ff8b426b58ec0e2a45f0f869d46889d02405`)
  - Outcome: **PASS** (10m55s total duration)
  - Test Metrics: **2,369 passed, 2 skipped, 9 deselected in 263.82s (0:04:23)**
  - Deprecation Warning: **Zero warnings emitted**. The `Node.js 20 is deprecated` message was completely eliminated.
- **Documentation Onboarding**: [Run 41801914859](https://github.com/Snoozer10/local-youtube-automation/actions/runs/41801914859), [Job 126479483410](https://github.com/Snoozer10/local-youtube-automation/actions/runs/41801914859/job/126479483410)
  - Runner Version: `2.338.2`
  - Action Downloads: Identical SHAs resolved cleanly.
  - Outcome: **PASS** (6s duration)
  - Contract check: 7 documents checked, 9 contract tests passed.
- **CodeRabbit**: Skipped.

### 6.2 Scope Boundary & Residual Release Workflow Limitation
- **Observed Scope**: Warning elimination is confirmed for the active `ci.yml` (`test` job) and `docs.yml` (`onboarding` job) workflows on hosted runners.
- **Release Workflow Boundary**: `.github/workflows/release.yml` was not executed or qualified in this slice. In accordance with campaign safety invariants and offline limits, release publication remains unexecuted.
- **Residual Third-Party Action Limitation**: `softprops/action-gh-release@v2` was intentionally retained unchanged in `release.yml` to preserve existing release publication authority without unauthorized external action upgrades. Because `softprops/action-gh-release@v2` still targets Node.js 20, any future execution of `release.yml` will emit a Node 20 runtime deprecation warning until a separate release-upgrade slice evaluates and qualifies an updated release action.
