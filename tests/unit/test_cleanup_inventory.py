"""Unit tests for the automated cleanup candidate inventory scanner (tools/inventory_cleanup_candidates.py)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

try:
    import tomllib as available_toml
except ModuleNotFoundError:
    import tomli as available_toml

# Add tools/ to sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from inventory_cleanup_candidates import (  # noqa: E402
    audit_dependencies,
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


def test_collect_ast_imports_ignores_dot_dirs_above_repo_root(tmp_path: Path) -> None:
    repo_root = tmp_path / ".codex" / "worktrees" / "repo"
    src_dir = repo_root / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "app.py").write_text("import requests\n", encoding="utf-8")

    assert "requests" in collect_ast_imports(repo_root)


def test_scanner_falls_back_to_tomli_when_tomllib_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    scanner_path = TOOLS_DIR / "inventory_cleanup_candidates.py"
    spec = importlib.util.spec_from_file_location("cleanup_inventory_py310", scanner_path)
    assert spec is not None and spec.loader is not None
    scanner = importlib.util.module_from_spec(spec)
    tomli_stub = types.ModuleType("tomli")
    tomli_stub.load = available_toml.load
    monkeypatch.setitem(sys.modules, "tomllib", None)
    monkeypatch.setitem(sys.modules, "tomli", tomli_stub)
    spec.loader.exec_module(scanner)

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\ndependencies = ["requests>=2"]\n', encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("import requests\n", encoding="utf-8")

    assert scanner.tomllib is tomli_stub
    assert scanner.audit_dependencies(tmp_path) == []


def test_audit_dependencies_flags_phantom_deps(tmp_path: Path) -> None:
    # Create isolated pyproject.toml with phantom and active dependencies
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """[project]
name = "test-pkg"
version = "0.1.0"
dependencies = [
    "moviepy>=1.0.3",
    "pydantic>=2.0.0",
]
""",
        encoding="utf-8",
    )
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("import pydantic\n", encoding="utf-8")

    candidates = audit_dependencies(tmp_path)
    targets = [c["target"] for c in candidates]
    # moviepy must be flagged because it is not imported in app.py
    assert any("moviepy" in t for t in targets)
    # pydantic must NOT be flagged because it is imported
    assert not any("pydantic" in t for t in targets)

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
