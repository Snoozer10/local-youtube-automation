"""Tests for Issue #38 error cases, shallow index, and legacy preservation."""

import hashlib
import re
from pathlib import Path

LEGACY_UNDERSTOOD_ERRORS_SHA256 = (
    "73e0486215fc176f581acfc1832c61ec2b0939f7b505bc45a689762defd8dc39"
)

REQUIRED_SECTIONS = [
    "## Overview",
    "## 1. Verified Facts",
    "## 2. Hypotheses",
    "## 3. Attempts and Outcomes",
    "## 4. Remaining Gaps & False-Positive Boundaries",
    "## 5. Verified Prevention Check",
    "## 6. Evidence Links",
]

VALID_LAYERS = {
    "os.filesystem",
    "video.qsv",
    "audio.pipe",
    "speech.manifest",
    "browser.gemini",
    "pipeline.gate",
}

VALID_STATUSES = {"resolved", "mitigated", "active", "hypothesis"}


def test_legacy_understood_errors_exact_preservation():
    repo_root = Path(__file__).resolve().parents[2]
    legacy_file = repo_root / "docs" / "error-solving" / "understood-errors.md"
    assert legacy_file.is_file(), "Legacy understood-errors.md file missing"

    data = legacy_file.read_bytes()
    current_hash = hashlib.sha256(data).hexdigest()
    assert (
        current_hash == LEGACY_UNDERSTOOD_ERRORS_SHA256
    ), "Legacy understood-errors.md was mutated; historical evidence must be preserved"


def test_error_index_and_guidance_exist():
    repo_root = Path(__file__).resolve().parents[2]
    error_dir = repo_root / "docs" / "error-solving"

    readme = error_dir / "README.md"
    agents = error_dir / "AGENTS.md"
    template = error_dir / "TEMPLATE.md"

    assert readme.is_file(), "docs/error-solving/README.md index is missing"
    assert agents.is_file(), "docs/error-solving/AGENTS.md guidance is missing"
    assert template.is_file(), "docs/error-solving/TEMPLATE.md template is missing"

    # Verify all internal markdown links resolve
    for doc in (readme, agents, template):
        text = doc.read_text(encoding="utf-8")
        links = re.findall(r"\[.*?\]\(([^)#\s]+)(?:#[^)]*)?\)", text)
        for link in links:
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            target_path = (doc.parent / link).resolve()
            assert target_path.exists(), f"Broken file link in {doc.name}: {link}"


def test_migrated_cases_follow_template_structure():
    repo_root = Path(__file__).resolve().parents[2]
    cases_dir = repo_root / "docs" / "error-solving" / "cases"
    assert cases_dir.is_dir(), "docs/error-solving/cases directory is missing"

    case_files = sorted(cases_dir.glob("ERR-*.md"))
    assert len(case_files) >= 5, f"Expected at least 5 migrated cases, found {len(case_files)}"

    for case_file in case_files:
        content = case_file.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            assert section in content, f"Case {case_file.name} missing required section: {section}"

        assert "- **Responsible Layer**:" in content, f"Case {case_file.name} missing Responsible Layer"
        assert "- **Status**:" in content, f"Case {case_file.name} missing Status"


def test_representative_error_descriptions_retrieve_case_and_layer():
    repo_root = Path(__file__).resolve().parents[2]
    cases_dir = repo_root / "docs" / "error-solving" / "cases"

    test_queries = [
        ("-2147219196 Explorer.EXE failed on long path", "ERR-001", "os.filesystem"),
        ("QSV lookahead stream corruption NAL size", "ERR-002", "video.qsv"),
        ("Audacity named pipe leading newline desync BatchCommand", "ERR-003", "audio.pipe"),
        ("Whisper alignment ghost word extrapolation drift", "ERR-004", "speech.manifest"),
        ("Gemini thinking indicator substring false-positive", "ERR-005", "browser.gemini"),
    ]

    # Index case terms
    case_data = {}
    for case_file in cases_dir.glob("ERR-*.md"):
        text = case_file.read_text(encoding="utf-8")
        case_id = case_file.name.split("-")[0] + "-" + case_file.name.split("-")[1]
        layer_match = re.search(r"- \*\*Responsible Layer\*\*:\s*([a-zA-Z0-9_\-.]+)", text)
        layer = layer_match.group(1) if layer_match else "unknown"
        case_data[case_id] = {"text": text.lower(), "layer": layer}

    for query, expected_id, expected_layer in test_queries:
        query_words = set(query.lower().split())
        matched_id = None
        best_score = 0
        for cid, data in case_data.items():
            score = sum(1 for word in query_words if word in data["text"])
            if score > best_score:
                best_score = score
                matched_id = cid

        assert matched_id == expected_id, f"Query '{query}' failed to retrieve {expected_id} (got {matched_id})"
        assert case_data[matched_id]["layer"] == expected_layer, f"Matched case layer mismatch: {case_data[matched_id]['layer']} != {expected_layer}"


def test_cases_and_index_bidirectional_sync():
    """Verify cases are indexed in README, links resolve, and layer/status enums are valid."""
    repo_root = Path(__file__).resolve().parents[2]
    error_dir = repo_root / "docs" / "error-solving"
    readme_text = (error_dir / "README.md").read_text(encoding="utf-8")
    case_files = sorted((error_dir / "cases").glob("ERR-*.md"))

    assert len(case_files) >= 5, "Expected at least 5 case files"

    for cf in case_files:
        assert cf.name in readme_text, f"Orphan case file not indexed in README.md: {cf.name}"

        content = cf.read_text(encoding="utf-8")
        links = re.findall(r"\[.*?\]\(([^)#\s]+)(?:#[^)]*)?\)", content)
        for link in links:
            if not link.startswith(("http://", "https://", "mailto:")):
                target = (cf.parent / link).resolve()
                assert target.exists(), f"Broken link in {cf.name}: {link}"

        layer_match = re.search(r"- \*\*Responsible Layer\*\*:\s*([a-zA-Z0-9_\-.]+)", content)
        status_match = re.search(r"- \*\*Status\*\*:\s*([a-zA-Z0-9_\-.]+)", content)
        assert layer_match, f"Missing Responsible Layer in {cf.name}"
        assert layer_match.group(1) in VALID_LAYERS, f"Invalid layer '{layer_match.group(1)}' in {cf.name}"
        assert status_match, f"Missing Status in {cf.name}"
        assert status_match.group(1) in VALID_STATUSES, f"Invalid status '{status_match.group(1)}' in {cf.name}"


def test_legacy_resolution_map_anchors_exist():
    """Verify all anchors in README.md resolution map physically exist in understood-errors.md."""
    repo_root = Path(__file__).resolve().parents[2]
    error_dir = repo_root / "docs" / "error-solving"
    readme_text = (error_dir / "README.md").read_text(encoding="utf-8")
    legacy_text = (error_dir / "understood-errors.md").read_text(encoding="utf-8")

    mapped_anchors = re.findall(r"understood-errors\.md#([a-zA-Z0-9_\-]+)", readme_text)
    assert len(mapped_anchors) >= 5, "Expected at least 5 mapped anchors in README.md"

    headings = re.findall(r"^#{2,4}\s+(.+)$", legacy_text, flags=re.MULTILINE)
    slugs = set()
    for h in headings:
        slug = re.sub(r"[^\w\s-]", "", h.lower()).strip().replace(" ", "-")
        slugs.add(slug)

    for anchor in mapped_anchors:
        assert anchor in slugs, f"Resolution map anchor '{anchor}' does not match any heading in understood-errors.md"
