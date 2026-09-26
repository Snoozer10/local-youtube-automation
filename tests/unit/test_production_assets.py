import json
from pathlib import Path

import pytest
from PIL import Image

from youtube_automation.production import assets
from youtube_automation.production.contracts import Analysis, Brief, Channel, fingerprint
from youtube_automation.production.shots import Overlay, Shot


def fixture_shot_and_brief():
    channel = Channel(
        channel_id="test",
        name="Test",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="voice",
        tone="calm",
        style="editorial illustration",
        allowed_treatments=["subject_scene"],
    )
    brief = Brief(
        source_sha256=fingerprint("source"),
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=Analysis(
            topics=["test"],
            claim_basis="factual",
            form="explanation",
            proposition="Scene",
            narrative_strategy="Observe",
            treatments=["subject_scene"],
            rationale="Concrete",
        ),
    )
    shot = Shot(
        shot_id="shot",
        scene_id="scene",
        asset_id="asset",
        entity_ids=["subject"],
        span_ids=[0],
        start_frame=0,
        end_frame=30,
        purpose="Explain the subject",
        treatment="subject_scene",
        subject="Subject",
        visible_state="Subject observes the scene",
        setting="A quiet room",
        framing="medium",
        composition="Subject centered with clear negative space",
    )
    return shot, brief


def test_strict_background_requires_actual_ocr_and_rejects_any_region(tmp_path, monkeypatch):
    path = tmp_path / "frame.png"
    Image.new("RGB", (640, 360), "white").save(path)
    monkeypatch.setattr(assets, "_detect_via_pytesseract", lambda *_: None)
    with pytest.raises(RuntimeError, match="unavailable"):
        assets.validate_background(path)
    monkeypatch.setattr(
        assets, "_detect_via_pytesseract", lambda *_: [{"text": "X: 180", "bbox": [0, 0, 80, 12]}]
    )
    with pytest.raises(ValueError, match="text"):
        assets.validate_background(path)
    monkeypatch.setattr(assets, "_detect_via_pytesseract", lambda *_: [])
    assert assets.validate_background(path) == (640, 360)


def test_corrupt_image_is_not_accepted(tmp_path):
    path = tmp_path / "frame.png"
    path.write_bytes(b"not an image" * 200)
    with pytest.raises(OSError):
        assets.validate_background(path)


def test_asset_receipt_geometry_must_match_accepted_pixels(tmp_path):
    accepted = tmp_path / "accepted_assets"
    receipts = tmp_path / "asset_receipts"
    accepted.mkdir()
    receipts.mkdir()
    image = accepted / "asset.png"
    Image.new("RGB", (640, 360), "blue").save(image)
    payload = {
        "asset_id": "asset",
        "path": "accepted_assets/asset.png",
        "sha256": assets.file_digest(image),
        "pixel_sha256": assets.pixel_digest(image),
        "dimensions": [640, 360],
        "technical_status": "verified",
        "version": 1,
    }
    path = receipts / "asset.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert assets.read_receipt(tmp_path, "asset")["dimensions"] == [640, 360]
    payload["dimensions"] = [1920, 1080]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="geometry or pixels changed"):
        assets.read_receipt(tmp_path, "asset")
    payload["dimensions"] = [640, 360]
    payload["pixel_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="geometry or pixels changed"):
        assets.read_receipt(tmp_path, "asset")


def test_interrupted_asset_receipt_activation_recovers_without_regeneration(
    tmp_path, monkeypatch
):
    shot, brief = fixture_shot_and_brief()
    candidate = tmp_path / "candidate.png"
    Image.new("RGB", (640, 360), "blue").save(candidate)
    monkeypatch.setattr(assets, "_detect_via_pytesseract", lambda *_: [])
    original_write = assets.atomic_write_json

    def interrupt_final_receipt(path, value):
        if Path(path).parent.name == "asset_receipts":
            raise OSError("simulated receipt activation crash")
        return original_write(path, value)

    monkeypatch.setattr(assets, "atomic_write_json", interrupt_final_receipt)
    with pytest.raises(OSError, match="activation crash"):
        assets.register_asset(tmp_path, shot, brief, candidate)
    assert not (tmp_path / "asset_receipts" / "asset.json").exists()
    assert (tmp_path / ".publication_journal" / "assets" / "asset.json").is_file()
    assert len(list((tmp_path / "accepted_assets").glob("*.png"))) == 1

    monkeypatch.setattr(assets, "atomic_write_json", original_write)
    recovered = assets.accepted_asset(tmp_path, shot, brief)
    assert recovered is not None
    assert assets.read_receipt(tmp_path, "asset")["sha256"] == recovered["sha256"]
    assert not (tmp_path / ".publication_journal" / "assets" / "asset.json").exists()


def test_incomplete_asset_publication_never_activates(tmp_path, monkeypatch):
    shot, brief = fixture_shot_and_brief()
    candidate = tmp_path / "candidate.png"
    Image.new("RGB", (640, 360), "blue").save(candidate)
    monkeypatch.setattr(assets, "_detect_via_pytesseract", lambda *_: [])
    original_write = assets.atomic_write_json

    def interrupt_final_receipt(path, value):
        if Path(path).parent.name == "asset_receipts":
            raise OSError("simulated receipt activation crash")
        return original_write(path, value)

    monkeypatch.setattr(assets, "atomic_write_json", interrupt_final_receipt)
    with pytest.raises(OSError):
        assets.register_asset(tmp_path, shot, brief, candidate)
    for path in (tmp_path / "accepted_assets").glob("*.png"):
        path.unlink()
    monkeypatch.setattr(assets, "atomic_write_json", original_write)

    assert assets.accepted_asset(tmp_path, shot, brief) is None
    assert not (tmp_path / "asset_receipts" / "asset.json").exists()


def test_local_canvas_is_deterministic_receipted_and_text_free(tmp_path, monkeypatch):
    _, brief = fixture_shot_and_brief()
    shot = Shot(
        shot_id="grid",
        scene_id="exercise",
        asset_id="grid_canvas",
        entity_ids=["schulte_grid"],
        span_ids=[0],
        start_frame=0,
        end_frame=60,
        purpose="Present a playable Schulte exercise",
        treatment="mechanism",
        narrative_role="diagram",
        subject="Local Schulte exercise canvas",
        visible_state="Static clean canvas",
        setting="Two-dimensional diagram space",
        framing="diagram",
        composition="Full-frame high-contrast diagram",
        operation="local_canvas",
        overlays=[
            Overlay(
                kind="data_grid",
                start_frame=0,
                end_frame=60,
                preset="schulte_6x6",
                x=0.08,
                y=0.08,
                width=0.84,
                height=0.84,
            )
        ],
    )
    monkeypatch.setattr(assets, "_detect_via_pytesseract", lambda *_: [])

    first = assets.ensure_local_canvas(tmp_path, shot, brief)
    second = assets.ensure_local_canvas(tmp_path, shot, brief)

    assert first == second
    assert first["source_url"] == "local://deterministic-diagram-canvas"
    assert first["dimensions"] == list(assets.LOCAL_CANVAS_SIZE)
    assert len(list((tmp_path / "accepted_assets").glob("*.png"))) == 1
