"""
test_extract_release_notes.py

Unit tests for deterministic release notes extraction from CHANGELOG.md.
"""

import pytest

from tools.extract_release_notes import build_full_release_markdown, extract_release_notes

SAMPLE_CHANGELOG = """# Changelog

All notable changes to the `youtube-automation-pipeline` project will be documented in this file.

## [Unreleased]

### Added
- Unreleased feature XYZ

## [4.1.0] - 2026-09-04

### Added
- Feature A in 4.1.0
- Feature B in 4.1.0

### Changed
- Refactor C in 4.1.0

### Fixed
- Bug D in 4.1.0

## [4.0.0] - 2026-09-03

### Added
- Initial pipeline release v4.0.0
"""


def test_extract_release_notes_exact_version():
    extracted = extract_release_notes(SAMPLE_CHANGELOG, "4.1.0")
    assert "Feature A in 4.1.0" in extracted
    assert "Feature B in 4.1.0" in extracted
    assert "Refactor C in 4.1.0" in extracted
    assert "Bug D in 4.1.0" in extracted

    # Strictly assert that Unreleased and 4.0.0 sections are excluded
    assert "Unreleased" not in extracted
    assert "XYZ" not in extracted
    assert "4.0.0" not in extracted
    assert "Initial pipeline release" not in extracted


def test_extract_release_notes_with_v_prefix():
    extracted = extract_release_notes(SAMPLE_CHANGELOG, "v4.1.0")
    assert "Feature A in 4.1.0" in extracted
    assert "4.0.0" not in extracted


def test_extract_release_notes_with_header():
    extracted = extract_release_notes(SAMPLE_CHANGELOG, "4.1.0", include_header=True)
    assert extracted.startswith("## [4.1.0] - 2026-09-04")
    assert "Bug D in 4.1.0" in extracted
    assert "4.0.0" not in extracted


def test_extract_release_notes_last_entry_at_eof():
    extracted = extract_release_notes(SAMPLE_CHANGELOG, "4.0.0")
    assert "Initial pipeline release v4.0.0" in extracted
    assert "4.1.0" not in extracted


def test_extract_release_notes_missing_version_raises():
    with pytest.raises(ValueError, match=r"Target version '\[99\.99\.99\]' was not found"):
        extract_release_notes(SAMPLE_CHANGELOG, "99.99.99")


def test_extract_from_actual_project_changelog():
    from pathlib import Path

    changelog_file = Path("CHANGELOG.md")
    assert changelog_file.exists()
    content = changelog_file.read_text(encoding="utf-8")

    extracted_410 = extract_release_notes(content, "4.1.0")
    assert "Canonical Timeline SSOT" in extracted_410
    assert "Speech-Paced Ken Burns Modulation" in extracted_410
    assert "Unreleased" not in extracted_410
    assert "4.0.0" not in extracted_410

    # Test full release formatting
    full_body = build_full_release_markdown("4.1.0", extracted_410)
    assert "## Release v4.1.0" in full_body
    assert "### 🌟 Executive Summary" in full_body
    assert "### 💻 System Prerequisites" in full_body
    assert "Canonical Timeline SSOT" in full_body
