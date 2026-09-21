"""Adaptive thumbnail style and accepted bytes follow the selected channel."""

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from youtube_automation.production.contracts import Analysis, Brief, Channel, fingerprint
from youtube_automation.production.thumbnails import (
    RECEIPT,
    concept_prompt,
    image_prompt,
    publish,
    recipe,
    validate_concepts,
    validate_critique,
    validate_receipt,
)


def make_brief(*, host_mode="NONE", host_description="", language="English"):
    channel = Channel(
        channel_id="nature",
        name="Nature Field Notes",
        audience="curious adults",
        language=language,
        dialect="neutral",
        voice="Nova",
        tone="observant",
        style="natural history photography",
        host_mode=host_mode,
        host_description=host_description,
        allowed_treatments=["subject_scene"] + (["host"] if host_mode != "NONE" else []),
    )
    analysis = Analysis(
        topics=["migration"],
        claim_basis="factual",
        form="explanation",
        proposition="Birds use landmarks during migration",
        narrative_strategy="Show field observations",
        treatments=["subject_scene"],
        rationale="Direct visual evidence",
    )
    return Brief(
        source_sha256=fingerprint("raw"),
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=analysis,
    )


def test_thumbnail_prompts_follow_channel_host_and_language():
    titles = [{"index": 1, "text": "How birds navigate"}]
    brief = make_brief()
    prompt = concept_prompt(brief, titles, "Birds track landmarks.")
    assert "natural history photography" in prompt
    assert "No recurring channel host or mascot" in prompt
    assert "English" in prompt
    assert "Arabic" not in prompt
    generated = image_prompt(
        brief,
        {"scene": "A migrating bird over a coastline", "visual_recipe": {"lighting": "dawn"}},
        "no text",
    )
    assert "natural history photography" in generated
    assert "no text" in generated
    assert "white circular head" not in generated
    assert "Do not insert a recurring channel host" in generated

    hosted = make_brief(host_mode="CUSTOM_AVATAR", host_description="A red-jacketed field guide")
    assert "A red-jacketed field guide" in concept_prompt(hosted, titles, "Birds track landmarks.")
    assert "A red-jacketed field guide" in image_prompt(hosted, {"scene": "Bird on coast"}, "no text")


def test_adaptive_thumbnail_receipt_verifies_bytes_and_recipe(tmp_path, monkeypatch):
    from youtube_automation.production import thumbnails

    brief = make_brief()
    script = "Birds track landmarks."
    titles = [{"index": 1, "text": "How birds navigate"}]
    (tmp_path / "refined_script.txt").write_text(script, encoding="utf-8")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    image = scratch / "title_1_thumbnail.png"
    Image.new("RGB", (1280, 720), "blue").save(image)
    monkeypatch.setattr(thumbnails, "verify_written_episode", lambda _root: True)
    monkeypatch.setattr(thumbnails, "load_brief", lambda _root: brief)
    monkeypatch.setattr(thumbnails, "_detect_via_pytesseract", lambda *_args: [])

    accepted = publish(tmp_path, brief, script, titles, "model-v1", [str(image)])
    assert len(accepted) == 1
    assert Path(accepted[0]).is_file()
    assert (tmp_path / RECEIPT).is_file()
    expected = recipe(brief, script, titles, "model-v1")
    assert validate_receipt(tmp_path, expected) == accepted
    with pytest.raises(ValueError, match="stale"):
        validate_receipt(tmp_path, recipe(brief, script, titles, "model-v2"))

    monkeypatch.setattr(thumbnails, "_detect_via_pytesseract", lambda *_args: None)
    with pytest.raises(RuntimeError, match="OCR is unavailable"):
        publish(tmp_path, brief, script, titles, "model-v1", [str(image)])

    Path(accepted[0]).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="bytes changed"):
        validate_receipt(tmp_path, expected)


def test_adaptive_thumbnail_rejects_changed_script_before_publication(tmp_path, monkeypatch):
    from youtube_automation.production import thumbnails

    brief = make_brief()
    (tmp_path / "refined_script.txt").write_text("Changed", encoding="utf-8")
    monkeypatch.setattr(thumbnails, "verify_written_episode", lambda _root: True)
    monkeypatch.setattr(thumbnails, "load_brief", lambda _root: brief)
    with pytest.raises(ValueError, match="script changed"):
        publish(tmp_path, brief, "Old", [], "model-v1", [str(tmp_path / "missing.png")])


def test_thumbnail_concepts_require_one_scene_per_title():
    titles = [{"index": 1, "text": "Birds"}, {"index": 2, "text": "Maps"}]
    valid = [{"title_index": 1, "scene": "Bird over a coastline"}, {"title_index": 2, "scene": "Map"}]
    assert validate_concepts(valid, titles) == valid
    with pytest.raises(ValueError, match="duplicate"):
        validate_concepts([valid[0], valid[0]], titles)
    with pytest.raises(ValueError, match="concrete scene"):
        validate_concepts([valid[0], {"title_index": 2, "scene": ""}], titles)
    with pytest.raises(ValueError, match="at most three words"):
        validate_concepts([valid[0], {"title_index": 2, "scene": "Map", "text_overlay": "one two three four"}], titles)
    assert validate_critique({"winners": [2, 1], "improvements": {}}, titles, 2)["winners"] == [2, 1]
    with pytest.raises(ValueError, match="invalid winners"):
        validate_critique({"winners": [1, 1]}, titles, 2)


def test_adaptive_thumbnail_entrypoint_publishes_and_resumes_without_browser(tmp_path, monkeypatch):
    import generate_thumbnail
    from youtube_automation.production import ledger

    brief = make_brief()
    script = "Birds track landmarks."
    (tmp_path / "raw_transcript.txt").write_text("raw", encoding="utf-8")
    (tmp_path / "episode_brief.json").write_text(brief.model_dump_json(), encoding="utf-8")
    outputs = {
        "breaked_paragraphs.txt": script,
        "final_output.txt": script,
        "refined_script.txt": script,
    }
    for name, content in outputs.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    (tmp_path / "adaptive_writing_receipt.json").write_text(
        json.dumps({"brief_sha256": fingerprint(brief), "outputs": {name: fingerprint(text) for name, text in outputs.items()}}),
        encoding="utf-8",
    )
    (tmp_path / "titles.txt").write_text("1. How birds navigate\n2. A map in the sky", encoding="utf-8")
    monkeypatch.setattr(generate_thumbnail.sys, "argv", ["generate_thumbnail.py", str(tmp_path)])
    monkeypatch.setattr(generate_thumbnail, "get_config_value", lambda _key, default=None: default)
    monkeypatch.setattr(generate_thumbnail.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(generate_thumbnail, "start_clean_gemini_chat", lambda _page: None)
    monkeypatch.setattr(generate_thumbnail, "select_gemini_model", lambda _page, _model: None)
    monkeypatch.setattr(
        generate_thumbnail,
        "send_telegram_notification",
        lambda _message: pytest.fail("Adaptive thumbnails must not send notifications"),
    )
    monkeypatch.setattr(ledger, "resource_database", lambda: tmp_path / "ledger.sqlite3")
    prompts = []
    responses = [
        json.dumps([
            {"title_index": 1, "scene": "A bird above a coastline"},
            {"title_index": 2, "scene": "Bird tracking distant mountains"},
        ]),
        json.dumps({"winners": [1, 2], "improvements": {}}),
    ]

    def fake_send(_page, prompt, timeout=180):
        prompts.append(prompt)
        return responses.pop(0)

    def fake_images(_page, items, output_dir):
        assert len(items) == 2
        assert all("natural history photography" in item["prompt"] for item in items)
        paths = []
        for item in items:
            target = Path(output_dir) / item["filename"]
            Image.new("RGB", (1280, 720), "blue").save(target)
            paths.append(str(target))
        return paths

    monkeypatch.setattr(generate_thumbnail, "send_and_wait", fake_send)
    monkeypatch.setattr(generate_thumbnail, "generate_images_via_gemini", fake_images)
    page = MagicMock()
    browser = SimpleNamespace(contexts=[SimpleNamespace(grant_permissions=lambda _perms: None, new_page=lambda: page)])

    @contextmanager
    def fake_playwright():
        yield SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=lambda _url: browser))

    monkeypatch.setattr(generate_thumbnail, "sync_playwright", fake_playwright)
    from youtube_automation.production import thumbnails

    monkeypatch.setattr(thumbnails, "_detect_via_pytesseract", lambda *_args: [])
    generate_thumbnail.main()
    assert "Nature Field Notes" in prompts[0]
    assert "white circular head" not in prompts[0]
    assert "truthful title synergy" in prompts[1]
    assert "Visceral reaction pose" not in prompts[1]
    assert (tmp_path / RECEIPT).exists()
    assert len(list((tmp_path / "thumbnails" / "accepted").glob("*.png"))) == 2

    monkeypatch.setattr(generate_thumbnail, "sync_playwright", lambda: pytest.fail("Validated resume should not open browser"))
    generate_thumbnail.main()


def test_thumbnail_entrypoint_never_falls_back_from_explicit_missing_run(tmp_path, monkeypatch):
    import generate_thumbnail

    monkeypatch.setattr(generate_thumbnail.sys, "argv", ["generate_thumbnail.py", str(tmp_path / "missing")])
    monkeypatch.setattr(
        generate_thumbnail, "get_latest_run_folder", lambda: pytest.fail("Wrong run fallback")
    )
    with pytest.raises(FileNotFoundError, match="Selected thumbnail run"):
        generate_thumbnail.main()
