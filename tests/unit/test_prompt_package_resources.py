"""Regression coverage for prompt resources in installed package layouts."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PROMPTS = ROOT / "prompts"
PACKAGE = ROOT / "src" / "youtube_automation" / "prompts"


def _prompt_assets(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*.txt"))
        if path.is_file()
    }


def test_packaged_prompt_assets_match_every_source_template() -> None:
    source_assets = _prompt_assets(SOURCE_PROMPTS)
    package_assets = _prompt_assets(PACKAGE)

    assert source_assets
    assert package_assets == source_assets


def test_prompt_loader_reads_installed_package_resources_outside_checkout(
    tmp_path: Path,
) -> None:
    installed_root = tmp_path / "site-packages"
    installed_root.mkdir()
    shutil.copytree(ROOT / "src" / "youtube_automation", installed_root / "youtube_automation")
    decoy_prompts = tmp_path / "prompts"
    decoy_prompts.mkdir()
    (decoy_prompts / "phase1.txt").write_text("not the installed package prompt", encoding="utf-8")
    outside_checkout = tmp_path / "outside"
    outside_checkout.mkdir()

    probe = """
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from youtube_automation.prompts import loader

assert loader.PROMPTS_DIR == Path(loader.__file__).parent
assert loader.load('phase1').name == 'phase1'
assert loader.render('phase1')
assert loader.fragment('safety_disclaimer')
assert loader.turn('phase3', 'turn')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(installed_root)],
        cwd=outside_checkout,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
