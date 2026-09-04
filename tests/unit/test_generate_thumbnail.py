"""Unit tests for generate_thumbnail.py (Feature 2 of Trajectory B).

Covers:
- Test 1: test_build_webcomic_thumbnail_prompt_includes_strict_negative_prompt
- Test 2: test_critique_json_parsing_and_fallback
- Test 3: test_text_collision_retry_and_purge
"""

import json
import os
from unittest.mock import MagicMock

import generate_thumbnail
from text_gate import STRENGTHENED_NEGATIVE_PROMPT
from validator import STRICT_NEGATIVE_PROMPT


def test_build_webcomic_thumbnail_prompt_includes_strict_negative_prompt():
    """Verifies that STRICT_NEGATIVE_PROMPT is present in the generated prompt and
    Arabic text is not instructed to be painted onto the raw bitmap.
    """
    concept = {
        "title_index": 1,
        "emotion": "shocked",
        "scene": "A man looking at a glowing laptop screen with astonishment",
        "text_overlay": "صدمة كبرى",
        "visual_recipe": {
            "lighting": "intense blue rim light",
            "color_palette": "dark charcoal and vibrant neon",
            "composition": "character on the right, laptop center",
        },
    }

    prompt = generate_thumbnail.build_webcomic_thumbnail_prompt(concept, index=1)

    # 1. STRICT_NEGATIVE_PROMPT must be deterministically included
    assert STRICT_NEGATIVE_PROMPT in prompt
    assert f"NEGATIVE PROMPT: [{STRICT_NEGATIVE_PROMPT}]" in prompt

    # 2. Raw Arabic text must NOT be instructed to be painted onto the image bitmap
    # (prevents garbled pseudo-Arabic diffusion rendering)
    assert 'Render the exact bold Arabic text "صدمة كبرى"' not in prompt
    # Negative space instruction should be present instead
    assert "negative space" in prompt.lower()
    assert "raw image bitmap" in prompt.lower() or "do not paint" in prompt.lower()


def test_critique_json_parsing_and_fallback():
    """Tests parsing ranking JSON and fallback handling on malformed or empty response."""
    concepts = [
        {"title_index": 1, "scene": "Scene 1"},
        {"title_index": 2, "scene": "Scene 2"},
        {"title_index": 3, "scene": "Scene 3"},
    ]

    # Case A: Valid JSON inside markdown code block
    valid_markdown_response = """
    Here is the ranking:
    ```json
    {
      "scores": [{"title_index": 1, "total_score": 35}, {"title_index": 3, "total_score": 38}],
      "winners": [3, 1],
      "improvements": {
        "3": "Make rim light warmer",
        "1": "Increase negative space on left"
      }
    }
    ```
    """
    critique = generate_thumbnail.parse_critique_json(valid_markdown_response, concepts, top_n=2)
    assert critique["winners"] == [3, 1]
    assert "3" in critique["improvements"]
    assert critique["improvements"]["3"] == "Make rim light warmer"

    # Case B: Plain valid JSON
    plain_json = json.dumps({
        "scores": [{"title_index": 2, "total_score": 40}],
        "winners": [2],
        "improvements": {"2": "Higher contrast"}
    })
    critique_b = generate_thumbnail.parse_critique_json(plain_json, concepts, top_n=1)
    assert critique_b["winners"] == [2]

    # Case C: Malformed JSON (should fall back gracefully to first top_n title indices)
    malformed_response = "I couldn't decide on winners, but try index 1."
    critique_c = generate_thumbnail.parse_critique_json(malformed_response, concepts, top_n=2)
    assert critique_c["winners"] == [1, 2]
    assert critique_c["improvements"] == {}

    # Case D: None / Empty response
    critique_d = generate_thumbnail.parse_critique_json(None, concepts, top_n=2)
    assert critique_d["winners"] == [1, 2]
    assert critique_d["improvements"] == {}


def test_text_collision_retry_and_purge(tmp_path, monkeypatch):
    """Mocks check_text_collision returning True and verifies retry logic and file purge."""
    output_dir = tmp_path / "thumbnails"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = "title_1_thumbnail.png"
    target_filepath = str(output_dir / filename)

    items = [
        {
            "title_index": 1,
            "filename": filename,
            "prompt": "Base webcomic prompt for title 1",
        }
    ]

    mock_page = MagicMock()
    prompts_sent = []

    def fake_send_image_prompt(page, prompt, timeout=300):
        prompts_sent.append(prompt)
        return "fake_response_success"

    def fake_save_image(page, response, filepath):
        # Create a dummy image file on disk
        with open(filepath, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nfake_image_bytes")
        return True

    monkeypatch.setattr(generate_thumbnail, "send_image_prompt_and_wait", fake_send_image_prompt)
    monkeypatch.setattr(generate_thumbnail, "_save_image_from_response", fake_save_image)

    # --- Scenario 1: Both attempt 1 and attempt 2 collide -> debug dumped, file purged ---
    fake_ocr_box = [{"text": "GARBLED", "confidence": 90.0, "bbox": [10, 10, 50, 20], "area_ratio": 0.05}]
    mock_check_collision = MagicMock(return_value=(True, fake_ocr_box))
    mock_dump_debug = MagicMock()

    monkeypatch.setattr(generate_thumbnail, "check_text_collision", mock_check_collision)
    monkeypatch.setattr(generate_thumbnail, "dump_text_collision_debug", mock_dump_debug)

    generated = generate_thumbnail.generate_images_via_gemini(mock_page, items, str(output_dir))

    # Should have attempted twice
    assert len(prompts_sent) == 2
    assert prompts_sent[0] == "Base webcomic prompt for title 1"
    assert STRENGTHENED_NEGATIVE_PROMPT in prompts_sent[1]

    # check_text_collision should have been called twice
    assert mock_check_collision.call_count == 2

    # dump_text_collision_debug must have been called on 2nd failure
    assert mock_dump_debug.call_count == 1
    debug_call_args = mock_dump_debug.call_args[1]
    assert debug_call_args["chunk_index"] == 1
    assert debug_call_args["image_path"] == target_filepath
    assert debug_call_args["ocr_boxes"] == fake_ocr_box
    assert STRENGTHENED_NEGATIVE_PROMPT in debug_call_args["prompt_text"]

    # The collided file MUST be purged from disk
    assert not os.path.exists(target_filepath)
    # The returned list must be empty (corrupt file not treated as valid)
    assert len(generated) == 0
    assert target_filepath not in generated

    # --- Scenario 2: Attempt 1 collides, Attempt 2 succeeds -> image retained ---
    prompts_sent.clear()
    collision_results = [(True, fake_ocr_box), (False, [])]

    def sequential_check_collision(filepath):
        return collision_results.pop(0)

    monkeypatch.setattr(generate_thumbnail, "check_text_collision", sequential_check_collision)
    mock_dump_debug.reset_mock()

    generated_retry_success = generate_thumbnail.generate_images_via_gemini(mock_page, items, str(output_dir))

    # Prompts sent: attempt 1, then attempt 2
    assert len(prompts_sent) == 2
    assert prompts_sent[0] == "Base webcomic prompt for title 1"
    assert STRENGTHENED_NEGATIVE_PROMPT in prompts_sent[1]

    # dump_text_collision_debug should NOT have been called because attempt 2 passed
    assert mock_dump_debug.call_count == 0

    # Image file exists on disk and is in generated list
    assert os.path.exists(target_filepath)
    assert generated_retry_success == [target_filepath]
