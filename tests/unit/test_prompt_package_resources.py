"""Regression coverage for prompt resources in installed package layouts."""

import json
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


def test_installed_prompt_config_supplies_default_and_respects_overrides(
    tmp_path: Path,
) -> None:
    installed_root = tmp_path / "site-packages"
    shutil.copytree(ROOT / "src" / "youtube_automation", installed_root / "youtube_automation")
    prefix_config = tmp_path / "daheeh_config.json"
    prefix_config.write_text(
        json.dumps(
            {
                "al_daheeh_master_pipeline_config": {
                    "dialect_profile": {"tashkeel_lexicon": {"decoy": "دِيكُوي"}}
                }
            }
        ),
        encoding="utf-8",
    )
    source_config = json.loads((ROOT / "daheeh_config.json").read_text(encoding="utf-8"))
    packaged_config = json.loads(
        (PACKAGE / "default_prompt_config.json").read_text(encoding="utf-8")
    )
    source_profile = source_config["al_daheeh_master_pipeline_config"]["dialect_profile"]
    packaged_profile = packaged_config["al_daheeh_master_pipeline_config"]["dialect_profile"]
    assert set(packaged_profile) == {
        "fusha_academic_ratio",
        "cairo_amiya_ratio",
        "tashkeel_lexicon",
    }
    assert packaged_profile["fusha_academic_ratio"] == source_profile["fusha_academic_ratio"]
    assert packaged_profile["cairo_amiya_ratio"] == source_profile["cairo_amiya_ratio"]
    assert list(packaged_profile["tashkeel_lexicon"].items()) == list(
        source_profile["tashkeel_lexicon"].items()
    )
    expected = "، ".join(source_profile["tashkeel_lexicon"].values())
    script = r"""
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from youtube_automation.prompts import loader

expected = sys.argv[2]
prefix_config = Path(sys.argv[3])
assert loader.CONFIG_PATH == loader.PROMPTS_DIR / "default_prompt_config.json"
assert loader.config_value("tashkeel") == expected
assert expected in loader.render("tts")
loader.CONFIG_PATH = Path(sys.argv[3])
assert loader.config_value("tashkeel") == "دِيكُوي"
prefix_config.unlink()
loader.CONFIG_PATH = loader.PROMPTS_DIR / "default_prompt_config.json"
assert loader.config_value("tashkeel") == expected

override = Path(sys.argv[4])
override.write_text(json.dumps({"al_daheeh_master_pipeline_config": {
    "dialect_profile": {"tashkeel_lexicon": {"override": "مُخْتَار"}}
}}), encoding="utf-8")
loader.CONFIG_PATH = override
assert loader.config_value("tashkeel") == "مُخْتَار"

missing = Path(sys.argv[5])
loader.CONFIG_PATH = missing
assert loader.config_value("tashkeel") == ""
malformed = Path(sys.argv[6])
malformed.write_text("{bad json", encoding="utf-8")
loader.CONFIG_PATH = malformed
assert loader.config_value("tashkeel") == ""

channel = {"dialect_profile": {"tashkeel_lexicon": {"channel": "قَنَاة"}}}
assert loader.config_value("tashkeel", channel) == "قَنَاة"

class ChannelModel:
    def model_dump(self):
        return {"dialect_profile": {"tashkeel_lexicon": {"model": "مَدْرَسَة"}}}

assert loader.config_value("tashkeel", ChannelModel()) == "مَدْرَسَة"
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(installed_root),
            expected,
            str(prefix_config),
            str(tmp_path / "override.json"),
            str(tmp_path / "missing.json"),
            str(tmp_path / "malformed.json"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
