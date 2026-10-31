"""Unit tests for the automated cleanup candidate inventory scanner (tools/inventory_cleanup_candidates.py)."""

from __future__ import annotations

import sys
from pathlib import Path

# Add tools/ to sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from inventory_cleanup_candidates import (  # noqa: E402
    audit_dependencies,
    audit_legacy_utilities,
    audit_root_shims,
    collect_ast_imports,
    compute_sha256,
    generate_inventory,
)


def test_compute_sha256(tmp_path: Path) -> None:
    test_file = tmp_path / "hello.txt"
    test_file.write_bytes(b"hello world\n")
    expected = "a948904f2f0f479b8f8197694b30184b0d2ed1c1cd2a1ec0fb85d299a192a447"
    assert compute_sha256(test_file) == expected
    assert compute_sha256(tmp_path / "missing.txt") == ""


def test_collect_ast_imports_ignores_dot_dirs(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("import json\nfrom pathlib import Path\n")

    dot_dir = tmp_path / ".agents" / "skills"
    dot_dir.mkdir(parents=True)
    (dot_dir / "hidden.py").write_text("import torchaudio\n")

    imports = collect_ast_imports(tmp_path)
    assert "json" in imports
    assert "pathlib" in imports
    assert "torchaudio" not in imports  # correctly skipped .agents directory


def test_audit_dependencies_flags_phantom_deps() -> None:
    candidates = audit_dependencies(REPO_ROOT)
    targets = [c["target"] for c in candidates]
    # moviepy and torchaudio must be flagged as phantom dependencies
    assert any("moviepy" in t for t in targets)
    assert any("torchaudio" in t for t in targets)

    for c in candidates:
        assert c["category"] == "phantom_dependency"
        assert c["safety_tier"] == "TIER_3_DISPOSABLE"
        assert c["action"] == "PRUNE"


def test_audit_root_shims_are_tier_1_immutable() -> None:
    shims = audit_root_shims(REPO_ROOT)
    assert len(shims) >= 20
    for shim in shims:
        assert shim["safety_tier"] == "TIER_1_IMMUTABLE"
        assert shim["action"] == "KEEP_PERMANENT"
        assert shim["category"] == "root_compatibility_shim"


def test_generate_inventory_full_schema() -> None:
    inventory = generate_inventory(REPO_ROOT)
    assert "timestamp" in inventory
    assert "repo_root" in inventory
    assert inventory["total_audited"] > 0
    assert inventory["total_prune_candidates"] > 0
    assert isinstance(inventory["candidates"], list)

    for c in inventory["candidates"]:
        assert "target" in c
        assert "safety_tier" in c
        assert "confidence" in c
        assert "action" in c
        assert "verification_gate_command" in c
        assert "rollback_complexity" in c
        assert "sha256_hash" in c
