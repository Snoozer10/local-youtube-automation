from unittest.mock import MagicMock

import pytest

from youtube_automation.production import flow


def test_flow_chip_count_does_not_double_count_nested_components():
    from youtube_automation.visuals.flow_generator import count_attached_prompt_chips

    page = MagicMock()
    container = MagicMock()
    container.is_visible.return_value = True
    root = MagicMock()
    root.first = container
    page.locator.return_value = root
    counts = {
        "flow-ingredient-chip": 1,
        "flow-image-ingredient-chip": 1,
        "button.chip-container": 1,
    }
    container.locator.side_effect = lambda selector: MagicMock(
        count=MagicMock(return_value=counts.get(selector, 0))
    )

    assert count_attached_prompt_chips(page) == 1
    container.locator.assert_called_once_with("flow-ingredient-chip")


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

    restored.assert_called_once_with(page, accepted.resolve())


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
    clicked = MagicMock(return_value=True)
    monkeypatch.setattr(flow_generator, "_click_add_to_prompt_on_image", clicked)

    flow.attach_exact_reference(page, tmp_path, "anchor")

    clicked.assert_called_once_with(page, refreshed)
