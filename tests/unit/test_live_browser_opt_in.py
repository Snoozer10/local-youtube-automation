"""Offline checks for the explicit live-browser test collection gate."""

import ast
import os
import subprocess
import sys
from pathlib import Path

_MIXED_M1_LIVE_TESTS = {
    "test_01_live_cdp_targets_and_foreign_targets",
    "test_02_tab_hygiene_stress",
    "test_03_concurrent_http_loopback_stress",
    "test_04_websocket_loopback_concurrent_queries",
    "test_06_multi_connection_websocket_stress",
    "test_07_tab_churn_during_target_probing",
}
_MIXED_M1_OFFLINE_TESTS = {
    "test_05_foreign_targets_adversarial_oracle",
    "test_08_tab_hygiene_edge_cases",
}


def test_live_browser_gate_skips_before_fixture_or_body(tmp_path):
    tests_root = Path(__file__).resolve().parents[1]
    sentinel = tmp_path / "side_effects.txt"
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    # Export the real collection hooks only; repository autouse fixtures stay out
    # of this synthetic project, which has no real live-browser tests.
    (tmp_path / "conftest.py").write_text(
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('real_conftest', {str(tests_root / 'conftest.py')!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "pytest_addoption = module.pytest_addoption\n"
        "pytest_configure = module.pytest_configure\n"
        "pytest_collection_modifyitems = module.pytest_collection_modifyitems\n",
        encoding="utf-8",
    )
    (tmp_path / "test_synthetic.py").write_text(
        "import pytest\n"
        "from pathlib import Path\n"
        f"SENTINEL = Path({str(sentinel)!r})\n"
        "@pytest.fixture\n"
        "def side_effect():\n"
        "    SENTINEL.write_text('fixture\\n', encoding='utf-8')\n"
        "@pytest.mark.live_browser\n"
        "def test_synthetic_live(side_effect):\n"
        "    with SENTINEL.open('a', encoding='utf-8') as stream:\n"
        "        stream.write('body\\n')\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(tests_root), str(tests_root.parent), str(tests_root.parent / "src")]
    )
    command = [sys.executable, "-m", "pytest", "-q", "--tb=short", "-x"]
    default = subprocess.run(
        command, cwd=tmp_path, env=env, capture_output=True, text=True,
        timeout=30, check=False,
    )
    assert default.returncode == 0, default.stdout + default.stderr
    assert "1 skipped" in default.stdout
    assert not sentinel.exists(), "live fixture or test ran without opt-in"
    opted_in = subprocess.run(
        [*command, "--run-live-browser"], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert opted_in.returncode == 0, opted_in.stdout + opted_in.stderr
    assert "1 passed" in opted_in.stdout
    assert sentinel.read_text(encoding="utf-8") == "fixture\nbody\n"


def test_live_case_modules_keep_explicit_collection_classification():
    tests_root = Path(__file__).resolve().parents[1]
    mixed_path = tests_root / "integration" / "test_m1_adversarial_challenge.py"
    live_path = tests_root / "integration" / "test_empirical_m1_live.py"

    mixed_functions = {
        node.name: node
        for node in ast.parse(mixed_path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }
    assert set(mixed_functions) == _MIXED_M1_LIVE_TESTS | _MIXED_M1_OFFLINE_TESTS
    for name in _MIXED_M1_LIVE_TESTS:
        assert any(
            isinstance(decorator, ast.Attribute)
            and decorator.attr == "live_browser"
            for decorator in mixed_functions[name].decorator_list
        )

    live_functions = [
        node
        for node in ast.parse(live_path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    assert live_functions
    assert all(
        any(
            isinstance(decorator, ast.Attribute)
            and decorator.attr == "live_browser"
            for decorator in node.decorator_list
        )
        for node in live_functions
    )
