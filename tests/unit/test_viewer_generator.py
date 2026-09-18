"""Unit tests for the Studio Viewer Generator module."""

import hashlib
import json
import os
from pathlib import Path

from tools.viewer_generator import build_frame_records, generate_comparison_viewer_html


def test_build_frame_records_and_duplicate_detection(tmp_path: Path):
    # Setup test run directory
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    canary_dir = run_dir / "canary_images"
    canary_dir.mkdir()
    gen_dir = run_dir / "generated_images"
    gen_dir.mkdir()

    # Create dummy images for Frame 1 and Frame 2 with identical content (duplicate hash)
    dup_content = b"identical_fake_image_bytes"
    f1_name = "00_00.png"
    f2_name = "00_05.png"
    (canary_dir / f1_name).write_bytes(dup_content)
    (canary_dir / f2_name).write_bytes(dup_content)

    socratic_prompts = [
        {
            "index": 1,
            "timestamp": "[00:00]",
            "enhanced_prompt": "Prompt 1 with 1-2-3 shape hierarchy and Da Vinci Sfumato chiaroscuro",
            "layout_classification": "AHWA_STUDIO",
        },
        {
            "index": 2,
            "timestamp": "[00:05]",
            "enhanced_prompt": "Prompt 2 with 24mm lens",
            "layout_classification": "AHWA_STUDIO",
        },
    ]
    (run_dir / "flow_prompts_socratic.json").write_text(json.dumps(socratic_prompts), encoding="utf-8")

    records = build_frame_records(str(run_dir), str(canary_dir))
    assert len(records) == 2
    assert records[0]["canary_exists"] is True
    assert records[1]["canary_exists"] is True
    # Verify duplicate hash detection
    assert records[0]["duplicate_match"] == 2
    assert records[1]["duplicate_match"] == 1
    assert records[0]["duplicate_hash"] == hashlib.sha256(dup_content).hexdigest()[:12]

    # Generate HTML
    out_html = tmp_path / "studio_viewer.html"
    generated_path = generate_comparison_viewer_html(str(run_dir), str(canary_dir), output_html=str(out_html))
    assert os.path.exists(generated_path)
    html_text = Path(generated_path).read_text(encoding="utf-8")
    assert "Socratic Comparison Studio" in html_text
    assert "DUPLICATE" in html_text
    assert "copy-regen-btn" in html_text


def test_baseline_backup_resolution_and_relative_paths(tmp_path: Path):
    run_dir = tmp_path / "prod_run"
    run_dir.mkdir()
    baseline_dir = run_dir / "generated_images_baseline"
    baseline_dir.mkdir()
    socratic_master_dir = run_dir / "socratic_master_frames"
    socratic_master_dir.mkdir()
    chunk_dir = run_dir / "chunk_1_images"
    chunk_dir.mkdir()

    # Frame 1: Different in baseline and canary (Enhanced)
    (baseline_dir / "00_00.png").write_bytes(b"baseline_content_1")
    (chunk_dir / "00_00.png").write_bytes(b"socratic_enhanced_content_1")

    # Frame 2: Identical in baseline and canary (Restored baseline)
    identical_bytes = b"identical_content_for_audit"
    (baseline_dir / "00_05.png").write_bytes(identical_bytes)
    (chunk_dir / "00_05.png").write_bytes(identical_bytes)

    # Frame 3: Missing in chunk_dir, but present in socratic_master_dir (Fallback)
    (baseline_dir / "00_10.png").write_bytes(b"baseline_content_3")
    (socratic_master_dir / "00_10.png").write_bytes(b"socratic_content_3")

    socratic_prompts = [
        {"index": 1, "timestamp": "[00:00]", "enhanced_prompt": "Prompt 1"},
        {"index": 2, "timestamp": "[00:05]", "enhanced_prompt": "Prompt 2"},
        {"index": 3, "timestamp": "[00:10]", "enhanced_prompt": "Prompt 3"},
    ]
    (run_dir / "flow_prompts_socratic.json").write_text(json.dumps(socratic_prompts), encoding="utf-8")

    records = build_frame_records(str(run_dir), str(chunk_dir))
    assert len(records) == 3

    # Frame 1 assertions
    r1 = records[0]
    assert r1["baseline_exists"] is True
    assert r1["canary_exists"] is True
    assert r1["in_local_dir"] is True
    assert r1["is_enhanced"] is True
    assert r1["is_restored"] is False
    assert r1["baseline_image"] == "../generated_images_baseline/00_00.png"
    assert r1["canary_image"] == "00_00.png"

    # Frame 2 assertions (Restored baseline)
    r2 = records[1]
    assert r2["is_enhanced"] is False
    assert r2["is_restored"] is True
    assert r2["baseline_image"] == "../generated_images_baseline/00_05.png"
    assert r2["canary_image"] == "00_05.png"

    # Frame 3 assertions (Fallback to master frames)
    r3 = records[2]
    assert r3["baseline_exists"] is True
    assert r3["canary_exists"] is True
    assert r3["in_local_dir"] is False
    assert r3["canary_image"] == "../socratic_master_frames/00_10.png"

    # HTML generation check
    html_file = generate_comparison_viewer_html(str(run_dir), str(chunk_dir))
    assert os.path.exists(html_file)
    content = Path(html_file).read_text(encoding="utf-8")
    assert "Chunk 1: Frames 1–50" in content
    assert "Socratic Enhanced Only" in content
    assert "Restored Baseline Only" in content


def test_orthographic_feature_detection(tmp_path: Path):
    run_dir = tmp_path / "test_run_ortho"
    run_dir.mkdir()
    canary_dir = run_dir / "canary"
    canary_dir.mkdir()

    socratic_prompts = [
        {
            "index": 1,
            "timestamp": "[00:00]",
            "enhanced_prompt": "Clean 2D vector with orthographic flat 2D projection plane",
            "layout_classification": "STANDALONE",
        },
        {
            "index": 2,
            "timestamp": "[00:05]",
            "enhanced_prompt": "Legacy prompt with 24mm wide-angle lens",
            "layout_classification": "STANDALONE",
        },
    ]
    (run_dir / "flow_prompts_socratic.json").write_text(json.dumps(socratic_prompts), encoding="utf-8")

    records = build_frame_records(str(run_dir), str(canary_dir))
    assert len(records) == 2
    assert "Orthographic 2D" in records[0]["features"]
    assert "24mm Wide-Angle" in records[1]["features"]


