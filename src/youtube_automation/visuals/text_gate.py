"""Multi-Layer Text Collision Gate (Ticket 5 / #18 / ADR 0004).

Provides 3-layer text collision detection and prevention for Google Flow rendering:
1. Deterministic Negative Prompt injection (at prompt creation / retry)
2. Validator regex runtime check (pre-generation and post-generation)
3. Local OCR Gate (post-generation via pytesseract with MSER/edge fallback).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any

from PIL import Image

try:
    try:
        from utils import get_config_value
    except ImportError:
        from youtube_automation.core.utils import get_config_value
except Exception:

    def get_config_value(k: str, d: str = "") -> str:
        v = os.getenv(k)
        return v if v is not None else d


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# --- Constants & Thresholds ---
OCR_CONFIDENCE_THRESHOLD = 60.0
OCR_MIN_TEXT_LEN = 2
OCR_MIN_BBOX_AREA_RATIO = 0.01

STRENGTHENED_NEGATIVE_PROMPT = (
    "ABSOLUTELY NO TEXT, NO LETTERS, NO WORDS, NO SUBTITLES, NO WATERMARK, "
    "NO SIGNATURE, NO TYPOGRAPHY, NO CAPTIONS, NO LOWER THIRDS, NO HEADLINES, "
    "NO LABELS, NO ALPHABET, NO DIGITS, NO ON-SCREEN WRITING"
)


@dataclass
class OCRBox:
    text: str
    confidence: float
    bbox: list[int]  # [x, y, width, height]
    area_ratio: float


def get_ocr_confidence_threshold(config: dict | None = None) -> float:
    if config and "OCR_CONFIDENCE" in config:
        try:
            return float(config["OCR_CONFIDENCE"])
        except (ValueError, TypeError):
            pass
    raw = get_config_value("OCR_CONFIDENCE", "60")
    try:
        return float(raw)
    except (ValueError, TypeError):
        return OCR_CONFIDENCE_THRESHOLD


def get_ocr_min_text_len(config: dict | None = None) -> int:
    if config and "MIN_TEXT_LEN" in config:
        try:
            return int(config["MIN_TEXT_LEN"])
        except (ValueError, TypeError):
            pass
    raw = get_config_value("MIN_TEXT_LEN", "2")
    try:
        return int(raw)
    except (ValueError, TypeError):
        return OCR_MIN_TEXT_LEN


def get_ocr_min_bbox_area_ratio(config: dict | None = None) -> float:
    if config and "MIN_BBOX" in config:
        try:
            return float(config["MIN_BBOX"])
        except (ValueError, TypeError):
            pass
    raw = get_config_value("MIN_BBOX", "0.01")
    try:
        return float(raw)
    except (ValueError, TypeError):
        return OCR_MIN_BBOX_AREA_RATIO


def _run_pytesseract_dict(image: Any, output_type: Any = None) -> dict[str, Any]:
    """Helper wrapper around pytesseract.image_to_data for easy mocking in unit tests."""
    import pytesseract

    if output_type is None:
        output_type = pytesseract.Output.DICT
    return pytesseract.image_to_data(image, output_type=output_type)


def _detect_via_pytesseract(image_path: str, config: dict | None = None) -> list[OCRBox] | None:
    """Attempts OCR using local pytesseract. Returns None if pytesseract is unavailable."""
    try:
        with Image.open(image_path) as img:
            img_w, img_h = img.size
            if img_w <= 0 or img_h <= 0:
                return []
            data = _run_pytesseract_dict(img)
    except Exception:
        return None

    min_conf = get_ocr_confidence_threshold(config)
    min_len = get_ocr_min_text_len(config)
    min_ratio = get_ocr_min_bbox_area_ratio(config)
    total_area = float(img_w * img_h)

    boxes: list[OCRBox] = []
    texts = data.get("text", [])
    confs = data.get("conf", [])
    lefts = data.get("left", [])
    tops = data.get("top", [])
    widths = data.get("width", [])
    heights = data.get("height", [])

    for i in range(len(texts)):
        raw_text = str(texts[i]).strip()
        if len(raw_text) < min_len:
            continue
        try:
            conf = float(confs[i])
        except (ValueError, TypeError):
            continue
        if conf < min_conf:
            continue
        w = int(widths[i])
        h = int(heights[i])
        box_area = float(w * h)
        area_ratio = box_area / total_area
        if area_ratio < min_ratio:
            continue

        boxes.append(
            OCRBox(
                text=raw_text,
                confidence=conf,
                bbox=[int(lefts[i]), int(tops[i]), w, h],
                area_ratio=round(area_ratio, 4),
            )
        )

    return boxes


def _detect_via_mser_fallback(image_path: str, config: dict | None = None) -> list[OCRBox]:
    """Fallback text candidate detection using OpenCV MSER / high-contrast edge bounding boxes."""
    min_ratio = get_ocr_min_bbox_area_ratio(config)
    boxes: list[OCRBox] = []

    try:
        import cv2

        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return []
        img_h, img_w = img.shape
        total_area = float(img_w * img_h)

        # MSER region detection for text candidates
        mser = cv2.MSER_create()
        regions, bboxes = mser.detectRegions(img)

        for bbox in bboxes:
            x, y, w, h = bbox
            area_ratio = float(w * h) / total_area
            # Text lines typically have aspect ratio between 0.3 and 10.0 and minimum area
            aspect = float(w) / max(float(h), 1.0)
            if area_ratio >= min_ratio and 0.3 <= aspect <= 10.0:
                boxes.append(
                    OCRBox(
                        text="[MSER_CANDIDATE]",
                        confidence=70.0,
                        bbox=[int(x), int(y), int(w), int(h)],
                        area_ratio=round(area_ratio, 4),
                    )
                )
    except Exception:
        # If cv2 not installed or fails, return empty list
        pass

    return boxes


def check_text_collision(
    image_path: str, config: dict | None = None, sequence_type: str | None = None, is_explainer: bool = False
) -> tuple[bool, list[dict[str, Any]]]:
    """Checks an image on disk for burned-in text / subtitle collisions.

    Returns:
        (has_collision, ocr_boxes) where ocr_boxes is a list of dicts.
    """
    if not os.path.exists(image_path):
        return False, []

    gate_enabled = get_config_value("ENABLE_TEXT_GATE", "true").strip().lower() in ("true", "1", "yes")
    if config and "ENABLE_TEXT_GATE" in config:
        gate_enabled = bool(config["ENABLE_TEXT_GATE"])
    if not gate_enabled:
        return False, []

    # Layer 3: Local OCR with fallback
    boxes = _detect_via_pytesseract(image_path, config)
    if boxes is None:
        mser_enabled = True
        if config and "ENABLE_MSER_FALLBACK" in config:
            mser_enabled = bool(config["ENABLE_MSER_FALLBACK"])
        if mser_enabled:
            boxes = _detect_via_mser_fallback(image_path, config)
        else:
            boxes = []

    try:
        with Image.open(image_path) as img:
            _, img_h = img.size
    except Exception:
        img_h = 1080

    box_dicts = []
    has_collision = False

    explainer_types = {"EXPLAINER_DECK", "ARCHIVAL_DOSSIER", "METRIC"}
    treat_as_explainer = is_explainer or (sequence_type and sequence_type.upper() in explainer_types)

    for b in boxes:
        box_dict = asdict(b) if isinstance(b, OCRBox) else dict(b)
        bbox = box_dict["bbox"]
        top = bbox[1]
        bottom = bbox[1] + bbox[3]

        if treat_as_explainer and top <= 0.8 * img_h and bottom <= 0.8 * img_h:
            box_dict["permitted"] = True
        else:
            has_collision = True

        box_dicts.append(box_dict)

    return has_collision, box_dicts


def dump_text_collision_debug(
    dump_path: str,
    chunk_index: int,
    image_path: str,
    ocr_boxes: list[dict[str, Any]],
    prompt_text: str = "",
) -> str:
    """Writes a debug artifact for operator diagnosis on repeated text collision."""
    os.makedirs(os.path.dirname(os.path.abspath(dump_path)), exist_ok=True)
    payload = {
        "chunk_index": chunk_index,
        "image_path": image_path,
        "status": "FAILED",
        "error": "text_collision_detected",
        "ocr_boxes": ocr_boxes,
        "prompt_text": prompt_text,
    }
    with open(dump_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return dump_path
