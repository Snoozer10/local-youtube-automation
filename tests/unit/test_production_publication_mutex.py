import subprocess
import sys
from pathlib import Path

import pytest

from youtube_automation.production import ledger


@pytest.mark.parametrize("custom_claim", [False, True])
def test_direct_process_and_custom_claim_share_fixed_publication_mutex(tmp_path, custom_claim):
    from contextlib import nullcontext

    database = ledger.resource_database()
    marker = tmp_path / "incorrect-entry"
    source = Path(__file__).resolve().parents[2] / "src"
    code = f'''
import sqlite3, sys
from pathlib import Path
sys.path.insert(0, {str(source)!r})
from youtube_automation.production import ledger
ledger.resource_database = lambda: Path({str(database)!r})
real_connect = sqlite3.connect
def fail_fast_connect(*args, **kwargs):
    kwargs["timeout"] = 0
    return real_connect(*args, **kwargs)
sqlite3.connect = fail_fast_connect
try:
    with ledger.publication_guard():
        Path({str(marker)!r}).write_text("unserialized")
except sqlite3.OperationalError as error:
    if "locked" not in str(error):
        raise
    print("BLOCKED", flush=True)
else:
    print("ENTERED", flush=True)
'''
    claim = ledger.leased_resource(tmp_path / "custom.sqlite3", "encoder") if custom_claim else nullcontext()
    with claim, ledger.publication_guard():
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "BLOCKED"
        assert not marker.exists()
    with ledger.publication_guard():
        marker.write_text("released")
    assert marker.read_text() == "released"


def test_direct_nested_guard_is_reentrant_and_exception_releases(tmp_path):
    with pytest.raises(RuntimeError, match="injected"):
        with ledger.publication_guard(), ledger.publication_guard():
            raise RuntimeError("injected")
    with ledger.publication_guard():
        (tmp_path / "released").write_text("okay")


def test_new_lease_is_rejected_inside_publication_before_database_work(tmp_path):
    with ledger.publication_guard(), pytest.raises(RuntimeError, match="publication"):
        with ledger.leased_resource(tmp_path / "never-created.sqlite3", "encoder"):
            pytest.fail("lease must not start while publication is locked")
    assert not (tmp_path / "never-created.sqlite3").exists()


def test_actual_installation_database_is_blocked_before_connect(isolated_shared_resource_paths):
    import sqlite3

    with pytest.raises(pytest.fail.Exception, match="real production SQLite connection"):
        sqlite3.connect(isolated_shared_resource_paths["production_database"])
