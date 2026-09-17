"""Unit tests for the validator module and relocated flow_image_generator utilities."""

import pytest
from pydantic import ValidationError

import flow_image_generator
import validator
from validator import (
    FrameItem,
    PipelineIntegrityError,
    parse_timestamp_seconds,
    verify_pipeline_integrity,
)

VALID_STYLE = (
    "2D graphic vector animation explainer style, crisp 3px black outlines, rich flat cel-shading"
)


def make_visual_prompt(**overrides):
    base = {
        "subject_details": "cartoon host in amber studio",
        "subject_action_increment": "raises hand",
        "environment_coordinates": "warm ahwa interior",
        "composition_layout": "centered rule-of-thirds framing",
        "camera_specifications": "wide 16:9 lens",
        "text_overlay_arabic": "NONE",
        "accent_color_hook": "#E09F3E",
        "style_anchor": VALID_STYLE,
    }
    base.update(overrides)
    return base


def make_item(index, timestamp, *, frame_index=1, **overrides):
    item = {
        "index": index,
        "timestamp": timestamp,
        "sequence_type": "STANDALONE",
        "layout_classification": "",
        "sequence_metadata": {"frame_index": frame_index},
        "visual_density": "",
        "visual_prompt": make_visual_prompt(),
    }
    item.update(overrides)
    return item


def make_fixture(count=15):
    seconds = [(i + 2) * 3 for i in range(count)]
    return [
        make_item(i + 1, f"[{s // 60:02d}:{s % 60:02d}]", frame_index=1)
        for i, s in enumerate(seconds)
    ]


class TestRelocationSmoke:
    def test_aliases_point_at_validator_functions(self):
        assert (
            flow_image_generator.flatten_visual_prompt_to_diffusion_text
            is validator.flatten_visual_prompt_to_diffusion_text
        )
        assert flow_image_generator.enforce_arabic_in_prompt is validator.enforce_arabic_in_prompt

    def test_flatten_output_structure_preserved(self):
        text = validator.flatten_visual_prompt_to_diffusion_text(make_visual_prompt())
        assert text.startswith("cartoon host in amber studio, raises hand.")
        assert "Art Style:" in text

    def test_enforce_appends_typography_directive(self):
        out = validator.enforce_arabic_in_prompt("CHALLENGER 1 enters the stage")
        assert "Typography Directive" in out
        assert "التحدي 1" in out


class TestModels:
    def test_frame_item_valid_full(self):
        item = FrameItem.model_validate(make_item(1, "[00:05]"))
        assert item.index == 1
        assert item.timestamp == "[00:05]"
        assert item.sequence_metadata.frame_index == 1
        assert item.visual_prompt.subject_details == "cartoon host in amber studio"

    def test_frame_item_minimal(self):
        minimal = FrameItem.model_validate(
            {
                "index": 1,
                "timestamp": "[00:05]",
                "visual_prompt": {"subject_details": "host", "style_anchor": VALID_STYLE},
            }
        )
        assert minimal.sequence_type == "STANDALONE"
        assert minimal.visual_prompt.text_overlay_arabic == "NONE"
        assert minimal.layout_classification == ""

    def test_extra_keys_ignored(self):
        payload = make_item(1, "[00:05]")
        payload["unknown_top_level"] = "x"
        payload["visual_prompt"]["unknown_vp_key"] = 42
        parsed = FrameItem.model_validate(payload)
        assert parsed.index == 1

    def test_bad_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            FrameItem.model_validate(make_item(1, "12:30"))
        with pytest.raises(ValidationError):
            FrameItem.model_validate(make_item(1, "[100:00]"))

    def test_hhmmss_timestamp_accepted(self):
        item = FrameItem.model_validate(make_item(1, "[01:02:03]"))
        assert item.timestamp == "[01:02:03]"

    def test_sequence_metadata_rejects_zero_frame(self):
        with pytest.raises(ValidationError):
            FrameItem.model_validate(make_item(1, "[00:05]", frame_index=0))


class TestParseTimestampSeconds:
    def test_mmss(self):
        assert parse_timestamp_seconds("[02:03]") == 123

    def test_hhmmss(self):
        assert parse_timestamp_seconds("[01:02:03]") == 3723

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_timestamp_seconds("02:03")


class TestIntegrityEngine:
    def test_equal_timestamps_frame_ascending_ok(self):
        items = [
            make_item(1, "[00:07]", frame_index=1),
            make_item(2, "[00:07]", frame_index=2),
        ]
        result = verify_pipeline_integrity(items, expected_total=2)
        assert len(result) == 2

    def test_equal_timestamps_frame_regression_violation(self):
        items = [
            make_item(1, "[00:07]", frame_index=2),
            make_item(2, "[00:07]", frame_index=1),
        ]
        with pytest.raises(PipelineIntegrityError) as excinfo:
            verify_pipeline_integrity(items, expected_total=2)
        joined = " ".join(excinfo.value.violations)
        assert "strictly increase" in joined

    def test_duplicate_index_named(self):
        items = [make_item(1, "[00:05]"), make_item(1, "[00:09]")]
        with pytest.raises(PipelineIntegrityError) as excinfo:
            verify_pipeline_integrity(items, expected_total=2)
        joined = " ".join(excinfo.value.violations)
        assert "Duplicate indices" in joined
        assert "1" in joined

    def test_missing_index_named(self):
        items = [make_item(i, f"[{i // 60:02d}:{i % 60:02d}]") for i in range(1, 101)]
        del items[4]
        with pytest.raises(PipelineIntegrityError) as excinfo:
            verify_pipeline_integrity(items, expected_total=100)
        joined = " ".join(excinfo.value.violations)
        assert "Missing indices" in joined
        assert "5" in joined

    def test_count_mismatch_reported(self):
        items = make_fixture(15)
        with pytest.raises(PipelineIntegrityError) as excinfo:
            verify_pipeline_integrity(items[:14], expected_total=15)
        assert any("Count mismatch" in v for v in excinfo.value.violations)

    def test_subtitle_phrase_autocleaned_then_passes(self):
        dirty = make_item(1, "[00:05]")
        dirty["visual_prompt"]["subject_details"] = "host explains calmly for subtitles"
        result = verify_pipeline_integrity([dirty], expected_total=1)
        assert "for subtitles" not in str(result)

        with pytest.raises(PipelineIntegrityError) as excinfo:
            verify_pipeline_integrity([dirty], expected_total=1, auto_repair=False)
        assert any("subtitle" in v for v in excinfo.value.violations)

    def test_margin_term_detected(self):
        item = make_item(1, "[00:05]")
        item["visual_prompt"]["composition_layout"] = "keep a clear left margin band"
        with pytest.raises(PipelineIntegrityError) as excinfo:
            verify_pipeline_integrity([item], expected_total=1)
        assert any("margin" in v for v in excinfo.value.violations)

    def test_latin_overlay_autoset_none(self):
        item = make_item(1, "[00:05]")
        item["visual_prompt"]["text_overlay_arabic"] = "Opening Title"
        result = verify_pipeline_integrity([item], expected_total=1)
        assert result[0]["visual_prompt"]["text_overlay_arabic"] == "NONE"

        with pytest.raises(PipelineIntegrityError) as excinfo:
            verify_pipeline_integrity([item], expected_total=1, auto_repair=False)
        assert any("Latin" in v for v in excinfo.value.violations)

    def test_arabic_overlay_passes_unchanged(self):
        overlay = "التحدي الأول"
        item = make_item(1, "[00:05]")
        item["visual_prompt"]["text_overlay_arabic"] = overlay
        result = verify_pipeline_integrity([item], expected_total=1)
        assert result[0]["visual_prompt"]["text_overlay_arabic"] == overlay

    def test_style_anchor_missing_3px(self):
        item = make_item(1, "[00:05]")
        item["visual_prompt"]["style_anchor"] = VALID_STYLE.replace("3px ", "")
        with pytest.raises(PipelineIntegrityError) as excinfo:
            verify_pipeline_integrity([item], expected_total=1)
        assert any("3px" in v for v in excinfo.value.violations)

    def test_style_anchor_missing_vector_and_cel_shading(self):
        item = make_item(1, "[00:05]")
        item["visual_prompt"]["style_anchor"] = "crisp 3px outlines only"
        with pytest.raises(PipelineIntegrityError) as excinfo:
            verify_pipeline_integrity([item], expected_total=1)
        joined = " ".join(excinfo.value.violations)
        assert "vector" in joined
        assert "cel-shading" in joined

    def test_schema_violation_missing_subject(self):
        item = make_item(1, "[00:05]")
        item["visual_prompt"]["subject_details"] = ""
        with pytest.raises(PipelineIntegrityError) as excinfo:
            verify_pipeline_integrity([item], expected_total=1)
        joined = " ".join(excinfo.value.violations)
        assert "schema violation" in joined
        assert "subject_details" in joined

    def test_happy_path_full_fixture(self):
        fixture = make_fixture(15)
        result = verify_pipeline_integrity(fixture, expected_total=15)
        assert len(result) == 15
        assert [entry["index"] for entry in result] == list(range(1, 16))
        assert all(entry["visual_prompt"]["style_anchor"] for entry in result)

    def test_original_payload_not_mutated_by_autorepair(self):
        dirty = make_item(1, "[00:05]")
        dirty["visual_prompt"]["subject_details"] = "host explains for subtitles"
        dirty["visual_prompt"]["text_overlay_arabic"] = "Title Card"
        verify_pipeline_integrity([dirty], expected_total=1)
        assert "for subtitles" in dirty["visual_prompt"]["subject_details"]
        assert dirty["visual_prompt"]["text_overlay_arabic"] == "Title Card"

    def test_error_carries_all_violation_strings(self):
        bad = make_item(1, "[00:05]")
        bad["visual_prompt"]["style_anchor"] = "flat colors"
        bad["visual_prompt"]["composition_layout"] = "bottom margin reserved"
        extra = make_item(1, "[00:09]")
        payload = [bad, extra]
        with pytest.raises(PipelineIntegrityError) as excinfo:
            verify_pipeline_integrity(payload, expected_total=4)
        violations = excinfo.value.violations
        joined = " ".join(violations)
        assert len(violations) >= 5
        assert any("Count mismatch" in v for v in violations)
        assert any("Missing indices" in v for v in violations)
        assert any("Duplicate indices" in v for v in violations)
        assert "3px" in joined
        assert "margin" in joined
        assert str(excinfo.value)


class TestEnglishOnlyGateAndNegativeInjection:
    def test_english_only_gate_passes_clean_english(self):
        from validator import validate_english_only_prompt

        valid, error = validate_english_only_prompt("A host character gesturing enthusiastically at desk")
        assert valid is True
        assert error == ""

    def test_english_only_gate_rejects_arabic_script(self):
        from validator import validate_english_only_prompt

        valid, error = validate_english_only_prompt("Host explaining النظرية النسبية on board")
        assert valid is False
        assert "Arabic script detected" in error

    def test_transliterate_arabic_fallback(self):
        from validator import transliterate_arabic_fallback

        text = "Host holding الكتاب at desk"
        transliterated = transliterate_arabic_fallback(text)
        assert "الكتاب" not in transliterated
        assert "al-kitab" in transliterated.lower() or "ktab" in transliterated.lower() or "kitab" in transliterated.lower()

    def test_flatten_deterministic_negative_injection(self):
        from validator import flatten_visual_prompt_to_diffusion_text

        vp = {
            "subject_details": "Host",
            "subject_action_increment": "points at screen",
            "environment_coordinates": "Studio",
            "composition_layout": "centered",
            "accent_color_hook": "Warm Amber",
            "style_anchor": "2D graphic vector animation explainer style, crisp 3px black vector outlines, flat 2-step cel-shading",
            "text_overlay_arabic": "NONE",
            "mood": "inquisitive",
            "lighting": "studio spotlight",
            "continuity_id": "HOST_01",
        }
        flattened = flatten_visual_prompt_to_diffusion_text(vp)
        assert "no text" in flattened.lower()
        assert "no subtitles" in flattened.lower()
        assert "no letters" in flattened.lower()
        assert "no watermark" in flattened.lower()


class TestVisualPrompt8PartSchema:
    def test_8part_visual_prompt_with_continuity_id(self):
        from validator import VisualPrompt

        vp = VisualPrompt(
            subject_details="Abo Hmeed",
            subject_action_increment="examines chart",
            environment_coordinates="ARCHIVAL_DOSSIER",
            composition_layout="rule of thirds",
            camera_specifications="zoom_in",
            text_overlay_arabic="NONE",
            accent_color_hook="Sepia",
            style_anchor="2D graphic vector animation explainer style, crisp 3px black vector outlines, flat 2-step cel-shading",
            mood="puzzled",
            lighting="side keylight",
            continuity_id="ABO_HMEED_01",
        )
        assert vp.continuity_id == "ABO_HMEED_01"
        assert vp.mood == "puzzled"
        assert vp.lighting == "side keylight"

    def test_pure_8part_diffusion_schema_validation_and_flattening(self):
        from validator import (
            FrameItem,
            flatten_visual_prompt_to_diffusion_text,
            verify_pipeline_integrity,
        )

        item = {
            "index": 1,
            "timestamp": "[00:05]",
            "visual_prompt": {
                "subject": "Ahmed El-Ghandour in signature yellow hoodie",
                "action": "points quizzically at chalkboard",
                "setting": "classic Ahwa studio background",
                "mood": "educational humor",
                "lighting": "warm studio illumination",
                "composition": "medium close-up 16:9 framing",
                "style": "2D vector animation style",
                "negative_prompt": "no photorealism, no 3D render",
                "continuity_id": "HOST_01",
            },
        }

        # Verify FrameItem validates cleanly without legacy fields
        frame = FrameItem.model_validate(item)
        assert frame.visual_prompt.subject == "Ahmed El-Ghandour in signature yellow hoodie"
        assert frame.visual_prompt.continuity_id == "HOST_01"

        # Verify pipeline integrity passes without requiring style_anchor
        verified = verify_pipeline_integrity([item], expected_total=1)
        assert len(verified) == 1

        # Verify flattening synthesizes elevated diffusion prompt with preset fallback & negative prompt
        flattened = flatten_visual_prompt_to_diffusion_text(item["visual_prompt"])
        assert "Ahmed El-Ghandour in signature yellow hoodie, points quizzically at chalkboard" in flattened
        assert "Scene Setting: classic Ahwa studio background" in flattened
        assert "Composition: medium close-up 16:9 framing" in flattened
        assert "Mood: educational humor" in flattened
        assert "Negative Prompt: no photorealism, no 3D render, no text, no subtitles" in flattened

    def test_negative_prompt_with_subtitles_and_margins_allowed(self):
        from validator import verify_pipeline_integrity

        item = {
            "index": 1,
            "timestamp": "[00:05]",
            "visual_prompt": {
                "subject": "A 2D graphic vector illustration of a scientist",
                "action": "holding a beaker",
                "setting": "clean white laboratory",
                "mood": "serious",
                "lighting": "bright studio light",
                "composition": "centered 16:9 shot",
                "style": "2D vector animation explainer style, crisp 3px black vector outlines, flat 2-step cel-shading",
                "negative_prompt": "subtitles, margin, watermark, text overlay",
            },
        }
        verified = verify_pipeline_integrity([item], expected_total=1)
        assert len(verified) == 1


def test_strict_negative_prompt_free_of_style_dna():
    """Enforce invariant: STRICT_NEGATIVE_PROMPT must never contain style DNA keywords,
    and must enforce optical camera distortion prohibitions (Task 1.3)."""
    from youtube_automation.prompts.validator import STRICT_NEGATIVE_PROMPT

    prohibited = ["3px", "vector", "cel-shading"]
    for word in prohibited:
        assert word not in STRICT_NEGATIVE_PROMPT.lower(), f"Prohibited positive token '{word}' in STRICT_NEGATIVE_PROMPT"

    # Task 1.3 Camera Model Migration Negative Assertions
    required_negative_camera_bans = ["no 24mm lens", "no barrel distortion", "no keystone distortion"]
    for ban in required_negative_camera_bans:
        assert ban in STRICT_NEGATIVE_PROMPT.lower(), f"Required camera ban '{ban}' missing from STRICT_NEGATIVE_PROMPT"


def test_bleed_padding_and_margin_pass_integrity():
    from youtube_automation.prompts.validator import verify_pipeline_integrity
    item = {
        "index": 1,
        "timestamp": "[00:05]",
        "visual_prompt": {
            "subject_details": "scientific apparatus",
            "setting_environment": "clean white laboratory",
            "lighting_setup": "bright studio light",
            "composition_layout": "16:9 widescreen with 10% bleed padding and 10% bleed margin",
            "style_anchor": "2D vector animation explainer style, crisp 3px black vector outlines, flat 2-step cel-shading",
            "negative_prompt": "subtitles, watermark, text overlay",
        },
    }
    verified = verify_pipeline_integrity([item], expected_total=1)
    assert len(verified) == 1


