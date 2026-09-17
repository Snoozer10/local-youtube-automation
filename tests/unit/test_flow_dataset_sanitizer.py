"""Unit test suite for Dataset Sanitization and Collision Disambiguation Tool (Audit §2.3, §4.4, §6.2)."""

from __future__ import annotations

import json
import pytest
from src.youtube_automation.prompts.prompt_enhancer import expand_asset_tokens
from tools.sanitize_flow_dataset import (
    COLLISION_DISAMBIGUATION_MAP,
    OVERSAMPLING_2K_DIRECTIVE,
    sanitize_flow_item,
    sanitize_roadmap_item,
    sanitize_flow_dataset,
)


def test_sanitize_flow_item_disambiguation():
    """Verifies that all 7 collision frames decouple sequence metadata, update root and VP subjects."""
    for idx, expected in COLLISION_DISAMBIGUATION_MAP.items():
        raw_item = {
            "index": idx,
            "timestamp": f"[01:{idx:02d}]",
            "sequence_type": "PROGRESSIVE_BUILD_SET",
            "sequence_metadata": {"total_frames_in_set": 3, "frame_index": 2},
            "subject": "CHARACTER_HOST_MAIN",
            "continuity_id": "SUBJ_TH_01",
            "visual_prompt": {
                "subject": "old colliding subject",
                "subject_details": "old colliding subject",
                "action": "old colliding action",
                "subject_action_increment": "old colliding action",
                "continuity_id": "SUBJ_TH_01",
                "composition": "clean centered 16:9 widescreen framing, level eye-line",
            },
        }

        sanitized = sanitize_flow_item(raw_item)
        vp = sanitized["visual_prompt"]

        assert sanitized["sequence_type"] == "STANDALONE"
        assert sanitized["sequence_metadata"]["total_frames_in_set"] == 1
        assert sanitized["sequence_metadata"]["frame_index"] == 1
        assert sanitized["subject"] == expand_asset_tokens(expected["subject"])
        assert sanitized["continuity_id"] == f"SUBJ_DISAMBIG_{idx:02d}"
        assert vp["subject"] == expand_asset_tokens(expected["subject"])
        assert vp["action"] == expected["action"]
        assert vp["continuity_id"] == f"SUBJ_DISAMBIG_{idx:02d}"


def test_sanitize_camera_and_safe_zones():
    """Verifies 24mm purge, 16:9 safe zone injection even when clean centered... is absent, and 2K oversampling."""
    raw_item = {
        "index": 99,
        "visual_prompt": {
            "subject": "circuit board",
            "action": "pulsing data",
            "composition": "24mm wide-angle lens, centered schematic layout",
            "composition_layout": "wide angle perspective, edge to edge",
        },
    }

    sanitized = sanitize_flow_item(raw_item)
    vp = sanitized["visual_prompt"]

    for k in ("composition", "composition_layout"):
        assert "24mm wide-angle lens" not in vp[k]
        assert "orthographic flat 2D projection plane" in vp[k]
        assert "coordinates X: 180 to 1740, Y: 90 to 980" in vp[k]
        assert "10% peripheral bleed padding" in vp[k]
        assert OVERSAMPLING_2K_DIRECTIVE in vp[k]

    assert OVERSAMPLING_2K_DIRECTIVE in vp["camera_specifications"]


def test_sfumato_and_negative_hygiene():
    """Verifies complete abolition of Sfumato without dangling words, and parenthesis-safe negative prompt cleanup."""
    raw_item = {
        "index": 105,
        "visual_prompt": {
            "subject": "antique ledger",
            "lighting": "warm tungsten lighting with Da Vinci Sfumato chiaroscuro lighting on canvas",
            "negative_prompt": "no 3px, no vector, no cel-shading, custom watermark, no pure red RGB(255,0,0)",
        },
    }

    sanitized = sanitize_flow_item(raw_item)
    vp = sanitized["visual_prompt"]

    assert "Da Vinci Sfumato" not in vp["lighting"]
    assert "razor-sharp shadow falloff, zero gradients on canvas" in vp["lighting"]

    neg = vp["negative_prompt"]
    assert "no 3px" not in neg
    assert "no vector" not in neg
    assert "no cel-shading" not in neg
    assert "custom watermark" in neg
    assert "no 24mm lens" in neg


def test_idempotence_and_dataset_roundtrip(tmp_path):
    """Verifies sanitize(sanitize(x)) == sanitize(x) and atomic file replacement."""
    flow_file = tmp_path / "flow_prompts.json"
    roadmap_file = tmp_path / "roadmap.jsonl"

    flow_data = [
        {
            "index": 16,
            "visual_prompt": {
                "subject": "old subject",
                "action": "old action",
                "composition": "24mm wide-angle lens, clean centered 16:9 widescreen framing",
                "lighting": "Da Vinci Sfumato inspired tone separation",
                "negative_prompt": "no 3px, no vector",
            },
        }
    ]
    roadmap_data = [
        {
            "index": 16,
            "visual_concept": "Da Vinci Sfumato chiaroscuro lighting on 24mm wide-angle lens with circuit board",
        }
    ]

    with open(flow_file, "w", encoding="utf-8") as f:
        json.dump(flow_data, f)
    with open(roadmap_file, "w", encoding="utf-8") as f:
        for r in roadmap_data:
            f.write(json.dumps(r) + "\n")

    fc, rc = sanitize_flow_dataset(str(flow_file), str(roadmap_file))
    assert fc == 1
    assert rc == 1

    with open(flow_file, "r", encoding="utf-8") as f:
        pass1_flow = json.load(f)
    with open(roadmap_file, "r", encoding="utf-8") as f:
        pass1_road = [json.loads(l) for l in f]

    fc2, rc2 = sanitize_flow_dataset(str(flow_file), str(roadmap_file))
    assert fc2 == 1
    assert rc2 == 1

    with open(flow_file, "r", encoding="utf-8") as f:
        pass2_flow = json.load(f)
    with open(roadmap_file, "r", encoding="utf-8") as f:
        pass2_road = [json.loads(l) for l in f]

    assert pass1_flow == pass2_flow
    assert pass1_road == pass2_road
