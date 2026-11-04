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
3. These versions are identical to the published, immutable release tags vetted in `.github/workflows/docs.yml` (added in PR #84, verified passing in 12s with zero warnings).
4. `softprops/action-gh-release@v2` in `.github/workflows/release.yml` is retained unchanged to preserve existing release publication authority without implied modification.
5. All E02 (PR #86) test-selection flags (`python -m pytest tests/unit tests/integration -c pyproject.toml -v -m "not live_browser" --cov=. --cov-report=xml`), explicit pytest configuration, live-browser exclusion, and isolation guards remain 100% intact.

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
No deprecation warnings or compatibility translations occurred.

---

## 3. Official Action Guidance & Version Matrix

### 3.1 Node Runtime Targets Across Major Releases
Inspection of official upstream `action.yml` manifests yields:

| Action | Major / Tag | Runtime Target | Status / Notes |
|---|---|---|---|
| `actions/checkout` | `v4` | `node20` | Deprecated; triggers forced execution warning on Node 24 |
| `actions/checkout` | `v5.1.0` | `node24` | Node 24 support; breaking changes to PR checkout defaults |
| `actions/checkout` | `v6.0.2` | `node24` | **Selected**: Vetted in `docs.yml`; input-compatible with v4; clean Node 24 execution |
| `actions/checkout` | `v7.0.1` | `node24` | Breaking changes (fork PR blocking on `pull_request_target`) |
| `actions/setup-python` | `v5` | `node20` | Deprecated; triggers forced execution warning on Node 24 |
| `actions/setup-python` | `v6.2.0` | `node24` | **Selected**: Vetted in `docs.yml`; input-compatible with v5; clean Node 24 execution |
| `actions/setup-python` | `v7.1.0` | `node24` | Breaking changes (removes `pip-install`, ESM migration) |
| `softprops/action-gh-release` | `v2` | `node20` | **Retained**: Third-party release tool; left untouched to preserve publication authority |

### 3.2 Input & Interface Compatibility Analysis
- **`actions/checkout`**:
  - `ci.yml` uses default checkout inputs (`actions/checkout@v4` -> `@v6.0.2`).
  - `release.yml` uses `fetch-depth: 0` (`actions/checkout@v4` -> `@v6.0.2`).
  - Verification: `fetch-depth`, `token`, `persist-credentials`, `clean`, `sparse-checkout-cone-mode` are 100% identical in schema and semantics.
- **`actions/setup-python`**:
  - Both `ci.yml` and `release.yml` use `python-version: "3.11"` and `cache: "pip"`.
  - Verification: `v6.2.0` preserves all `v5` inputs while adding optional `pip-version` and `pip-install`. The existing configuration is fully backward-compatible.
- **Windows Runner & Packaging Behavior**:
  - CI runner environment: `windows-latest` (Microsoft Windows Server 2025 Datacenter `windows-2025-vs2026`).
  - Release packaging: The PowerShell bundle script relies on standard Windows filesystem utilities (`Compress-Archive`, `System.IO.Compression.FileSystem`), `python -m build`, and `SHA256SUMS.txt` generation. None of these depend on action internal runtime mechanics beyond repository checkout and Python 3.11 environment initialization.

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
