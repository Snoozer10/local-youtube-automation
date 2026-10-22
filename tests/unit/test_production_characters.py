import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image
from pydantic import ValidationError
from unit.test_production_shots import shot, version_three_brief

from youtube_automation.production import characters, flow
from youtube_automation.production.assets import file_digest, pixel_digest, recipe
from youtube_automation.production.contracts import EpisodeCharacter, fingerprint
from youtube_automation.production.shots import (
    ShotPlan,
    _character_identity_error,
    _human_quality_feedback,
    _semantic_planning_prompt,
    _validate_editorial_quality,
    resolve_editorial_policy,
)
from youtube_automation.production.visual_gate import VisualBudgetExceeded
from youtube_automation.visuals.asset_studio import visible_episode_ingredients


def cast_brief():
    brief = version_three_brief()
    brief.visual_strategy.characters = [EpisodeCharacter(
        character_id="alex", name="Alex", origin="illustrative",
        description="Adult with curly black hair, round glasses and a plain blue shirt",
        rationale="An illustrative participant connects the before/after scenes",
    )]
    return brief


def save_receipt(root, brief):
    image = root / "canonical.png"
    Image.new("RGB", (256, 256), "blue").save(image)
    part = characters.CharacterImage(path=image.name, sha256=file_digest(image), pixel_sha256=pixel_digest(image), source_url="https://flow-content.google/image/portrait")
    receipt = characters.CharacterReceipt(
        character_id="alex", definition_sha256=fingerprint(brief.visual_strategy.characters[0]),
        recipe=characters.character_recipe(brief, "alex"), provider_id="provider-alex",
        provider_name=characters.character_provider_name(brief, "alex"),
        project_url="https://flow.google.com/project/proof", profile_index="3", portrait=part, body=part,
    )
    directory = root / "character_receipts"
    directory.mkdir(exist_ok=True)
    (directory / "alex.json").write_text(receipt.model_dump_json(), encoding="utf-8")
    return receipt


def test_optional_cast_fields_preserve_existing_fingerprints():
    brief = version_three_brief()
    old = brief.model_dump(mode="json")
    old["visual_strategy"].pop("characters")
    assert fingerprint(brief) == fingerprint(old)
    item = shot()
    old_shot = item.model_dump(mode="json")
    old_shot.pop("character_ids")
    assert fingerprint(item) == fingerprint(old_shot)


def test_single_appearance_receipt_preserves_exact_bytes_and_binding(tmp_path):
    brief = cast_brief()
    receipt = save_receipt(tmp_path, brief)
    receipt.body = None
    path = tmp_path / "character_receipts" / "alex.json"
    path.write_text(receipt.model_dump_json(), encoding="utf-8")
    assert characters.read_character_receipt(tmp_path, brief, "alex").body is None
    (tmp_path / receipt.portrait.path).write_bytes(b"changed")
    with pytest.raises(ValueError, match="canonical image changed"):
        characters.read_character_receipt(tmp_path, brief, "alex")


def test_empty_aliases_preserve_legacy_receipt_serialization(tmp_path):
    receipt = save_receipt(tmp_path, cast_brief())
    assert "source_aliases" not in receipt.portrait.model_dump(mode="json")
    assert "preview" not in receipt.portrait.model_dump(mode="json")
    old = fingerprint(receipt)
    receipt.portrait.source_aliases = ["https://flow.google.com/asb/canonical=s1600-rw"]
    assert fingerprint(receipt) != old


def test_saved_resize_alias_failure_replays_without_fuzzy_matching(tmp_path):
    from pathlib import Path

    case = json.loads((Path(__file__).parents[1] / "fixtures/flow_reference_alias_v1.json").read_text(encoding="utf-8"))
    receipt = save_receipt(tmp_path, cast_brief())
    receipt.portrait.source_url = case["canonical_source"]
    chip, image = MagicMock(), MagicMock()
    chip.evaluate.return_value = ""
    chip.get_attribute.return_value = None
    chip.locator.return_value.count.return_value = 1
    chip.locator.return_value.all.return_value = [image]
    image.is_visible.return_value = True
    image.get_attribute.return_value = case["attached_preview"]
    assert not flow._character_chip_matches(MagicMock(), chip, receipt)
    receipt.portrait.source_aliases = [case["verified_editor_alias"]]
    assert flow._character_chip_matches(MagicMock(), chip, receipt)
    image.get_attribute.return_value = case["wrong_preview"]
    assert not flow._character_chip_matches(MagicMock(), chip, receipt)


def test_proven_asb_alias_matches_only_its_exact_character(tmp_path, monkeypatch):
    receipt = save_receipt(tmp_path, cast_brief())
    receipt.portrait.source_aliases = ["https://flow.google.com/asb/canonical=s1600-rw"]
    chip, image = MagicMock(), MagicMock()
    chip.evaluate.return_value = ""
    chip.get_attribute.return_value = None
    chip.locator.return_value.count.return_value = 1
    chip.locator.return_value.all.return_value = [image]
    image.is_visible.return_value = True
    image.get_attribute.return_value = "https://lh3.googleusercontent.com/asb/canonical"
    monkeypatch.setattr("youtube_automation.visuals.image_extractor.extract_high_res_image", lambda *_a, **_k: pytest.fail("Alias matching must not use fuzzy pixels"))
    assert flow._character_chip_matches(MagicMock(), chip, receipt)
    image.get_attribute.return_value = "https://lh3.googleusercontent.com/asb/another-person"
    assert not flow._character_chip_matches(MagicMock(), chip, receipt)
    image.get_attribute.return_value = "https://lh3.googleusercontent.com/asb/canonical"
    chip.locator.return_value.count.return_value = 0
    assert not flow._character_chip_matches(MagicMock(), chip, receipt)


@pytest.mark.parametrize("url,expected", [
    ("https://flow-content.google/image/portrait?Expires=42", "portrait"),
    ("https://flow.google.com/asb/canonical=s1600-rw", "asb:canonical"),
    ("https://lh3.googleusercontent.com/asb/canonical=s512", "asb:canonical"),
    ("https://unrelated.example/asb/canonical", ""),
    ("https://flow.google.com/asb/canonical/another", ""),
])
def test_provider_image_identity_ignores_only_trusted_resize_modifiers(url, expected):
    assert flow._provider_image_id(url) == expected


def test_alias_registration_preserves_original_receipt_without_a_send(tmp_path, monkeypatch):
    from youtube_automation.visuals import asset_studio

    brief = cast_brief()
    receipt = save_receipt(tmp_path, brief)
    receipt.body = None
    receipt_path = tmp_path / "character_receipts/alex.json"
    receipt_path.write_text(receipt.model_dump_json(), encoding="utf-8")
    original = receipt_path.read_bytes()

    def prove(page, name, provider_id, source, pixels, output):
        assert (name, provider_id, source, pixels) == (receipt.provider_name, receipt.provider_id, receipt.portrait.source_url, receipt.portrait.pixel_sha256)
        output.mkdir(parents=True)
        Image.new("RGB", (128, 128), "blue").save(output / "alias_ingredient_preview.png")
        return "https://flow.google.com/asb/canonical=s1600-rw"

    monkeypatch.setattr(asset_studio, "capture_episode_character_alias", prove)
    monkeypatch.setattr("youtube_automation.production.visual_gate.reserve_flow_submission", lambda *_a: pytest.fail("Alias proof cannot spend a send"))
    plan = SimpleNamespace(shots=[shot(character_ids=["alex"])])
    characters.ensure_episode_characters(MagicMock(), tmp_path, plan, brief, profile_index="3", project_url=receipt.project_url)
    bound = characters.read_character_receipt(tmp_path, brief, "alex")
    assert bound.portrait.source_aliases == ["https://flow.google.com/asb/canonical=s1600-rw"]
    assert bound.portrait.pixel_sha256 == receipt.portrait.pixel_sha256
    assert bound.portrait.preview is not None
    assert bound.portrait.preview.pixel_sha256 != receipt.portrait.pixel_sha256
    characters.ensure_episode_characters(MagicMock(), tmp_path, plan, brief, profile_index="3", project_url=receipt.project_url)
    assert next((tmp_path / ".character_candidates/alex").glob("receipt_before_alias_*.json")).read_bytes() == original


def test_rotating_asb_tokens_require_exact_frozen_preview_pixels(tmp_path, monkeypatch):
    from pathlib import Path

    case = json.loads((Path(__file__).parents[1] / "fixtures/flow_rotating_preview_v1.json").read_text(encoding="utf-8"))
    receipt = save_receipt(tmp_path, cast_brief())
    preview_path = tmp_path / "preview.png"
    Image.new("RGB", (128, 128), "blue").save(preview_path)
    receipt.portrait.preview = characters.CharacterPreview(path=preview_path.name, sha256=file_digest(preview_path), pixel_sha256=pixel_digest(preview_path))
    chip, image = MagicMock(), MagicMock()
    chip.evaluate.return_value = ""
    chip.get_attribute.return_value = None
    chip.locator.return_value.count.return_value = 1
    chip.locator.return_value.all.return_value = [image]
    image.is_visible.return_value = True
    image.get_attribute.return_value = case["reattached_preview"]
    color = ["blue"]

    def extract(_page, _image, path, **_kwargs):
        Image.new("RGB", (128, 128), color[0]).save(path)
        return True

    monkeypatch.setattr("youtube_automation.visuals.image_extractor.extract_high_res_image", extract)
    assert flow._character_chip_matches(MagicMock(), chip, receipt)
    color[0] = "red"
    assert not flow._character_chip_matches(MagicMock(), chip, receipt)
    chip.get_attribute.return_value = "wrong-character"
    assert not flow._character_chip_matches(MagicMock(), chip, receipt)


@pytest.mark.parametrize("escape", [False, True])
def test_character_preview_tampering_or_path_escape_blocks_receipt(tmp_path, escape):
    brief = cast_brief()
    receipt = save_receipt(tmp_path, brief)
    receipt.portrait.preview = characters.CharacterPreview(path="../outside.png" if escape else receipt.portrait.path, sha256=receipt.portrait.sha256, pixel_sha256=receipt.portrait.pixel_sha256)
    if not escape:
        receipt.portrait.preview.pixel_sha256 = "0" * 64
    (tmp_path / "character_receipts/alex.json").write_text(receipt.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="preview image changed"):
        characters.read_character_receipt(tmp_path, brief, "alex")


@pytest.mark.parametrize("card_count", [1, 2])
def test_character_search_waits_for_results_but_rejects_duplicate_exact_names(monkeypatch, card_count):
    from youtube_automation.visuals import asset_studio

    page, overlay, control, results = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    page.locator.return_value.all.return_value = [overlay]
    overlay.is_visible.return_value = True
    overlay.get_by_role.return_value.all.return_value = [control]
    control.is_visible.return_value = True
    overlay.locator.return_value.filter.return_value = results
    ready = []
    query = {"value": "Alex", "refreshed": False}

    def fill_query(value):
        query["refreshed"] = query["refreshed"] or value != query["value"]
        query["value"] = value

    control.fill.side_effect = fill_query
    results.first.wait_for.side_effect = lambda **_k: ready.append(True)
    cards = [MagicMock() for _ in range(card_count)]
    for card in cards:
        card.is_visible.return_value = True
    results.all.side_effect = lambda: cards if ready and query["refreshed"] and query["value"] == "Alex" else []
    monkeypatch.setattr(asset_studio, "visible_episode_ingredients", lambda *_: [])
    if card_count == 2:
        with pytest.raises(RuntimeError, match="found 2"):
            asset_studio.attach_episode_character(page, "Alex")
        assert all(not card.click.called for card in cards)
    else:
        asset_studio.attach_episode_character(page, "Alex")
        cards[0].click.assert_called_once()


def test_character_project_recovery_uses_current_profile_receipt(tmp_path):
    brief = cast_brief()
    receipt = save_receipt(tmp_path, brief)
    plan = SimpleNamespace(shots=[SimpleNamespace(character_ids=["alex"])])
    assert characters.resolve_character_project(tmp_path, plan, brief, profile_index="3", saved_project_url=None) == receipt.project_url
    with pytest.raises(characters.CharacterProfileMismatch, match="pinned to Flow profile 3"):
        characters.resolve_character_project(tmp_path, plan, brief, profile_index="2", saved_project_url=None)
    with pytest.raises(ValueError, match="conflicts"):
        characters.resolve_character_project(tmp_path, plan, brief, profile_index="3", saved_project_url="https://flow.google.com/project/unrelated")


@pytest.mark.parametrize("kind", ["scene", "character"])
def test_blob_reference_verification_passes_image_element_to_extractor(tmp_path, monkeypatch, kind):
    receipt = save_receipt(tmp_path, cast_brief())
    image = MagicMock()
    image.is_visible.return_value = True
    image.get_attribute.return_value = "blob:canonical-appearance"
    chip = MagicMock()
    chip.evaluate.return_value = receipt.provider_name
    chip.get_attribute.return_value = None
    chip.locator.return_value.all.return_value = [image]

    def extract(page, img_locator, save_path, min_size_kb):
        assert img_locator is image
        Image.new("RGB", (256, 256), "blue").save(save_path)
        return True

    monkeypatch.setattr("youtube_automation.visuals.image_extractor.extract_high_res_image", extract)
    if kind == "scene":
        assert flow._scene_reference_chip_matches(MagicMock(), chip, {"source_url": "blob:source", "pixel_sha256": receipt.portrait.pixel_sha256})
    else:
        receipt.body = None
        assert flow._character_chip_matches(MagicMock(), chip, receipt)


def test_visible_ingredient_does_not_count_its_nested_button_twice():
    page = MagicMock()
    wrapper, nested_button = MagicMock(), MagicMock()
    for element in (wrapper, nested_button):
        element.is_visible.return_value = True
    wrapper.evaluate.return_value = True
    nested_button.evaluate.return_value = False
    page.locator.return_value.all.return_value = [wrapper, nested_button]
    assert visible_episode_ingredients(page) == [wrapper]


def test_current_flow_unlabelled_character_chip_requires_canonical_image(tmp_path):
    receipt = save_receipt(tmp_path, cast_brief())
    chip, image = MagicMock(), MagicMock()
    chip.evaluate.return_value = ""
    chip.get_attribute.return_value = None
    chip.locator.return_value.count.return_value = 1
    chip.locator.return_value.all.return_value = [image]
    image.is_visible.return_value = True
    image.get_attribute.return_value = receipt.portrait.source_url
    assert flow._character_chip_matches(MagicMock(), chip, receipt)
    image.get_attribute.return_value = "https://flow-content.google/image/another-person"
    assert not flow._character_chip_matches(MagicMock(), chip, receipt)
    image.get_attribute.return_value = receipt.portrait.source_url
    chip.locator.return_value.count.return_value = 0
    assert not flow._character_chip_matches(MagicMock(), chip, receipt)


def test_typed_source_characters_require_evidence_and_frozen_identity():
    with pytest.raises(ValidationError, match="exact source excerpt"):
        EpisodeCharacter(character_id="alex", name="Alex", origin="source_narration", description="Blue shirt", rationale="Narrated person")
    character = cast_brief().visual_strategy.characters[0]
    with pytest.raises(ValidationError):
        character.description = "Another person"


def test_long_gap_character_moves_scene_without_migrating_scene_objects():
    brief = cast_brief()
    items = [shot(shot_id=f"s{i}", asset_id=f"a{i}", scene_id=f"scene{i}", entity_ids=[f"place{i}"],
                  character_ids=["alex"] if i in {0, 8} else [],
                  narrative_role="story_subject" if i in {0, 8} else "background",
                  subject=f"{'Alex on' if i in {0, 8} else 'View of'} place{i}",
                  visible_state="Walking along a branching path", composition=f"Open view of place{i}",
                  start_frame=i * 60, end_frame=(i + 1) * 60,
                  framing=["wide", "medium", "insert", "overhead"][i % 4]) for i in range(9)]
    plan = ShotPlan(version=2, timeline_sha256="a" * 64, brief_sha256=fingerprint(brief), fps=30,
                    total_frames=540, editorial_policy=resolve_editorial_policy(brief), shots=items)
    _validate_editorial_quality(plan, brief, complete=False)
    assert items[0].character_ids == items[-1].character_ids
    items[-1].entity_ids = ["place0"]
    with pytest.raises(ValueError, match="cannot migrate"):
        _validate_editorial_quality(plan, brief, complete=False)


def test_unknown_cast_and_character_as_scene_entity_reject():
    brief = cast_brief()
    assert "Unknown" in _character_identity_error(shot(character_ids=["stranger"]), brief)
    assert "never scene-local" in _character_identity_error(shot(entity_ids=["alex"]), brief)


def test_initial_prompt_exposes_explicit_cast_without_forcing_a_protagonist():
    prompt = _semantic_planning_prompt(cast_brief(), [], [], [], 1, "")
    assert '"character_id": "alex"' in prompt
    assert "Do not invent a recurring protagonist" in prompt


@pytest.mark.parametrize("change", ["missing", "pixels", "profile", "definition"])
def test_character_receipt_fails_closed_when_binding_changes(tmp_path, change):
    brief = cast_brief()
    save_receipt(tmp_path, brief)
    if change == "missing":
        (tmp_path / "character_receipts" / "alex.json").unlink()
    if change == "pixels":
        Image.new("RGB", (256, 256), "red").save(tmp_path / "canonical.png")
    if change == "definition":
        brief.visual_strategy.characters = [brief.visual_strategy.characters[0].model_copy(update={"description": "Different hair"})]
    if change == "profile":
        with pytest.raises(characters.CharacterProfileMismatch, match="pinned to Flow profile 3"):
            characters.read_character_receipt(tmp_path, brief, "alex", profile_index="4")
    else:
        with pytest.raises((OSError, ValueError)):
            characters.read_character_receipt(tmp_path, brief, "alex", profile_index="3")


def test_dependent_asset_recipe_binds_exact_character_receipts(tmp_path):
    brief = cast_brief()
    save_receipt(tmp_path, brief)
    item = shot(character_ids=["alex"], subject="Alex on a path")
    with pytest.raises(ValueError, match="receipt lineage"):
        recipe(item, brief, None)
    assert recipe(item, brief, None, characters.character_lineage(tmp_path, brief, ["alex"])) != recipe(item, brief, None, {"alex": "a" * 64})


@pytest.mark.parametrize("chips", [[], ["wrong"], ["alex", "alex"], ["alex", "extra"]])
def test_exact_character_set_rejects_missing_wrong_duplicate_extra(tmp_path, monkeypatch, chips):
    from youtube_automation.visuals import asset_studio

    brief = cast_brief()
    save_receipt(tmp_path, brief)
    monkeypatch.setattr(flow, "load_brief", lambda *_: brief)
    monkeypatch.setattr(asset_studio, "visible_episode_ingredients", lambda *_: chips)
    monkeypatch.setattr(flow, "_character_chip_matches", lambda page, chip, receipt: chip == "alex")
    page = SimpleNamespace(url="https://flow.google.com/project/proof")
    with pytest.raises(RuntimeError, match="ingredient set|Exact character"):
        flow.verify_adaptive_prompt_references(page, tmp_path, shot(character_ids=["alex"]), "3")


def test_swapped_chip_blocks_second_immediate_submit_verification(tmp_path, monkeypatch):
    from youtube_automation.visuals import asset_studio

    brief = cast_brief()
    save_receipt(tmp_path, brief)
    monkeypatch.setattr(flow, "load_brief", lambda *_: brief)
    current = ["alex"]
    monkeypatch.setattr(asset_studio, "visible_episode_ingredients", lambda *_: current)
    monkeypatch.setattr(flow, "_character_chip_matches", lambda page, chip, receipt: chip == "alex")
    page = SimpleNamespace(url="https://flow.google.com/project/proof")
    item = shot(character_ids=["alex"])
    flow.verify_adaptive_prompt_references(page, tmp_path, item, "3")
    current[:] = ["wrong"]
    with pytest.raises(RuntimeError, match="Exact character"):
        flow.verify_adaptive_prompt_references(page, tmp_path, item, "3")


def test_scene_reference_must_match_unused_chip_not_a_character_image(tmp_path, monkeypatch):
    from youtube_automation.visuals import asset_studio

    brief = cast_brief()
    save_receipt(tmp_path, brief)
    monkeypatch.setattr(flow, "load_brief", lambda *_: brief)
    monkeypatch.setattr(asset_studio, "visible_episode_ingredients", lambda *_: ["alex", "unrelated"])
    monkeypatch.setattr(flow, "_character_chip_matches", lambda page, chip, receipt: chip == "alex")
    monkeypatch.setattr(flow, "read_receipt", lambda *_: {"source_url": "character-image"})
    inspected = []

    def scene_matches(page, chip, receipt):
        inspected.append(chip)
        return chip == "alex"

    monkeypatch.setattr(flow, "_scene_reference_chip_matches", scene_matches)
    page = SimpleNamespace(url="https://flow.google.com/project/proof")
    with pytest.raises(RuntimeError, match="Exact scene reference"):
        flow.verify_adaptive_prompt_references(page, tmp_path, shot(character_ids=["alex"], reference_asset_id="reference", operation="replace"), "3")
    assert inspected == ["unrelated"]


def test_character_creation_reserves_both_sends_and_preserves_uncertain_budget(tmp_path, monkeypatch):
    from youtube_automation.visuals import asset_studio

    brief = cast_brief()
    plan = SimpleNamespace(shots=[shot(character_ids=["alex"])], total_frames=600, fps=30)
    sends = []

    def uncertain(page, name, description, style, output, reserve):
        for stage in ["portrait", "body"]:
            reserve(stage)
            sends.append(stage)
        raise RuntimeError("Uncertain body send")

    monkeypatch.setattr(asset_studio, "create_episode_character", uncertain)
    monkeypatch.setattr(asset_studio, "preflight_episode_character", lambda *_: None)
    with pytest.raises(RuntimeError, match="Uncertain"):
        characters.ensure_episode_characters(MagicMock(), tmp_path, plan, brief, profile_index="3", project_url="project")
    assert sends == ["portrait", "body"]
    assert json.loads((tmp_path / "visual_spending.json").read_text())["flow_submissions"] == 2
    with pytest.raises(RuntimeError, match="reconciliation"):
        characters.ensure_episode_characters(MagicMock(), tmp_path, plan, brief, profile_index="3", project_url="project")
    assert json.loads((tmp_path / "visual_spending.json").read_text())["flow_submissions"] == 2


def test_character_send_cannot_cross_saved_budget(tmp_path, monkeypatch):
    from youtube_automation.visuals import asset_studio

    brief = cast_brief()
    plan = SimpleNamespace(shots=[shot(character_ids=["alex"])], total_frames=600, fps=30)
    (tmp_path / "visual_budget.json").write_text('{"version":1,"max_images":3,"require_review":false}')
    (tmp_path / "visual_spending.json").write_text('{"version":1,"flow_submissions":3}')

    def create(page, name, description, style, output, reserve):
        reserve("portrait")
        pytest.fail("Must stop before send")

    monkeypatch.setattr(asset_studio, "create_episode_character", create)
    monkeypatch.setattr(asset_studio, "preflight_episode_character", lambda *_: None)
    with pytest.raises(VisualBudgetExceeded):
        characters.ensure_episode_characters(MagicMock(), tmp_path, plan, brief, profile_index="3", project_url="project")


def test_human_feedback_excludes_paths_and_provider_details(tmp_path):
    from youtube_automation.production.review import HumanPreviewRejection

    brief = cast_brief()
    rejection = HumanPreviewRejection(reviewer="owner", plan_sha256="a" * 64, preview_sha256="b" * 64,
        source_sha256=brief.source_sha256, overall_rating=1.5, reasons=["Characters change appearance"],
        required_next="Fresh review", source="private-url", supersedes="private-path")
    (tmp_path / "human_review_rejection.json").write_text(rejection.model_dump_json())
    feedback = _human_quality_feedback(tmp_path, brief)
    assert "1.5" in feedback and "SUPERSEDES" in feedback
    assert "private" not in feedback


def test_unsupported_character_ui_spends_nothing_and_creates_no_send_intent(tmp_path, monkeypatch):
    from youtube_automation.visuals import asset_studio

    def unsupported(*_):
        raise RuntimeError("Episode character studio unsupported")

    monkeypatch.setattr(asset_studio, "preflight_episode_character", unsupported)
    create = MagicMock()
    monkeypatch.setattr(asset_studio, "create_episode_character", create)
    plan = SimpleNamespace(shots=[shot(character_ids=["alex"])], total_frames=600, fps=30)
    with pytest.raises(RuntimeError, match="unsupported"):
        characters.ensure_episode_characters(MagicMock(), tmp_path, plan, cast_brief(), profile_index="3", project_url="project")
    create.assert_not_called()
    assert not (tmp_path / "visual_spending.json").exists()
    assert not (tmp_path / ".publication_journal" / "characters" / "alex.json").exists()


@pytest.mark.parametrize("failure", ["success", "body_absent", "hidden_body", "body_click", "body_capture", "mixed_identity"])
def test_create_episode_character_reads_contenteditable_name_after_portrait_send(tmp_path, monkeypatch, failure):
    from youtube_automation.visuals import asset_studio

    phase = {"current": "portrait", "image_reads": 0}
    portrait_url = "https://flow-content.google/image/portrait"
    body_url = "https://flow-content.google/image/body"

    def visible(element):
        element.is_visible.return_value = True
        locator = MagicMock()
        locator.all.return_value = [element]
        return locator

    portrait_input, name_input, info = MagicMock(), MagicMock(), MagicMock()
    name_input.evaluate.side_effect = [None, True]
    name_input.inner_text.return_value = "Alex"
    name_input.input_value.side_effect = AssertionError("contenteditable has no input value")
    one_x, portrait_submit, body_submit = MagicMock(), MagicMock(), MagicMock()
    one_x.is_disabled.return_value = False
    portrait_submit.is_disabled.return_value = False
    body_submit.is_disabled.return_value = False
    create_body, done = MagicMock(), MagicMock()
    create_body.is_disabled.return_value = False
    create_body.click.side_effect = (
        RuntimeError("ambiguous body click") if failure == "body_click"
        else lambda: phase.update(current="body")
    )
    body_input, dialog = MagicMock(), MagicMock()
    portrait_image, body_image, unknown_image = MagicMock(), MagicMock(), MagicMock()
    hidden_body = MagicMock()
    hidden_body.is_visible.return_value = False
    for image, url in ((portrait_image, portrait_url), (body_image, body_url)):
        image.is_visible.return_value = True
        image.get_attribute.side_effect = lambda name, url=url: url if name == "src" else None
        image.evaluate.return_value = True
    unknown_image.is_visible.return_value = True
    unknown_image.get_attribute.side_effect = lambda name: "https://unrelated.example/image/portrait" if name == "src" else None
    unknown_image.evaluate.return_value = True

    def page_locator(selector):
        if "Describe your character" in selector:
            return visible(portrait_input)
        if "Character Name" in selector:
            return visible(name_input)
        if "Describe how your character acts" in selector or "Character Info" in selector:
            return visible(info)
        if selector == "main img":
            locator = MagicMock()

            def images():
                phase["image_reads"] += 1
                if phase["image_reads"] == 1:
                    return []
                if phase["current"] == "portrait":
                    return [portrait_image, unknown_image] if failure == "mixed_identity" else [portrait_image]
                return [body_image]

            locator.all.side_effect = images
            return locator
        if selector.startswith("mat-dialog-container"):
            return visible(dialog)
        if "button[aria-label*='Generate'" in selector:
            return visible(portrait_submit if phase["current"] == "portrait" else body_submit)
        raise AssertionError(f"Unexpected page locator: {selector}")

    def dialog_locator(selector):
        if "textarea" in selector:
            return visible(body_input)
        if "button[aria-label*='Generate'" in selector:
            return visible(body_submit)
        raise AssertionError(f"Unexpected dialog locator: {selector}")

    dialog.locator.side_effect = dialog_locator
    page = MagicMock()
    page.url = "https://flow.google.com/project/proof/character/provider-alex"
    page.locator.side_effect = page_locator

    def get_by_role(role, *, name, include_hidden=False, **_kwargs):
        if name == "1x":
            return visible(one_x)
        if name == "Create Body":
            if failure == "body_absent":
                locator = MagicMock()
                locator.all.return_value = []
                return locator
            if failure == "hidden_body":
                locator = MagicMock()
                locator.all.return_value = [hidden_body] if include_hidden else []
                return locator
            return visible(create_body)
        if name == "Done":
            return visible(done)
        raise AssertionError(f"Unexpected role locator: {role} {name}")

    page.get_by_role.side_effect = get_by_role
    def extract(_page, image, path, **_kwargs):
        if failure == "body_capture" and image is body_image:
            return False
        Image.new("RGB", (256, 256), "blue").save(path)
        return True

    monkeypatch.setattr("youtube_automation.visuals.image_extractor.extract_high_res_image", extract)
    reserved = []
    if failure in {"success", "body_absent"}:
        result = asset_studio.create_episode_character(
            page, "Alex", "curly hair and glasses", "illustrative", tmp_path / "candidate", reserved.append,
        )
        assert result["provider_id"] == "provider-alex"
        if failure == "success":
            assert reserved == ["portrait", "body"]
        else:
            assert result["body_path"] is None
            assert reserved == ["portrait"]
        done.click.assert_called_once()
    else:
        with pytest.raises(RuntimeError):
            asset_studio.create_episode_character(
                page, "Alex", "curly hair and glasses", "illustrative", tmp_path / "candidate", reserved.append,
            )
        assert reserved == (["portrait", "body"] if failure == "body_capture" else ["portrait"])
        done.click.assert_not_called()
        assert not (tmp_path / "candidate" / "body.png").exists()
    name_input.inner_text.assert_called_once_with()
    name_input.input_value.assert_not_called()


def test_character_preflight_rejects_missing_exact_one_x_before_submit():
    from youtube_automation.visuals import asset_studio

    page, composer = MagicMock(), MagicMock()
    page.url = "https://flow.google.com/project/proof/character"
    page.locator.return_value = composer
    composer.first.wait_for.return_value = None
    composer.all.return_value = [composer]
    composer.is_visible.return_value = True
    missing = MagicMock()
    missing.all.return_value = []
    page.get_by_role.return_value = missing

    with pytest.raises(RuntimeError, match="unsupported"):
        asset_studio.preflight_episode_character(page)

    page.locator.assert_called_once()
    page.get_by_role.assert_called_once_with("button", name="1x", exact=True)


def test_canary_character_scope_ignores_unselected_profile_pin_and_spends_only_selected_character(tmp_path, monkeypatch):
    from youtube_automation.visuals import asset_studio

    brief = cast_brief()
    alex = brief.visual_strategy.characters[0]
    riley = EpisodeCharacter(
        character_id="riley", name="Riley", origin="illustrative",
        description="Adult with short auburn hair and a green jacket",
        rationale="A separate illustrative participant",
    )
    brief.visual_strategy.characters = [alex, riley]
    project_url = "https://flow.google.com/project/proof"
    save_receipt(tmp_path, brief)
    riley_image = tmp_path / "riley.png"
    Image.new("RGB", (256, 256), "green").save(riley_image)
    riley_part = characters.CharacterImage(
        path=riley_image.name, sha256=file_digest(riley_image), pixel_sha256=pixel_digest(riley_image),
        source_url="https://flow-content.google/image/riley",
    )
    riley_receipt = characters.CharacterReceipt(
        character_id="riley", definition_sha256=fingerprint(riley),
        recipe=characters.character_recipe(brief, "riley"), provider_id="provider-riley",
        provider_name=characters.character_provider_name(brief, "riley"), project_url=project_url,
        profile_index="4", portrait=riley_part, body=riley_part,
    )
    riley_path = tmp_path / "character_receipts" / "riley.json"
    riley_path.write_text(riley_receipt.model_dump_json(), encoding="utf-8")
    riley_bytes = riley_path.read_bytes()
    plan = SimpleNamespace(
        shots=[shot(shot_id="alex-shot", asset_id="asset-alex", character_ids=["alex"]),
               shot(shot_id="riley-shot", asset_id="asset-riley", character_ids=["riley"])],
        total_frames=600, fps=30,
    )

    assert characters.resolve_character_project(
        tmp_path, plan, brief, profile_index="3", saved_project_url=None, character_ids={"alex"},
    ) == project_url
    (tmp_path / "character_receipts" / "alex.json").unlink()
    monkeypatch.setattr(asset_studio, "preflight_episode_character", lambda *_: None)

    def create(_page, name, _description, _style, output, reserve):
        assert name == characters.character_provider_name(brief, "alex")
        reserve("portrait")
        output.mkdir(parents=True, exist_ok=True)
        portrait = output / "portrait.png"
        Image.new("RGB", (256, 256), "blue").save(portrait)
        return {
            "provider_id": "provider-alex-new", "portrait_path": str(portrait),
            "portrait_url": "https://flow-content.google/image/alex-new",
        }

    monkeypatch.setattr(asset_studio, "create_episode_character", create)
    page = SimpleNamespace(url=project_url)
    page.goto = lambda url, **_kwargs: setattr(page, "url", url)
    characters.ensure_episode_characters(
        page, tmp_path, plan, brief, profile_index="3", project_url=project_url, character_ids={"alex"},
    )

    assert characters.read_character_receipt(tmp_path, brief, "alex", profile_index="3").provider_id == "provider-alex-new"
    assert riley_path.read_bytes() == riley_bytes
    assert json.loads((tmp_path / "visual_spending.json").read_text(encoding="utf-8"))["flow_submissions"] == 1


def test_recipe_changed_journal_without_receipt_requires_manual_reconciliation(tmp_path, monkeypatch):
    from youtube_automation.visuals import asset_studio

    brief = cast_brief()
    old_recipe = characters.character_recipe(brief, "alex")
    brief.visual_strategy.characters = [brief.visual_strategy.characters[0].model_copy(
        update={"description": "Adult with straight brown hair and square glasses"},
    )]
    assert characters.character_recipe(brief, "alex") != old_recipe
    journal = tmp_path / ".publication_journal" / "characters" / "alex.json"
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({"character_id": "alex", "recipe": old_recipe, "state": "completed"}), encoding="utf-8")
    original = journal.read_bytes()
    monkeypatch.setattr(asset_studio, "preflight_episode_character", lambda *_: pytest.fail("Must stop before UI setup"))
    monkeypatch.setattr(asset_studio, "create_episode_character", lambda *_args, **_kwargs: pytest.fail("Must not create a replacement"))
    plan = SimpleNamespace(shots=[shot(character_ids=["alex"])], total_frames=600, fps=30)

    with pytest.raises(characters.CharacterReceiptReconciliationRequired, match="manual reconciliation"):
        characters.ensure_episode_characters(
            MagicMock(), tmp_path, plan, brief, profile_index="3", project_url="project", character_ids={"alex"},
        )

    assert journal.read_bytes() == original
    assert not (tmp_path / "character_receipts" / "alex.json").exists()
    assert not (tmp_path / "visual_spending.json").exists()


def test_character_lineage_ignores_alias_preview_but_tracks_canonical_pixels(tmp_path):
    brief = cast_brief()
    receipt = save_receipt(tmp_path, brief)
    before = characters.character_lineage(tmp_path, brief, ["alex"])
    preview_path = tmp_path / "alias-preview.png"
    Image.new("RGB", (128, 128), "red").save(preview_path)
    receipt.portrait.source_aliases = ["https://flow.google.com/asb/canonical=s1600-rw"]
    receipt.portrait.preview = characters.CharacterPreview(
        path=preview_path.name, sha256=file_digest(preview_path), pixel_sha256=pixel_digest(preview_path),
    )
    receipt_path = tmp_path / "character_receipts" / "alex.json"
    receipt_path.write_text(receipt.model_dump_json(), encoding="utf-8")
    assert characters.character_lineage(tmp_path, brief, ["alex"]) == before

    canonical = tmp_path / receipt.portrait.path
    Image.new("RGB", (256, 256), "purple").save(canonical)
    for image in (receipt.portrait, receipt.body):
        if image is not None:
            image.sha256 = file_digest(canonical)
            image.pixel_sha256 = pixel_digest(canonical)
    receipt_path.write_text(receipt.model_dump_json(), encoding="utf-8")
    assert characters.character_lineage(tmp_path, brief, ["alex"]) != before
