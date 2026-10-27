"""Tests for Issue #39: Canonical skill provenance, task bindings, and platform discovery."""

import json
from pathlib import Path


def test_skill_lock_files_valid_and_structured():
    repo_root = Path(__file__).resolve().parents[2]
    skill_lock_path = repo_root / "skill-lock.json"
    skills_lock_path = repo_root / "skills-lock.json"

    assert skill_lock_path.is_file(), "skill-lock.json missing from root"
    assert skills_lock_path.is_file(), "skills-lock.json missing from root"

    skill_lock = json.loads(skill_lock_path.read_text(encoding="utf-8"))
    skills_lock = json.loads(skills_lock_path.read_text(encoding="utf-8"))

    assert skill_lock.get("version") == 1
    assert len(skill_lock.get("task_bindings", {})) == 52
    assert len(skill_lock.get("bound_skills", [])) == 24
    assert len(skill_lock.get("active_project_skills", [])) == 109
    assert len(skill_lock.get("archived_skills", [])) == 21

    assert skills_lock.get("version") == 1
    assert len(skills_lock.get("skills", {})) == 29


def test_all_task_bindings_reference_catalogued_skills():
    repo_root = Path(__file__).resolve().parents[2]
    skill_lock = json.loads((repo_root / "skill-lock.json").read_text(encoding="utf-8"))

    bound_set = set(skill_lock["bound_skills"])
    active_set = {s["name"] for s in skill_lock["active_project_skills"] if isinstance(s, dict) and "name" in s}
    all_known = bound_set | active_set

    for task_id, binding in skill_lock["task_bindings"].items():
        skills_for_task = binding.get("skills", [])
        assert len(skills_for_task) > 0, f"Task {task_id} has empty skills binding"
        for s in skills_for_task:
            assert s in all_known, f"Task {task_id} references uncatalogued skill: {s}"


def test_claude_skills_exist_and_readable():
    repo_root = Path(__file__).resolve().parents[2]
    claude_skills_dir = repo_root / ".claude" / "skills"

    assert claude_skills_dir.is_dir(), ".claude/skills directory missing"
    skill_subdirs = [p for p in claude_skills_dir.iterdir() if p.is_dir()]
    assert len(skill_subdirs) == 14, f"Expected 14 Claude skills, found {len(skill_subdirs)}"

    for sdir in skill_subdirs:
        skill_file = sdir / "SKILL.md"
        assert skill_file.is_file(), f"Missing SKILL.md in {sdir.name}"
        assert len(skill_file.read_text(encoding="utf-8").strip()) > 0, f"Empty SKILL.md in {sdir.name}"


def test_skills_lock_records_provenance_and_hashes():
    repo_root = Path(__file__).resolve().parents[2]
    skills_lock = json.loads((repo_root / "skills-lock.json").read_text(encoding="utf-8"))

    for skill_name, info in skills_lock["skills"].items():
        assert "source" in info and len(info["source"]) > 0, f"{skill_name} missing source"
        assert "computedHash" in info and len(info["computedHash"]) == 64, f"{skill_name} missing computed SHA-256 hash"


def test_provenance_and_discovery_document_completeness():
    repo_root = Path(__file__).resolve().parents[2]
    doc_path = repo_root / "docs" / "skills" / "PROVENANCE_AND_DISCOVERY.md"

    assert doc_path.is_file(), "docs/skills/PROVENANCE_AND_DISCOVERY.md missing"
    content = doc_path.read_text(encoding="utf-8")

    required_sections = [
        "## 1. Authority and Lock Files",
        "## 2. Active Platform Discovery Surfaces",
        "## 3. Bound Skills and Task Coverage",
        "## 4. Bounded Consolidation and Redundancy Verification",
        "## 5. Restoration Mapping and Re-check Procedure",
        "## 6. Explicit Platform Limitations and Gaps",
    ]

    for section in required_sections:
        assert section in content, f"Missing required section: {section}"

    # Explicit recorded gaps
    assert "Codex" in content and "<0.160" in content, "Codex <0.160 selection gap not documented"
    assert ".agents/" in content and "gitignored" in content, ".agents/ gitignored convention not documented"
