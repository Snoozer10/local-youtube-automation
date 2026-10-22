from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "docs" / "sessions" / "VOICE_DIRECTION_ADAPTER_IMPLEMENTATION.py"
STAGE_TESTS_PATH = ROOT / "tests" / "unit" / "test_voice_direction_stage.py"


def _load_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _response_text(stage_tests, run_dir):
    return stage_tests._response(run_dir)


@pytest.fixture
def modules():
    return (
        _load_from_path("staged_voice_direction_adapter", ADAPTER_PATH),
        _load_from_path("staged_voice_direction_stage_tests", STAGE_TESTS_PATH),
    )


@pytest.fixture
def run_dir(tmp_path, monkeypatch, modules):
    _, stage_tests = modules
    from youtube_automation.production import cli, direction_stage

    monkeypatch.setenv("ADAPTIVE_TTS_MODEL", "gemini-3.8-flash-tts")
    monkeypatch.setattr(cli, "resource_database", lambda: tmp_path / "jobs.db")
    monkeypatch.setattr(cli, "gemini_transport", lambda *a, **k: pytest.fail("provider transport called"))
    monkeypatch.setattr(direction_stage, "publication_guard", contextlib.nullcontext)
    stage_tests._run(tmp_path)
    return tmp_path


def test_staged_module_loads_from_its_actual_filename(modules):
    adapter, _ = modules
    assert Path(adapter.__file__).resolve() == ADAPTER_PATH.resolve()
    from youtube_automation.production import direction_stage

    assert adapter.direction_inputs is direction_stage.direction_inputs
    assert adapter.direction_prompt is direction_stage.direction_prompt


def test_supplied_response_uses_production_tags_and_verification(run_dir, modules):
    adapter, stage_tests = modules
    from youtube_automation.production import direction_stage

    response_text = _response_text(stage_tests, run_dir)
    response = json.loads(response_text)
    candidate = adapter.ensure_direction_candidate(run_dir, response_text)
    verified = direction_stage.verify_direction_candidate(run_dir)

    assert candidate["paragraphs"] == response["paragraphs"]
    assert verified["paragraphs"] == response["paragraphs"]
    assert all("<" in paragraph for paragraph in verified["paragraphs"])


def test_response_callback_cannot_be_replaced_by_a_network_callable(run_dir, modules):
    adapter, _ = modules
    with pytest.raises(TypeError, match="supplied as text"):
        adapter.ensure_direction_candidate(run_dir, lambda prompt: "network")


@pytest.mark.parametrize("operation", ["generate", "accept"])
def test_source_audio_receipt_blocks_generation_and_approval_after_candidate(
    run_dir, modules, operation
):
    adapter, stage_tests = modules
    response = _response_text(stage_tests, run_dir)
    adapter.ensure_direction_candidate(run_dir, response)
    candidate_hash = stage_tests._candidate_hash(run_dir)
    (Path(run_dir) / "source_audio_receipt.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="Imported raw narration"):
        if operation == "generate":
            adapter.ensure_direction_candidate(run_dir, response)
        else:
            adapter.accept_direction(
                run_dir,
                reviewer="reviewer",
                candidate_sha256=candidate_hash,
            )


def test_acceptance_requires_exact_hash_and_uses_production_guard(run_dir, modules):
    adapter, stage_tests = modules
    adapter.ensure_direction_candidate(run_dir, _response_text(stage_tests, run_dir))

    with pytest.raises(ValueError):
        adapter.accept_direction(
            run_dir,
            reviewer="reviewer",
            candidate_sha256="0" * 64,
        )


def test_tampered_candidate_provenance_is_rejected(run_dir, modules):
    adapter, stage_tests = modules
    from youtube_automation.production import direction_stage

    adapter.ensure_direction_candidate(run_dir, _response_text(stage_tests, run_dir))
    original_hash = stage_tests._candidate_hash(run_dir)
    candidate_path = Path(run_dir) / direction_stage.CANDIDATE_FILE
    candidate_path.write_bytes(candidate_path.read_bytes() + b" ")

    with pytest.raises(ValueError):
        adapter.accept_direction(
            run_dir,
            reviewer="reviewer",
            candidate_sha256=original_hash,
        )


def test_approval_api_has_no_arbitrary_dictionary_bypass(run_dir, modules):
    adapter, stage_tests = modules
    adapter.ensure_direction_candidate(run_dir, _response_text(stage_tests, run_dir))
    with pytest.raises(TypeError):
        adapter.accept_direction(
            run_dir,
            {"paragraphs": ["invented approval"]},
            reviewer="reviewer",
            candidate_sha256="0" * 64,
        )


def test_missing_run_context_blocks_generation_and_approval(tmp_path, modules):
    adapter, _ = modules
    with pytest.raises((ValueError, FileNotFoundError)):
        adapter.ensure_direction_candidate(tmp_path, "{}")
    with pytest.raises((ValueError, FileNotFoundError)):
        adapter.accept_direction(
            tmp_path,
            reviewer="reviewer",
            candidate_sha256="0" * 64,
        )


def test_missing_policy_context_fails_before_candidate_generation(run_dir, modules, monkeypatch):
    adapter, stage_tests = modules
    from youtube_automation.production import direction_stage

    response = _response_text(stage_tests, run_dir)

    def missing_policy(_run_dir):
        raise direction_stage.VoiceDirectionError("missing direction policy")

    monkeypatch.setattr(direction_stage, "direction_inputs", missing_policy)
    with pytest.raises(ValueError, match="missing direction policy"):
        adapter.ensure_direction_candidate(run_dir, response)


def test_existing_take_guard_uses_production_acceptance(run_dir, modules):
    adapter, stage_tests = modules
    adapter.ensure_direction_candidate(run_dir, _response_text(stage_tests, run_dir))
    (run_dir / "voice_chapters").mkdir()
    (run_dir / "voice_chapters" / "take.wav").write_bytes(b"existing take")

    with pytest.raises(ValueError, match="Existing voice takes"):
        adapter.accept_direction(
            run_dir,
            reviewer="reviewer",
            candidate_sha256=stage_tests._candidate_hash(run_dir),
        )
