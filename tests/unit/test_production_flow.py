from unittest.mock import MagicMock

import pytest

from youtube_automation.production import flow


def test_flow_chip_count_does_not_double_count_nested_components():
    from youtube_automation.visuals.flow_generator import count_attached_prompt_chips

    page = MagicMock()
    visible = MagicMock()
    visible.is_visible.return_value = True
    hidden = MagicMock()
    hidden.is_visible.return_value = False
    page.locator.return_value.all.return_value = [visible, hidden]

    assert count_attached_prompt_chips(page) == 1
    selector = page.locator.call_args.args[0]
    assert "flow-base-prompt-box flow-ingredient-chip" in selector
    assert "form:has([contenteditable='true']) flow-ingredient-chip" in selector


def test_exact_reference_gate_rejects_a_missing_prompt_chip(tmp_path, monkeypatch):
    from youtube_automation.visuals import flow_generator

    monkeypatch.setattr(
        flow,
        "read_receipt",
        lambda *_: {
            "source_url": "https://flow-content.google/image/accepted-id/source",
            "pixel_sha256": "accepted-pixels",
        },
    )
    monkeypatch.setattr(flow_generator, "visible_attached_prompt_images", lambda *_: [])

    with pytest.raises(RuntimeError, match="exact reference chip is not attached"):
        flow.verify_exact_reference(MagicMock(), tmp_path, "anchor")


def test_adaptive_submit_gate_rejects_unexpected_reference_chip(tmp_path, monkeypatch):
    from youtube_automation.visuals import flow_generator

    monkeypatch.setattr(flow_generator, "count_attached_prompt_chips", lambda *_: 1)
    shot = MagicMock(reference_asset_id=None)

    with pytest.raises(RuntimeError, match="unexpected reference chip"):
        flow.verify_adaptive_prompt_references(MagicMock(), tmp_path, shot)


def test_unrestorable_reference_project_never_uses_recent_card(tmp_path, monkeypatch):
    monkeypatch.setattr(
        flow,
        "read_receipt",
        lambda *_: {"source_url": "blob:accepted", "project_url": "https://flow/project/old"},
    )
    page = MagicMock(url="https://flow/project/new")
    with pytest.raises(RuntimeError, match="could not be restored"):
        flow.attach_exact_reference(page, tmp_path, "anchor")
    page.goto.assert_called_once_with(
        "https://flow/project/old", wait_until="domcontentloaded", timeout=45000
    )
    page.locator.assert_not_called()


def test_missing_exact_reference_blocks_even_if_other_images_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(
        flow,
        "read_receipt",
        lambda *_: {
            "source_url": "blob:accepted",
            "project_url": "https://flow/project/one",
            "pixel_sha256": "accepted-pixels",
            "path": "accepted_assets/anchor.png",
        },
    )
    unrelated = MagicMock()
    unrelated.get_attribute.return_value = "blob:unrelated"
    unrelated.is_visible.return_value = True
    page = MagicMock(url="https://flow/project/one")
    page.locator.return_value.all.return_value = [unrelated]
    monkeypatch.setattr(flow, "_attach_uploaded_reference", lambda *_: False)
    with pytest.raises(RuntimeError, match="content differs"):
        flow.attach_exact_reference(page, tmp_path, "anchor")


def test_missing_provider_card_restores_content_addressed_local_asset(tmp_path, monkeypatch):
    accepted = tmp_path / "accepted_assets" / "digest.png"
    accepted.parent.mkdir()
    accepted.write_bytes(b"accepted")
    monkeypatch.setattr(
        flow,
        "read_receipt",
        lambda *_: {
            "source_url": "https://flow-content.google/image/id?old-signature",
            "project_url": "https://flow/project/one",
            "pixel_sha256": "accepted-pixels",
            "path": "accepted_assets/digest.png",
        },
    )
    page = MagicMock(url="https://flow/project/one")
    page.locator.return_value.all.return_value = []
    restored = MagicMock(return_value=True)
    monkeypatch.setattr(flow, "_attach_uploaded_reference", restored)

    flow.attach_exact_reference(page, tmp_path, "anchor")

    restored.assert_called_once_with(page, accepted.resolve(), flow.read_receipt(tmp_path, "anchor"))


def test_reference_survives_signed_url_refresh_when_provider_id_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(
        flow,
        "read_receipt",
        lambda *_: {
            "source_url": "https://flow-content.google/image/id?old-signature",
            "project_url": "https://flow/project/one",
            "pixel_sha256": "accepted-pixels",
        },
    )
    refreshed = MagicMock()
    refreshed.get_attribute.side_effect = lambda name: {
        "src": "https://flow.google.com/asb/refreshed-signed-url",
        "alt": "Tile displaying a user's image",
    }.get(name)
    refreshed.is_visible.return_value = True
    chip = MagicMock()
    chip.is_visible.return_value = True
    chip.get_attribute.return_value = "https://flow-content.google/image/id?new-signature"
    page = MagicMock(url="https://flow/project/one")
    all_images = MagicMock()
    all_images.all.return_value = [refreshed]
    chip_locator = MagicMock()
    chip_locator.first = chip
    page.locator.side_effect = lambda selector: (
        all_images if selector == "img" else chip_locator
    )

    from youtube_automation.visuals import flow_generator

    monkeypatch.setattr(flow_generator, "clear_attached_prompt_chips", lambda *_: None)
    counts = iter([0, 1])
    monkeypatch.setattr(flow_generator, "count_attached_prompt_chips", lambda *_: next(counts))
    monkeypatch.setattr(flow, "_attached_reference_matches", lambda *_: True)
    clicked = MagicMock(return_value=True)
    monkeypatch.setattr(flow_generator, "_click_add_to_prompt_on_image", clicked)

    flow.attach_exact_reference(page, tmp_path, "anchor")

    clicked.assert_called_once_with(page, refreshed)
