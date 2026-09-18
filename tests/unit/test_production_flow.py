from unittest.mock import MagicMock

import pytest

from youtube_automation.production import flow


def test_reference_from_other_project_never_uses_recent_card(tmp_path, monkeypatch):
    monkeypatch.setattr(
        flow,
        "read_receipt",
        lambda *_: {"source_url": "blob:accepted", "project_url": "https://flow/project/old"},
    )
    page = MagicMock(url="https://flow/project/new")
    with pytest.raises(RuntimeError, match="not available"):
        flow.attach_exact_reference(page, tmp_path, "anchor")
    page.locator.assert_not_called()


def test_missing_exact_reference_blocks_even_if_other_images_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(
        flow,
        "read_receipt",
        lambda *_: {"source_url": "blob:accepted", "project_url": "https://flow/project/one"},
    )
    unrelated = MagicMock()
    unrelated.get_attribute.return_value = "blob:unrelated"
    page = MagicMock(url="https://flow/project/one")
    page.locator.return_value.all.return_value = [unrelated]
    with pytest.raises(RuntimeError, match="absent"):
        flow.attach_exact_reference(page, tmp_path, "anchor")
