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


def test_universal_ingestion_without_socratic_prompts(tmp_path: Path):
    """Verifies that runs with only flow_prompts.json (no socratic prompts) are ingested properly."""
    run_dir = tmp_path / "baseline_only_run"
    run_dir.mkdir()
    gen_dir = run_dir / "generated_images"
    gen_dir.mkdir()

    # Create dummy images
    (gen_dir / "00_00.png").write_bytes(b"dummy_image_1")
    (gen_dir / "00_05.png").write_bytes(b"dummy_image_2")

    # Structured dict prompts (like What Do Animals Think Of Humans)
    baseline_prompts = [
        {
            "index": 1,
            "timestamp": "[00:00]",
            "subject": "Golden retriever looking at human",
            "action": "tilting head curiously",
            "setting": "cozy living room",
            "style": "clean 2D animation style",
        },
        {
            "index": 2,
            "timestamp": "[00:05]",
            "subject": "Tabby cat perching on bookshelf",
            "action": "observing human activity",
            "setting": "warm study",
            "style": "clean 2D vector style",
        },
    ]
    (run_dir / "flow_prompts.json").write_text(json.dumps(baseline_prompts), encoding="utf-8")

    # Timeline spans
    timeline_data = {
        "spans": [
            {"index": 0, "start_time": 0.0, "end_time": 4.5, "duration": 4.5, "text": "Sentence 1", "camera_action": "linear_push"},
            {"index": 1, "start_time": 4.5, "end_time": 9.2, "duration": 4.7, "text": "Sentence 2", "punch_frame": 12},
        ]
    }
    (run_dir / "timeline.json").write_text(json.dumps(timeline_data), encoding="utf-8")

    records = build_frame_records(str(run_dir))
    # CRITICAL: Must NOT be empty!
    assert len(records) == 2
    assert records[0]["index"] == 1
    assert records[1]["index"] == 2
    assert "Subject: Golden retriever" in records[0]["baseline_prompt"]
    assert "Action: tilting head" in records[0]["baseline_prompt"]
    assert records[0]["baseline_exists"] is True
    assert records[0]["start_time"] == 0.0
    assert records[0]["duration"] == 4.5
    assert "🎥 Linear Push (103%)" in records[0]["features"]
    assert "⚡ Scale Punch (125% @ frame +12)" in records[1]["features"]


def test_two_pass_timestamp_span_alignment(tmp_path: Path):
    """Verifies that Two-Pass Timestamp-Validated Span Alignment protects against index mismatches."""
    run_dir = tmp_path / "alignment_run"
    run_dir.mkdir()
    gen_dir = run_dir / "generated_images"
    gen_dir.mkdir()

    (gen_dir / "00_12.png").write_bytes(b"image_content")

    # Non-contiguous prompt index 5 at timestamp 12.0s
    baseline_prompts = [
        {"index": 5, "timestamp": "[00:12]", "prompt": "Special scene after cut"}
    ]
    (run_dir / "flow_prompts.json").write_text(json.dumps(baseline_prompts), encoding="utf-8")

    # Timeline spans have contiguous spans 0, 1, 2, 3
    timeline_data = {
        "spans": [
            {"index": 0, "start_time": 0.0, "end_time": 4.0, "duration": 4.0},
            {"index": 1, "start_time": 4.0, "end_time": 8.0, "duration": 4.0},
            {"index": 2, "start_time": 8.0, "end_time": 11.5, "duration": 3.5},
            {"index": 3, "start_time": 11.5, "end_time": 16.0, "duration": 4.5, "punch_frame": 15},
        ]
    }
    (run_dir / "timeline.json").write_text(json.dumps(timeline_data), encoding="utf-8")

    records = build_frame_records(str(run_dir))
    # Index 5 has timestamp 12.0s, which falls in span 3 (11.5s to 16.0s)
    rec_5 = next(r for r in records if r["index"] == 5)
    assert rec_5["start_time"] == 11.5
    assert rec_5["duration"] == 4.5
    assert rec_5["punch_frame"] == 15


def test_media_assets_resolution(tmp_path: Path):
    """Verifies that resolve_media_assets locates master audio and video proxy."""
    from tools.viewer_generator import resolve_media_assets

    run_dir = tmp_path / "media_run"
    run_dir.mkdir()
    html_dir = run_dir / "canary_images"
    html_dir.mkdir()

    # Create dummy media files
    wav_file = run_dir / "full_episode_voice.wav"
    wav_file.write_bytes(b"RIFFdummywavbytes")
    mp4_file = run_dir / "youtube_ready_video_720p.mp4"
    mp4_file.write_bytes(b"ftypmp4dummybytes")

    media = resolve_media_assets(str(run_dir), str(html_dir))
    assert media["has_audio"] is True
    assert media["has_video"] is True
    assert media["audio_path"] == "../full_episode_voice.wav"
    assert media["video_path"] == "../youtube_ready_video_720p.mp4"


def test_resolution_mismatch_detection(tmp_path: Path):
    """Verifies that differing image resolutions trigger resolution mismatch warnings."""
    import struct
    import zlib

    def make_png(width: int, height: int) -> bytes:
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
        ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data))
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
        raw_data = b"\x00" * (height * (width + 1))
        comp_data = zlib.compress(raw_data)
        idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + comp_data))
        idat = struct.pack(">I", len(comp_data)) + b"IDAT" + comp_data + idat_crc
        iend_crc = struct.pack(">I", zlib.crc32(b"IEND"))
        iend = struct.pack(">I", 0) + b"IEND" + iend_crc
        return sig + ihdr + idat + iend

    run_dir = tmp_path / "res_run"
    run_dir.mkdir()
    gen_dir = run_dir / "generated_images"
    gen_dir.mkdir()
    canary_dir = run_dir / "canary_images"
    canary_dir.mkdir()

    # Baseline: 1920x1080 (16:9)
    (gen_dir / "00_00.png").write_bytes(make_png(1920, 1080))
    # Canary: 1792x1024 (7:4 != 16:9)
    (canary_dir / "00_00.png").write_bytes(make_png(1792, 1024))

    (run_dir / "flow_prompts_socratic.json").write_text(
        json.dumps([{"index": 1, "timestamp": "[00:00]", "enhanced_prompt": "Canary"}]), encoding="utf-8"
    )

    records = build_frame_records(str(run_dir), str(canary_dir))
    assert len(records) == 1
    assert records[0]["resolution_mismatch"] is not None
    assert "1920x1080 vs 1792x1024" in records[0]["resolution_mismatch"]


def test_dynamic_scaffolding_in_generated_html(tmp_path: Path):
    """Verifies that generated HTML includes the payload script, media elements, wipe viewport, and zero hardcoded '293'."""
    run_dir = tmp_path / "dynamic_scaffold_run"
    run_dir.mkdir()
    gen_dir = run_dir / "generated_images"
    gen_dir.mkdir()

    # Create dummy audio and video
    (run_dir / "full_episode_voice.wav").write_bytes(b"RIFF dummy wav")
    (run_dir / "youtube_ready_video_720p.mp4").write_bytes(b"dummy mp4")

    # Create 3 frames
    prompts = [
        {"index": i, "timestamp": f"[00:{i*5:02d}]", "enhanced_prompt": f"Frame {i} prompt"}
        for i in range(1, 4)
    ]
    (run_dir / "flow_prompts_socratic.json").write_text(json.dumps(prompts), encoding="utf-8")

    for i in range(1, 4):
        (gen_dir / f"00_{i*5:02d}.png").write_bytes(b"fake image")

    out_file = run_dir / "studio_viewer.html"
    generate_comparison_viewer_html(str(run_dir), output_html=str(out_file))

    assert out_file.exists()
    html_text = out_file.read_text(encoding="utf-8")

    # 1. Payload Script & JSON
    assert '<script id="studio-data" type="application/json">' in html_text
    assert '"media":' in html_text
    assert '"frames":' in html_text

    # 2. Single-source audio invariant
    assert 'videoProxy.muted = true' in html_text
    assert '<video id="video-proxy" preload="metadata" muted' in html_text
    assert '<audio id="master-audio"' in html_text

    # 3. Split Curtain Wipe & Diff Viewports
    assert 'id="wipe-viewport"' in html_text
    assert 'id="wipe-handle"' in html_text
    assert 'id="diff-viewport"' in html_text

    # 4. Safe Zones
    assert 'id="safe-zones-overlay"' in html_text or 'safe-zones-svg' in html_text
    assert 'ACTION SAFE (90%)' in html_text
    assert 'TITLE SAFE (80%)' in html_text

    # 5. Range Compressor & Scrubbing
    assert 'compressRanges' in html_text
    assert 'id="scrubber-track"' in html_text

    # 6. ZERO hardcoded "293" in select options
    assert 'Show All Frames (293)' not in html_text
    assert 'Frames 251–293' not in html_text


def test_relative_path_disk_audit(tmp_path: Path):
    """Verifies that nested chunk viewer HTML correctly resolves parent baseline and master frames."""
    run_dir = tmp_path / "chunk_audit_run"
    run_dir.mkdir()
    baseline_dir = run_dir / "generated_images_baseline"
    baseline_dir.mkdir()
    chunk_dir = run_dir / "chunk_1_images"
    chunk_dir.mkdir()

    (baseline_dir / "00_00.png").write_bytes(b"baseline_0")
    (chunk_dir / "00_00.png").write_bytes(b"chunk_0")

    (run_dir / "flow_prompts.json").write_text(
        json.dumps([{"index": 1, "timestamp": "[00:00]", "prompt": "Baseline prompt"}]), encoding="utf-8"
    )

    records = build_frame_records(str(run_dir), str(chunk_dir), html_dir=str(chunk_dir))
    assert len(records) == 1
    assert records[0]["baseline_image"] == "../generated_images_baseline/00_00.png"
    assert records[0]["canary_image"] == "00_00.png"

    # Generate HTML inside chunk directory
    chunk_html = chunk_dir / "studio_viewer.html"
    generate_comparison_viewer_html(str(run_dir), str(chunk_dir), output_html=str(chunk_html))

    assert chunk_html.exists()
    content = chunk_html.read_text(encoding="utf-8")
    assert '../generated_images_baseline/00_00.png' in content




