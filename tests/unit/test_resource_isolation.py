import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from youtube_automation.core import utils
from youtube_automation.production import ledger


def _fingerprint(path: Path) -> tuple[int, str] | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return path.stat().st_size, digest.hexdigest()


def _production_resource_state(database: Path, registry: Path) -> dict[str, tuple[int, str] | None]:
    paths = [database, registry]
    paths.extend(Path(f"{database}{suffix}") for suffix in ("-journal", "-wal", "-shm"))
    return {str(path): _fingerprint(path) for path in paths}


def test_shared_resource_paths_are_local_and_leases_release(isolated_shared_resource_paths):
    paths = isolated_shared_resource_paths
    production_before = _production_resource_state(
        paths["production_database"], paths["production_registry"]
    )

    assert ledger.resource_database() == paths["database"]
    assert utils.OWNED_BROWSER_REGISTRY == paths["registry"]

    with ledger.leased_resource(paths["database"], "browser"):
        pass

    with pytest.raises(ValueError, match="exercise exception cleanup"):
        with ledger.leased_resource(paths["database"], "browser"):
            raise ValueError("exercise exception cleanup")

    # A fresh claim after both exits proves success and exception paths released the lease.
    with ledger.leased_resource(paths["database"], "browser"):
        pass

    utils._write_owned_browsers({"9222": {"pid": 12345}})
    assert utils._read_owned_browsers() == {"9222": {"pid": 12345}}
    assert paths["registry"].is_file()
    assert _production_resource_state(
        paths["production_database"], paths["production_registry"]
    ) == production_before



_LATE_ALIAS_MODULE = "_test_resource_isolation_late_alias"


def _seed_delayed_import_aliases(isolated_shared_resource_paths):
    import sys
    from types import ModuleType

    paths = isolated_shared_resource_paths
    production_before = _production_resource_state(
        paths["production_database"], paths["production_registry"]
    )

    module = ModuleType(_LATE_ALIAS_MODULE)
    module.resource_database = ledger.resource_database
    module.OWNED_BROWSER_REGISTRY = utils.OWNED_BROWSER_REGISTRY
    module.first_database = module.resource_database()
    module.first_registry = module.OWNED_BROWSER_REGISTRY
    sys.modules[_LATE_ALIAS_MODULE] = module

    assert module.first_database == paths["database"]
    assert module.first_registry == paths["registry"]
    with ledger.leased_resource(module.resource_database(), "delayed-import"):
        pass
    module.OWNED_BROWSER_REGISTRY.write_text('{"9222": {"pid": 12345}}', encoding="utf-8")

    assert module.first_database.is_file()
    assert module.first_registry.is_file()
    assert _production_resource_state(
        paths["production_database"], paths["production_registry"]
    ) == production_before


def _assert_successive_alias_rebind(isolated_shared_resource_paths):
    import sys

    paths = isolated_shared_resource_paths
    production_before = _production_resource_state(
        paths["production_database"], paths["production_registry"]
    )
    module = sys.modules[_LATE_ALIAS_MODULE]

    assert module.resource_database is ledger.resource_database
    assert module.resource_database() == paths["database"]
    assert module.resource_database() != module.first_database
    assert module.OWNED_BROWSER_REGISTRY == paths["registry"]
    assert module.OWNED_BROWSER_REGISTRY != module.first_registry

    with ledger.leased_resource(module.resource_database(), "successive-test"):
        pass
    module.OWNED_BROWSER_REGISTRY.write_text('{"9222": {"pid": 54321}}', encoding="utf-8")

    assert _production_resource_state(
        paths["production_database"], paths["production_registry"]
    ) == production_before


def test_delayed_aliases_rebind_in_self_contained_successive_cases(tmp_path):
    """Exercise two real fixture lifecycles without relying on parent test order."""
    tests_root = Path(__file__).resolve().parents[1]
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('real_conftest', {str(tests_root / 'conftest.py')!r})\n"
        "real = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(real)\n"
        "isolated_shared_resource_paths = real.isolated_shared_resource_paths\n"
        "pytest_sessionstart = real.pytest_sessionstart\n"
        "pytest_sessionfinish = real.pytest_sessionfinish\n"
        "pytest_addoption = real.pytest_addoption\n"
        "pytest_configure = real.pytest_configure\n"
        "pytest_collection_modifyitems = real.pytest_collection_modifyitems\n",
        encoding="utf-8",
    )
    (tmp_path / "test_successive.py").write_text(
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('resource_regression', {str(Path(__file__).resolve())!r})\n"
        "regression = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(regression)\n"
        "def test_first(isolated_shared_resource_paths):\n"
        "    regression._seed_delayed_import_aliases(isolated_shared_resource_paths)\n"
        "def test_second(isolated_shared_resource_paths):\n"
        "    regression._assert_successive_alias_rebind(isolated_shared_resource_paths)\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(tests_root), str(tests_root.parent), str(tests_root.parent / "src")]
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short", "-x"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
