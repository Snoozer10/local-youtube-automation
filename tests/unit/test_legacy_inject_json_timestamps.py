"""Compatibility regressions for the deprecated legacy timestamp injector."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LEGACY_SCRIPT = REPOSITORY_ROOT / "legacy_and_utilities" / "inject_json_timestamps.py"


def _write_prompt(directory: Path, timestamp: str = "[99:59]") -> None:
    (directory / "flow_prompts.json").write_text(
        json.dumps([{"index": 1, "timestamp": timestamp}]), encoding="utf-8"
    )


def _read_timestamp(directory: Path) -> str:
    return json.loads((directory / "flow_prompts.json").read_text(encoding="utf-8"))[0][
        "timestamp"
    ]


def _run_cli(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LEGACY_SCRIPT)],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


@pytest.mark.unit
def test_cli_prefers_current_directory_and_leaves_other_runs_untouched(tmp_path: Path) -> None:
    (tmp_path / "image_timestamps.txt").write_text("[00:07] local timing\n", encoding="utf-8")
    _write_prompt(tmp_path)

    run_dirs = [tmp_path / "youtube_runs" / name for name in ("older", "newer")]
    for run_dir in run_dirs:
        run_dir.mkdir(parents=True)
        (run_dir / "timestamped_transcript.txt").write_text(
            "[00:33] run timing\n", encoding="utf-8"
        )
        _write_prompt(run_dir)

    result = _run_cli(tmp_path)

    assert result.returncode == 0, result.stderr
    assert _read_timestamp(tmp_path) == "[00:07]"
    assert [_read_timestamp(run_dir) for run_dir in run_dirs] == ["[99:59]", "[99:59]"]


@pytest.mark.unit
def test_cli_falls_back_to_newest_run_only(tmp_path: Path) -> None:
    older, newer = (tmp_path / "youtube_runs" / name for name in ("older", "newer"))
    older.mkdir(parents=True)
    newer.mkdir()
    for run_dir, stamp in ((older, "[00:11]"), (newer, "[00:22]")):
        (run_dir / "image_timestamps.txt").write_text(f"{stamp} run timing\n", encoding="utf-8")
        _write_prompt(run_dir)
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    result = _run_cli(tmp_path)

    assert result.returncode == 0, result.stderr
    assert _read_timestamp(older) == "[99:59]"
    assert _read_timestamp(newer) == "[00:22]"


@pytest.mark.unit
def test_legacy_import_api_remains_available() -> None:
    spec = importlib.util.spec_from_file_location("legacy_timestamp_injector", LEGACY_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    with pytest.warns(FutureWarning, match="deprecated"):
        spec.loader.exec_module(module)

    assert callable(module.get_target_directory)
    assert callable(module.parse_image_timestamps)
    assert callable(module.sanitize_json_content)
    assert callable(module.load_flow_prompts_json)
    assert callable(module.inject_timestamps)
