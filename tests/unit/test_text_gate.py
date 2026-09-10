"""Unit tests for Multi-Layer Text Collision Gate (Ticket 5 / #18 / ADR 0004)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

import text_gate


@pytest.fixture
def sample_image(tmp_path: Path) -> str:
    """Creates a 1000x1000 dummy PNG image."""
    img_path = str(tmp_path / "test_frame.png")
    img = Image.new("RGB", (1000, 1000), color=(255, 255, 255))
    img.save(img_path)
    return img_path


class TestOCRThresholds:
    def test_confidence_boundary_59_passes_60_rejected(self, monkeypatch, sample_image):
        # 1000x1000 image = 1,000,000 px. Bbox 100x100 = 10,000 px (1% area).
        def mock_image_to_data(image, output_type=None):
            return {
                "text": ["", "Subtitles"],
                "conf": ["-1", "59"],
                "left": [0, 100],
                "top": [0, 800],
                "width": [0, 100],
                "height": [0, 100],
            }

        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", mock_image_to_data)

        has_text, boxes = text_gate.check_text_collision(sample_image)
        assert not has_text, "Confidence 59 should pass (below threshold 60)"
        assert len(boxes) == 0

        def mock_image_to_data_60(image, output_type=None):
            return {
                "text": ["", "Subtitles"],
                "conf": ["-1", "60"],
                "left": [0, 100],
                "top": [0, 800],
                "width": [0, 100],
                "height": [0, 100],
            }

        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", mock_image_to_data_60)
        has_text_60, boxes_60 = text_gate.check_text_collision(sample_image)
        assert has_text_60, "Confidence 60 should be rejected (>= threshold 60)"
        assert len(boxes_60) == 1
        assert boxes_60[0]["text"] == "Subtitles"
        assert boxes_60[0]["confidence"] == 60.0
        assert boxes_60[0]["area_ratio"] == 0.01

    def test_min_text_len_boundary(self, monkeypatch, sample_image):
        def mock_image_to_data_single_char(image, output_type=None):
            return {
                "text": ["", "A"],
                "conf": ["-1", "90"],
                "left": [0, 100],
                "top": [0, 800],
                "width": [0, 200],
                "height": [0, 100],
            }

        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", mock_image_to_data_single_char)
        has_text, boxes = text_gate.check_text_collision(sample_image)
        assert not has_text, "1 character (len < 2) should pass"

        def mock_image_to_data_two_chars(image, output_type=None):
            return {
                "text": ["", "AB"],
                "conf": ["-1", "90"],
                "left": [0, 100],
                "top": [0, 800],
                "width": [0, 200],
                "height": [0, 100],
            }

        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", mock_image_to_data_two_chars)
        has_text_2, boxes_2 = text_gate.check_text_collision(sample_image)
        assert has_text_2, "2 characters (len >= 2) should be rejected"
        assert len(boxes_2) == 1

    def test_min_bbox_area_boundary(self, monkeypatch, sample_image):
        # 1000x1000 image. 1% is 10,000 px. 90x100 = 9,000 px (0.9% -> below 1%)
        def mock_image_to_data_small_box(image, output_type=None):
            return {
                "text": ["", "TinyText"],
                "conf": ["-1", "95"],
                "left": [0, 100],
                "top": [0, 800],
                "width": [0, 90],
                "height": [0, 100],
            }

        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", mock_image_to_data_small_box)
        has_text, boxes = text_gate.check_text_collision(sample_image)
        assert not has_text, "Bbox area < 1% should pass"

        # 100x100 = 10,000 px (1.0% -> >= 1%)
        def mock_image_to_data_exact_box(image, output_type=None):
            return {
                "text": ["", "BigText"],
                "conf": ["-1", "95"],
                "left": [0, 100],
                "top": [0, 800],
                "width": [0, 100],
                "height": [0, 100],
            }

        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", mock_image_to_data_exact_box)
        has_text_exact, boxes_exact = text_gate.check_text_collision(sample_image)
        assert has_text_exact, "Bbox area >= 1% should be rejected"


class TestPytesseractAndFallback:
    def test_pytesseract_detection_when_available(self, monkeypatch, sample_image):
        mock_data = {
            "text": ["", "Title", "Text"],
            "conf": ["-1", "85", "90"],
            "left": [0, 100, 300],
            "top": [0, 500, 500],
            "width": [0, 150, 150],
            "height": [0, 100, 100],
        }
        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", lambda img, output_type=None: mock_data)

        has_text, boxes = text_gate.check_text_collision(sample_image)
        assert has_text is True
        assert len(boxes) == 2
        assert boxes[0]["text"] == "Title"
        assert boxes[1]["text"] == "Text"

    def test_pytesseract_failure_falls_back_to_mser(self, monkeypatch, sample_image):
        # Force pytesseract to fail/be unavailable
        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", MagicMock(side_effect=ImportError("no tesseract")))

        # Mock MSER fallback to return a detected box
        fake_mser_box = {
            "text": "[MSER_CANDIDATE]",
            "confidence": 75.0,
            "bbox": [100, 100, 200, 100],
            "area_ratio": 0.02,
        }
        monkeypatch.setattr(text_gate, "_detect_via_mser_fallback", lambda img_path, config=None: [fake_mser_box])

        has_text, boxes = text_gate.check_text_collision(sample_image)
        assert has_text is True
        assert len(boxes) == 1
        assert boxes[0]["text"] == "[MSER_CANDIDATE]"

    def test_clean_image_passes_all_gates(self, monkeypatch, sample_image):
        mock_empty_data = {
            "text": ["", "   "],
            "conf": ["-1", "20"],
            "left": [0, 0],
            "top": [0, 0],
            "width": [0, 10],
            "height": [0, 10],
        }
        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", lambda img, output_type=None: mock_empty_data)

        has_text, boxes = text_gate.check_text_collision(sample_image)
        assert has_text is False
        assert len(boxes) == 0


class TestDebugDumpAndStrengthenedPrompt:
    def test_dump_text_collision_debug_writes_expected_json(self, tmp_path):
        dump_path = str(tmp_path / "debug" / "malformed_chunk_3.json")
        boxes = [{"text": "Hello", "confidence": 80.0, "bbox": [10, 10, 50, 50], "area_ratio": 0.02}]
        saved_file = text_gate.dump_text_collision_debug(
            dump_path=dump_path,
            chunk_index=3,
            image_path="test.png",
            ocr_boxes=boxes,
            prompt_text="sample prompt",
        )
        assert Path(saved_file).exists()
        with open(saved_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["chunk_index"] == 3
        assert data["image_path"] == "test.png"
        assert data["status"] == "FAILED"
        assert data["ocr_boxes"] == boxes
        assert data["prompt_text"] == "sample prompt"

    def test_strengthened_negative_prompt_contains_critical_bans(self):
        neg = text_gate.STRENGTHENED_NEGATIVE_PROMPT.lower()
        assert "no text" in neg
        assert "no letters" in neg
        assert "no words" in neg
        assert "no subtitles" in neg

class TestSpatialAwareness:
    def test_explainer_deck_permits_upper_text(self, monkeypatch, sample_image):
        def mock_image_to_data(image, output_type=None):
            return {
                "text": ["", "Title"],
                "conf": ["-1", "95"],
                "left": [0, 100],
                "top": [0, 100],  # Top 10%
                "width": [0, 100],
                "height": [0, 100],
            }

        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", mock_image_to_data)
        has_text, boxes = text_gate.check_text_collision(sample_image, sequence_type="EXPLAINER_DECK")
        assert not has_text, "Explainer deck should permit text in upper 80%"
        assert len(boxes) == 1
        assert boxes[0].get("permitted") is True

    def test_explainer_deck_rejects_bottom_text(self, monkeypatch, sample_image):
        def mock_image_to_data(image, output_type=None):
            return {
                "text": ["", "Subtitle"],
                "conf": ["-1", "95"],
                "left": [0, 100],
                "top": [0, 900],  # Bottom 10%
                "width": [0, 100],
                "height": [0, 100],
            }

        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", mock_image_to_data)
        has_text, boxes = text_gate.check_text_collision(sample_image, sequence_type="EXPLAINER_DECK")
        assert has_text, "Explainer deck should reject text in bottom 20%"
        assert len(boxes) == 1
        assert boxes[0].get("permitted") is not True

    def test_standalone_rejects_all_text(self, monkeypatch, sample_image):
        def mock_image_to_data(image, output_type=None):
            return {
                "text": ["", "Title"],
                "conf": ["-1", "95"],
                "left": [0, 100],
                "top": [0, 100],  # Top 10%
                "width": [0, 100],
                "height": [0, 100],
            }

        monkeypatch.setattr(text_gate, "_run_pytesseract_dict", mock_image_to_data)
        has_text, boxes = text_gate.check_text_collision(sample_image, sequence_type="STANDALONE")
        assert has_text, "Standalone should reject text even in upper 80%"
