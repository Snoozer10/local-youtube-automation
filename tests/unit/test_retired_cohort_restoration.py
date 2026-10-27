"""Tests for Issue #41: Verification of retired non-runtime cohort and reversible recovery."""

import hashlib
import json
import shutil
from pathlib import Path


def test_retired_cohort_files_absent_from_tools():
    repo_root = Path(__file__).resolve().parents[2]
    tools_dir = repo_root / "tools"

    retired_files = [
        "check_project_9320.py",
        "check_h10_project.py",
        "inspect_h10_prompts.py",
        "test_banana_21.py",
        "test_banana_pro.py",
        "test_raw_cdp.py",
        "test_cdp_quick.py",
    ]

    for fname in retired_files:
        p = tools_dir / fname
        assert not p.exists(), f"Retired file still exists in tools/: {fname}"


def test_retired_cohort_receipt_and_preimages_integrity():
    repo_root = Path(__file__).resolve().parents[2]
    receipt_path = repo_root / "evidence" / "receipts" / "RETIRED_COHORT_TOOLS_SCRATCH.json"

    assert receipt_path.is_file(), "Missing retirement receipt"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert receipt["issue"] == 41
    assert receipt["cohort"] == "tools_adhoc_browser_and_run_scratch"
    assert receipt["status"] == "RETIRED"
    assert len(receipt["files"]) == 7

    for entry in receipt["files"]:
        preimage = repo_root / entry["preimage_path"]
        assert preimage.is_file(), f"Preimage missing: {preimage}"
        data = preimage.read_bytes()
        actual_sha = hashlib.sha256(data).hexdigest()
        assert actual_sha == entry["sha256"], f"Preimage SHA mismatch for {entry['path']}"
        assert len(data) == entry["size_bytes"], f"Preimage size mismatch for {entry['path']}"


def test_tools_agents_guidance_records_retirement():
    repo_root = Path(__file__).resolve().parents[2]
    agents_path = repo_root / "tools" / "AGENTS.md"

    assert agents_path.is_file(), "tools/AGENTS.md missing"
    content = agents_path.read_text(encoding="utf-8")
    assert "## Retired Cohorts" in content
    assert "RETIRED_COHORT_TOOLS_SCRATCH.json" in content


def test_demonstrate_reversible_restoration_to_temp_directory(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    receipt_path = repo_root / "evidence" / "receipts" / "RETIRED_COHORT_TOOLS_SCRATCH.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    restored_dir = tmp_path / "restored_tools"
    restored_dir.mkdir(parents=True, exist_ok=True)

    for entry in receipt["files"]:
        preimage = repo_root / entry["preimage_path"]
        target = restored_dir / Path(entry["path"]).name
        shutil.copy2(preimage, target)

        restored_data = target.read_bytes()
        restored_sha = hashlib.sha256(restored_data).hexdigest()
        assert restored_sha == entry["sha256"], f"Restored file SHA mismatch: {target.name}"

    assert len(list(restored_dir.iterdir())) == 7
