"""Shared pytest fixtures for compile_video tests."""

import json
import os
import shutil
import subprocess
import tempfile

import pytest
from ffmpeg_stubs import FakePopen

import compile_video


@pytest.fixture
def config():
    """Default video config with test overrides."""
    c = compile_video.load_video_config()
    c["ENCODER_FORCE"] = "libx264"
    c["ENABLE_LOUDNORM_TWOPASS"] = False
    c["ENABLE_SUBTITLES"] = False
    c["ENABLE_ANIMATIONS"] = True
    c["ENABLE_CHECKPOINT_RESUME"] = False
    c["ENABLE_SINGLE_PASS"] = True
    c["_audio_duration"] = 10.0
    c["FFMPEG_CLIP_TIMEOUT"] = 60
    c["FFMPEG_FINAL_TIMEOUT"] = 120
    return c


@pytest.fixture
def encoder_config(config):
    """Video config for encoder detection tests (no ENCODER_FORCE override)."""
    c = config.copy()
    c["ENCODER_FORCE"] = ""
    return c


@pytest.fixture
def temp_run_folder():
    """Temp dir with run folder structure (generated_images, temp_clips)."""
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "generated_images"), exist_ok=True)
    os.makedirs(os.path.join(d, "temp_clips"), exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_timeline():
    """Standard 3-block timeline."""
    return [
        {"name": "00_00", "sec": 0.0},
        {"name": "00_08", "sec": 8.0},
        {"name": "00_15", "sec": 15.0},
    ]


@pytest.fixture
def sync_timeline(config, sample_timeline):
    """ZERO-DRIFT prepared timeline with frame_count/duration/occurrence fields."""
    return compile_video.prepare_synchronized_timeline(sample_timeline, 10.0, config["OUTPUT_FPS"])


@pytest.fixture
def sample_flow_prompts(temp_run_folder):
    """Write flow_prompts.json with camera decisions."""
    path = os.path.join(temp_run_folder, "flow_prompts.json")
    data = [
        {"timestamp": "[00:00]", "visual_prompt": {"camera_specifications": "zoom in slowly"}},
        {
            "timestamp": "[00:08]",
            "visual_prompt": {"camera_specifications": "pan left across scene"},
        },
        {"timestamp": "[00:15]", "visual_prompt": {"camera_specifications": "static shot"}},
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


@pytest.fixture
def sample_manual_animations(temp_run_folder):
    """Write manual_animations.txt with overrides."""
    path = os.path.join(temp_run_folder, "manual_animations.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("00_00=zoom_out\n")
        f.write("00_15=pan_right\n")
    return path


@pytest.fixture
def mock_ffmpeg(monkeypatch):
    """Patch subprocess.run for ffmpeg/ffprobe calls."""

    def mock_run(cmd, *args, **kwargs):
        # Mock ffprobe duration
        if "ffprobe" in cmd[0]:

            class R:
                stdout = "10.0\n"
                returncode = 0

            return R()

        # Mock ffmpeg -encoders
        if "-encoders" in cmd:

            class R:
                stdout = "h264_qsv\nh264_nvenc\nlibx264\n"
                returncode = 0

            return R()

        # Mock loudnorm measure pass
        if "loudnorm" in " ".join(cmd) and "print_format=json" in " ".join(cmd):

            class R:
                stderr = '{"input_i":"-14.5","input_tp":"-1.2","input_lra":"7.8","input_thresh":"-25.3","target_offset":"0.5"}'
                returncode = 0

            return R()

        # Default: success
        class R:
            stdout = ""
            stderr = ""
            returncode = 0

        return R()

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: b"10.0\n")
    return mock_run


@pytest.fixture
def mock_ffmpeg_popen(monkeypatch):
    """Patch subprocess.Popen with a successful fake; records commands."""
    calls = []

    def popen_factory(cmd, **kwargs):
        calls.append(list(cmd))
        return FakePopen(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", popen_factory)
    return calls


@pytest.fixture
def test_images_dir():
    """Create temp dir with test PNG images."""
    d = tempfile.mkdtemp()
    # Generate simple test images using ffmpeg
    for name in ["00_00.png", "00_08.png", "00_15.png"]:
        img_path = os.path.join(d, name)
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=200x200",
            "-frames:v",
            "1",
            "-update",
            "1",
            img_path,
        ]
        subprocess.run(cmd, capture_output=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def dummy_audio_file():
    """Create a dummy audio file for testing."""
    d = tempfile.mkdtemp()
    audio_path = os.path.join(d, "audio.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=10",
        "-ar",
        "48000",
        audio_path,
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        pytest.skip("ffmpeg unavailable for audio generation")
    yield audio_path
    if os.path.exists(audio_path):
        os.remove(audio_path)
    os.rmdir(d)


@pytest.fixture
def dummy_transcript_file(temp_run_folder):
    """Create a timestamped transcript source (image_timestamps.txt) for subtitle testing."""
    txt_path = os.path.join(temp_run_folder, "image_timestamps.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("[00:00] Test subtitle\n")
        f.write("[00:05] Another subtitle\n")
    return txt_path

@pytest.fixture(autouse=True)
def isolated_shared_resource_paths(monkeypatch, tmp_path):
    """Redirect shared resource state before each test can acquire or write it."""
    import sys
    from pathlib import Path

    from youtube_automation.core import utils
    from youtube_automation.production import ledger

    ledger_resource_database = ledger.resource_database
    production_database = ledger_resource_database()
    import sqlite3
    import traceback

    real_connect = sqlite3.connect

    def isolated_connect(database, *args, **kwargs):
        if isinstance(database, (str, bytes, Path)):
            candidate = Path(database.decode() if isinstance(database, bytes) else database)
            if candidate.resolve() == production_database.resolve():
                pytest.fail("Attempted real production SQLite connection before isolation: "
                            + "".join(traceback.format_stack(limit=8)))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", isolated_connect)
    production_registry = utils.OWNED_BROWSER_REGISTRY
    test_database = tmp_path / "adaptive.sqlite3"
    test_registry = tmp_path / "owned_browsers.json"
    preexisting_modules = {id(module) for module in tuple(sys.modules.values())}

    def test_resource_database() -> Path:
        return test_database

    monkeypatch.setattr(ledger, "resource_database", test_resource_database)
    monkeypatch.setattr(utils, "OWNED_BROWSER_REGISTRY", test_registry)

    for module in tuple(sys.modules.values()):
        namespace = getattr(module, "__dict__", None)
        if not isinstance(namespace, dict):
            continue
        if namespace.get("resource_database") is ledger_resource_database:
            monkeypatch.setattr(module, "resource_database", test_resource_database, raising=False)
        if namespace.get("OWNED_BROWSER_REGISTRY") == production_registry:
            monkeypatch.setattr(module, "OWNED_BROWSER_REGISTRY", test_registry, raising=False)

    paths = {
        "database": test_database,
        "registry": test_registry,
        "production_database": production_database,
        "production_registry": production_registry,
    }
    try:
        yield paths
    finally:
        for module in tuple(sys.modules.values()):
            if id(module) in preexisting_modules:
                continue
            namespace = getattr(module, "__dict__", None)
            if not isinstance(namespace, dict):
                continue
            if namespace.get("resource_database") is test_resource_database:
                namespace["resource_database"] = ledger_resource_database
            if namespace.get("OWNED_BROWSER_REGISTRY") == test_registry:
                namespace["OWNED_BROWSER_REGISTRY"] = production_registry



def _shared_resource_fingerprints(database, registry):
    import hashlib
    from pathlib import Path

    paths = [Path(database), Path(registry)]
    paths.extend(Path(f"{database}{suffix}") for suffix in ("-journal", "-wal", "-shm"))
    fingerprints = {}
    for path in paths:
        if not path.exists():
            fingerprints[str(path)] = None
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        fingerprints[str(path)] = (path.stat().st_size, digest.hexdigest())
    return fingerprints


def pytest_sessionstart(session):
    """Capture real shared resources before per-test monkeypatching begins."""
    from youtube_automation.core import utils
    from youtube_automation.production import ledger

    database = ledger.resource_database()
    registry = utils.OWNED_BROWSER_REGISTRY
    session._shared_resource_paths = (database, registry)
    session._shared_resource_baseline = _shared_resource_fingerprints(database, registry)


def pytest_sessionfinish(session, exitstatus):
    """Fail the run if any test changed a persistent shared resource."""
    import sys

    paths = getattr(session, "_shared_resource_paths", None)
    baseline = getattr(session, "_shared_resource_baseline", None)
    if paths is None or baseline is None:
        return
    current = _shared_resource_fingerprints(*paths)
    if current == baseline:
        return
    changed = sorted(
        path for path in set(baseline) | set(current)
        if baseline.get(path) != current.get(path)
    )
    sys.stderr.write("Persistent production resources changed during pytest: " + ", ".join(changed) + "\\n")
    session.exitstatus = 1


def pytest_addoption(parser):
    parser.addoption(
        "--run-live-browser",
        action="store_true",
        default=False,
        help="run explicitly marked live browser/CDP/socket integration tests",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_browser: requires an explicit --run-live-browser opt-in",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live-browser"):
        return

    skip_live_browser = pytest.mark.skip(
        reason="live browser/CDP/socket test requires --run-live-browser"
    )
    for item in items:
        if item.get_closest_marker("live_browser") is not None:
            item.add_marker(skip_live_browser)
