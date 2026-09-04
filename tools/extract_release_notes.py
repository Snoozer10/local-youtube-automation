"""
extract_release_notes.py

Deterministic utility to slice out a specific version's release notes from CHANGELOG.md.
Adheres strictly to Keep a Changelog 1.1.0 format without capturing [Unreleased] or older releases.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def extract_release_notes(
    changelog_text: str,
    version: str,
    include_header: bool = False,
) -> str:
    """
    Deterministically extracts release notes for a target version from CHANGELOG markdown.

    Args:
        changelog_text: The complete raw text of CHANGELOG.md.
        version: Target version string, with or without leading 'v' (e.g., '4.1.0' or 'v4.1.0').
        include_header: If True, includes the '## [version] - date' header line in the output.

    Returns:
        The clean Markdown text of the target release section.

    Raises:
        ValueError: If the target version section is not found in the changelog.
    """
    norm = changelog_text.replace("\r\n", "\n")
    clean_version = version.lstrip("v").strip()

    if include_header:
        pattern = rf"(?ms)(^## \[{re.escape(clean_version)}\](?:[^\n]*)\n.*?)(?=^## \[|\Z)"
    else:
        pattern = rf"(?ms)^## \[{re.escape(clean_version)}\](?:[^\n]*)\n(.*?)(?=^## \[|\Z)"

    match = re.search(pattern, norm)
    if not match:
        raise ValueError(
            f"Target version '[{clean_version}]' was not found in the provided changelog."
        )

    return match.group(1).strip()


def build_full_release_markdown(
    version: str,
    changelog_section: str,
    repo: str = "Snoozer10/local-youtube-automation",
) -> str:
    """
    Constructs a production-grade GitHub Release Markdown body conforming to
    shipping-and-launch and documentation-and-adrs standards.
    """
    clean_v = version.lstrip("v").strip()
    return f"""## Release v{clean_v}

### 🌟 Executive Summary
Version **v{clean_v}** introduces the **Canonical Timeline Engine** (`timeline.json`) as the single source of truth across all speech alignment, visual prompt extraction, and hardware video compilation stages. It hardens the automated Arabic educational video pipeline with **speech-paced dynamic Ken Burns zoom modulation**, **multi-layer OCR text collision gating** for AI visual harvesting, and **strict IPv4 loopback (`127.0.0.1:9222`) CDP browser automation**, guaranteeing zero-drift CFR video alignment and zero cloud SDK dependency.

---

### 📋 Changelog
{changelog_section}

---

### 📦 Assets & Downloads
| Filename | Type | Target Platform | SHA-256 Checksum |
| :--- | :--- | :--- | :--- |
| `youtube_automation_pipeline-{clean_v}-py3-none-any.whl` | Python Wheel | Python >=3.10 | *Compute with `Get-FileHash`* |
| `youtube-automation-pipeline-v{clean_v}-windows-x64.zip` | Standalone Portable Archive | Windows 10/11 x64 | *Compute with `Get-FileHash`* |
| `SHA256SUMS.txt` | Checksum Manifest | Universal | *Signed SHA-256 manifest* |

---

### 💻 System Prerequisites
Before running the pipeline, ensure the host system provides:
1. **Operating System**: Windows 10 or Windows 11 (64-bit).
2. **Python Environment**: Python 3.10 or 3.11 (Python 3.11 recommended).
3. **FFmpeg & FFprobe 5.0+**: With Intel QSV (`h264_qsv`) or NVIDIA NVENC (`h264_nvenc`) support.
   ```powershell
   winget install Gyan.FFmpeg
   ```
4. **Audacity 3.x+**: With `mod-script-pipe` enabled for Named Pipes DSP mastering (`Edit` → `Preferences` → `Modules` → `mod-script-pipe: Enabled`).
5. **Google Chrome / Chromium**: Launched with remote debugging port on loopback:
   ```powershell
   chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\ChromeDebugProfile"
   ```

---

### 🚀 Quickstart Guide

#### Option A: Portable / Source Setup
```powershell
# 1. Clone or extract release archive
cd youtube-automation-pipeline

# 2. Initialize virtual environment
python -m venv venv
.\\venv\\Scripts\\Activate.ps1

# 3. Install core dependencies
pip install -r requirements.txt
python -m playwright install chromium

# 4. Run supervisor batch pipeline
python run_agency.py
```

#### Option B: Wheel Installation
```powershell
pip install youtube_automation_pipeline-{clean_v}-py3-none-any.whl
python -m playwright install chromium
```

---

### 🔒 Architectural Decision Records (ADRs)
- [ADR 0001: Timeline Unification & Canonical SSOT](https://github.com/{repo}/blob/v{clean_v}/docs/adr/0001-timeline-unification.md)
- [ADR 0002: Hardware-Accelerated Video Encoding Ladder](https://github.com/{repo}/blob/v{clean_v}/docs/adr/0002-encoding-ladder.md)
- [ADR 0003: 3-Span Windowed Storyboard & Prompt Extraction](https://github.com/{repo}/blob/v{clean_v}/docs/adr/0003-prompt-extraction.md)
- [ADR 0004: Multi-Layer OCR Text Collision Gate](https://github.com/{repo}/blob/v{clean_v}/docs/adr/0004-text-collision-gate.md)
- [ADR 0005: Lossless Audacity Named Pipes DSP Contract](https://github.com/{repo}/blob/v{clean_v}/docs/adr/0005-audio-dsp-contract.md)
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministically slice release notes from CHANGELOG.md"
    )
    parser.add_argument(
        "version",
        help="Target version to slice (e.g. '4.1.0' or 'v4.1.0')",
    )
    parser.add_argument(
        "--changelog",
        "-c",
        default="CHANGELOG.md",
        help="Path to CHANGELOG.md (default: CHANGELOG.md)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Path to write output markdown file (default: stdout)",
    )
    parser.add_argument(
        "--include-header",
        action="store_true",
        help="Include the ## [version] - date header line in output",
    )
    parser.add_argument(
        "--full-release",
        action="store_true",
        help="Generate a complete production GitHub Release notes body",
    )
    parser.add_argument(
        "--repo",
        default="Snoozer10/local-youtube-automation",
        help="GitHub repository slug (default: Snoozer10/local-youtube-automation)",
    )

    args = parser.parse_args()

    changelog_path = Path(args.changelog)
    if not changelog_path.is_file():
        sys.stderr.write(f"Error: Changelog file not found at '{changelog_path}'\n")
        sys.exit(1)

    try:
        raw_text = changelog_path.read_text(encoding="utf-8")
        extracted = extract_release_notes(
            raw_text,
            args.version,
            include_header=args.include_header,
        )

        if args.full_release:
            final_output = build_full_release_markdown(
                args.version,
                extracted,
                repo=args.repo,
            )
        else:
            final_output = extracted

        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(final_output, encoding="utf-8")
            print(f"[SUCCESS] Release notes written to: {out_path}")
        else:
            sys.stdout.reconfigure(encoding="utf-8")
            print(final_output)

    except Exception as exc:
        sys.stderr.write(f"Extraction Error: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
