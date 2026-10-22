from unittest.mock import MagicMock

import pytest

from youtube_automation.production import flow


def test_flow_page_selection_preserves_borrowed_edit_tab():
    from types import SimpleNamespace

    from youtube_automation.visuals import flow_generator as generator

    borrowed = SimpleNamespace(
        url="https://labs.google/fx/tools/flow/edit/123",
        close=MagicMock(),
        goto=MagicMock(),
    )
    owned = SimpleNamespace(url="about:blank")
    context = SimpleNamespace(pages=[borrowed], new_page=MagicMock(return_value=owned))

    assert generator._select_flow_page(context) is owned
    context.new_page.assert_called_once_with()
    borrowed.close.assert_not_called()
    borrowed.goto.assert_not_called()


def test_attached_images_sdk_query_structure_and_visibility_filtering():
    """Check the SDK query contract; the fixture does not evaluate CSS or a DOM."""
    from youtube_automation.visuals import flow_generator

    class Image:
        def __init__(self, visible):
            self.visible = visible

        def is_visible(self):
            return self.visible

    visible, hidden = Image(True), Image(False)

    class FakeLocator:
        def all(self):
            return [visible, hidden]

    class FakePage:
        selector = None

        def locator(self, selector):
            self.selector = selector
            return FakeLocator()

    page = FakePage()
    assert flow_generator.visible_attached_prompt_images(page) == [visible]
    assert page.selector == (
        "flow-base-prompt-box :is(flow-ingredient-bar img, flow-ingredient-chip img, "
        "flow-image-ingredient-chip img, img[alt*='Ingredient' i], img[alt*='reference' i]), "
        "div.base-prompt-box :is(flow-ingredient-bar img, flow-ingredient-chip img, "
        "flow-image-ingredient-chip img, img[alt*='Ingredient' i], img[alt*='reference' i]), "
        "form:has([contenteditable='true']) :is(flow-ingredient-bar img, flow-ingredient-chip img, "
        "flow-image-ingredient-chip img, img[alt*='Ingredient' i], img[alt*='reference' i])"
    )


@pytest.mark.parametrize("canary_shot_ids", [None, ["shot_1"]])
def test_flow_retry_boundary_preserves_one_attempt_canary(canary_shot_ids):
    from youtube_automation.visuals import flow_generator as generator

    reservations = ["initial"]
    sends = ["initial"]

    def reserve():
        reservations.append("retry")

    def dispatch():
        sends.append("retry")

    if canary_shot_ids is not None:
        with pytest.raises(RuntimeError, match="cannot retry"):
            generator._retry_flow_action(canary_shot_ids, reserve, dispatch)
        assert reservations == ["initial"]
        assert sends == ["initial"]
    else:
        generator._retry_flow_action(canary_shot_ids, reserve, dispatch)
        assert reservations == ["initial", "retry"]
        assert sends == ["initial", "retry"]


def test_flow_startup_uses_runtime_profile_over_stale_environment(tmp_path, monkeypatch):
    from youtube_automation.visuals import flow_generator as generator

    requested = []
    monkeypatch.setattr("youtube_automation.core.utils.active_profile_index", lambda: 3)
    monkeypatch.setattr(generator, "get_config_value", lambda key, default=None: "2" if key == "ACTIVE_PROFILE_INDEX" else default)
    monkeypatch.setattr(generator, "sync_playwright", MagicMock())

    def connect(client, *, port, profile_index, browser_type):
        requested.append(profile_index)
        raise RuntimeError("offline startup probe")

    monkeypatch.setattr(generator, "ensure_cdp_browser", connect)
    with pytest.raises(RuntimeError, match="offline startup probe"):
        generator._main(str(tmp_path), canary_shot_ids=["first"])
    assert requested == ["3"]


def test_canary_keeps_order_and_requires_scene_reference_closure():
    from youtube_automation.visuals.flow_generator import StoryboardFrame, _select_canary_storyboard

    frames = [StoryboardFrame(index=i, timestamp="[00:00]", prompt_text="scene", raw_payload={"adaptive_shot": {"shot_id": f"s{i}", "asset_id": f"a{i}", "reference_asset_id": "a1" if i == 3 else None}}) for i in range(1, 5)]
    assert _select_canary_storyboard(frames, ["s3", "s1"]) == [frames[0], frames[2]]
    with pytest.raises(ValueError, match="dependency"):
        _select_canary_storyboard(frames, ["s3"])
    with pytest.raises(ValueError, match="current adaptive"):
        _select_canary_storyboard(frames, ["s9"])
    with pytest.raises(ValueError, match="distinct"):
        _select_canary_storyboard(frames, ["s1", "s1"])
    with pytest.raises(ValueError, match="three"):
        _select_canary_storyboard(frames, ["s1", "s2", "s3", "s4"])


def test_cached_canary_does_not_open_or_request_gemini(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from youtube_automation.visuals import flow_generator as generator

    (tmp_path / "episode_brief.json").write_text("{}")
    context = SimpleNamespace(pages=[SimpleNamespace(url="https://flow.google.com/project/proof")], new_page=lambda: pytest.fail("Canary must not open Gemini"))
    monkeypatch.setattr(generator, "sync_playwright", MagicMock())
    monkeypatch.setattr(generator, "ensure_cdp_browser", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(generator, "prepare_browser_context", lambda *_: context)
    monkeypatch.setattr(generator, "clean_context_tabs", lambda *_: None)

    def prepare(root, request):
        with pytest.raises(RuntimeError, match="model requests are disabled"):
            request("Unexpected planning")
        raise RuntimeError("verified cached canary seam")

    monkeypatch.setattr(flow, "prepare_flow", prepare)
    with pytest.raises(RuntimeError, match="verified cached canary seam"):
        generator._main(str(tmp_path), canary_shot_ids=["first"])


def test_canary_verification_never_declares_the_remaining_plan_complete(tmp_path, monkeypatch):
    from types import SimpleNamespace

    plan = SimpleNamespace(shots=[SimpleNamespace(shot_id="first", asset_id="a1", operation="generate"), SimpleNamespace(shot_id="later", asset_id="a2", operation="generate")])
    monkeypatch.setattr(flow, "accepted_asset", lambda root, shot, brief: {} if shot.shot_id == "first" else None)
    flow.verify_generated_assets(tmp_path, plan, SimpleNamespace(), shot_ids={"first"})
    with pytest.raises(RuntimeError, match="a2"):
        flow.verify_generated_assets(tmp_path, plan, SimpleNamespace())
    with pytest.raises(ValueError, match="scope"):
        flow.verify_generated_assets(tmp_path, plan, SimpleNamespace(), shot_ids={"unknown"})


def test_schulte_edit_history_never_reaches_flow_payloads(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    calls = []
    diagrams = [SimpleNamespace(operation=operation, local_composition="schulte_challenge", asset_id=f"grid_{index}")
                for index, operation in enumerate(("generate", "replace", "reuse"))]
    plan = SimpleNamespace(shots=diagrams, total_frames=600, fps=30)
    brief = SimpleNamespace(version=2)
    monkeypatch.setattr(flow, "load_brief", lambda _: brief)
    monkeypatch.setattr(flow, "ensure_shot_plan", lambda *_: plan)
    monkeypatch.setattr(flow, "ensure_local_canvas", lambda root, shot, _brief: calls.append(shot))
    flow.prepare_flow(tmp_path, lambda _: pytest.fail("No model call expected"))
    assert calls == diagrams
    assert json.loads((tmp_path / "flow_prompts.json").read_text()) == []


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
    assert "flow-base-prompt-box :is(flow-ingredient-chip)" in selector
    assert "form:has([contenteditable='true']) :is(flow-ingredient-chip)" in selector


def test_flow_changelog_dialog_is_dismissed_and_confirmed_hidden():
    from youtube_automation.visuals.flow_generator import dismiss_blocking_flow_modals

    page = MagicMock()
    hidden = MagicMock()
    hidden.is_visible.return_value = False
    modal = MagicMock()
    modal.is_visible.side_effect = [True, False]
    close = MagicMock()
    close.is_visible.return_value = True
    modal.locator.return_value.first = close

    def locate(selector):
        result = MagicMock()
        result.first = modal if selector == "[role='dialog']" else hidden
        return result

    page.locator.side_effect = locate
    page.get_by_text.return_value.first = hidden

    assert dismiss_blocking_flow_modals(page) is True
    close.click.assert_called_once_with(force=True)
    modal.wait_for.assert_called_once_with(state="hidden", timeout=5000)
    page.keyboard.press.assert_not_called()


def test_unknown_flow_dialog_is_not_blindly_escaped_or_accepted():
    from youtube_automation.visuals.flow_generator import dismiss_blocking_flow_modals

    page = MagicMock()
    hidden = MagicMock()
    hidden.is_visible.return_value = False
    modal = MagicMock()
    modal.is_visible.return_value = True
    modal.locator.return_value.first = hidden

    def locate(selector):
        result = MagicMock()
        result.first = modal if selector == "[role='dialog']" else hidden
        return result

    page.locator.side_effect = locate
    page.get_by_text.return_value.first = hidden

    assert dismiss_blocking_flow_modals(page) is False
    page.keyboard.press.assert_not_called()


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


def _flow_reference_case(
    monkeypatch,
    tmp_path,
    *,
    with_character,
    receipt_url,
    preview_url,
    pixel_sha256="expected-pixels",
):
    from types import SimpleNamespace

    from youtube_automation.production import characters
    from youtube_automation.visuals import asset_studio, flow_generator, image_extractor

    preview = MagicMock()
    preview.get_attribute.return_value = preview_url
    preview.is_visible.return_value = True
    scene_chip = MagicMock()
    scene_chip.locator.return_value.all.return_value = [preview]
    page = MagicMock()
    page.url = "https://flow.google.com/project/test"
    receipt = {"source_url": receipt_url, "pixel_sha256": "expected-pixels"}
    extraction_calls = []

    def extract_high_res_image(_page, image, path, *, min_size_kb):
        extraction_calls.append((image, path, min_size_kb))
        return True

    monkeypatch.setattr(image_extractor, "extract_high_res_image", extract_high_res_image)
    monkeypatch.setattr(flow, "pixel_digest", lambda _path: pixel_sha256)

    if with_character:
        character_chip = object()
        monkeypatch.setattr(
            asset_studio,
            "visible_episode_ingredients",
            lambda _page: [character_chip, scene_chip],
        )
        monkeypatch.setattr(flow, "load_brief", lambda _root: object())
        monkeypatch.setattr(
            characters,
            "read_character_receipt",
            lambda *_args, **_kwargs: {},
        )
        monkeypatch.setattr(
            flow,
            "_character_chip_matches",
            lambda _page, chip, _receipt: chip is character_chip,
        )
        monkeypatch.setattr(flow, "read_receipt", lambda *_args: receipt)
        shot = SimpleNamespace(
            shot_id="shot-1",
            character_ids=("character-1",),
            reference_asset_id="scene-1",
        )
        def verify():
            return flow.verify_adaptive_prompt_references(
                page, tmp_path, shot, profile_index="0"
            )
    else:
        monkeypatch.setattr(
            flow_generator,
            "visible_attached_prompt_images",
            lambda _page: [preview],
        )
        monkeypatch.setattr(flow, "read_receipt", lambda *_args: receipt)
        def verify():
            return flow.verify_exact_reference(page, tmp_path, "scene-1")

    return verify, extraction_calls


@pytest.mark.parametrize("with_character", [False, True])
@pytest.mark.parametrize(
    ("receipt_url", "preview_url"),
    [
        (
            "https://flow-content.google/image/native-image",
            "https://flow.google.com/asb/preview-image=w400",
        ),
        (
            "https://lh3.googleusercontent.com/asb/preview-image=s256",
            "https://flow-content.google/image/native-image",
        ),
    ],
)
def test_cross_namespace_reference_uses_exact_pixel_verifier(
    monkeypatch, tmp_path, with_character, receipt_url, preview_url
):
    verify, extraction_calls = _flow_reference_case(
        monkeypatch,
        tmp_path,
        with_character=with_character,
        receipt_url=receipt_url,
        preview_url=preview_url,
    )

    assert verify() is None
    assert len(extraction_calls) == 1
    assert extraction_calls[0][2] == 1


@pytest.mark.parametrize("with_character", [False, True])
@pytest.mark.parametrize(
    (
        "receipt_url",
        "preview_url",
        "pixel_sha256",
        "identity_overrides",
        "expected_extractions",
    ),
    [
        (
            "https://flow-content.google/image/native-image",
            "https://flow.google.com/asb/preview-image=w400",
            "wrong-pixels",
            None,
            1,
        ),
        (
            "https://flow-content.google/image/native-first",
            "https://flow-content.google/image/native-second",
            "expected-pixels",
            None,
            0,
        ),
        (
            "https://flow.google.com/asb/alias-first=w400",
            "https://flow.google.com/asb/alias-second=w400",
            "expected-pixels",
            None,
            0,
        ),
        (
            "receipt",
            "preview",
            "expected-pixels",
            {"receipt": "vendor:receipt", "preview": "native-image"},
            0,
        ),
        (
            "https://flow-content.google/image/native-image",
            "https://untrusted.example/image/preview-image",
            "expected-pixels",
            None,
            0,
        ),
    ],
    ids=[
        "wrong_pixels",
        "wrong_native_id",
        "wrong_asb_alias",
        "unknown_namespace_id",
        "unknown_url_namespace",
    ],
)
def test_reference_mismatch_uses_pixels_only_for_trusted_alias_native_pair(
    monkeypatch,
    tmp_path,
    with_character,
    receipt_url,
    preview_url,
    pixel_sha256,
    identity_overrides,
    expected_extractions,
):
    verify, extraction_calls = _flow_reference_case(
        monkeypatch,
        tmp_path,
        with_character=with_character,
        receipt_url=receipt_url,
        preview_url=preview_url,
        pixel_sha256=pixel_sha256,
    )
    if identity_overrides is not None:
        monkeypatch.setattr(
            flow,
            "_provider_image_id",
            lambda url: identity_overrides[url],
        )

    with pytest.raises(RuntimeError):
        verify()
    assert len(extraction_calls) == expected_extractions
