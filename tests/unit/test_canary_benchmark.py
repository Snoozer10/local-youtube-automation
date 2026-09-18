"""Unit tests for tools/run_canary_benchmark.py.

Validates:
1. Target canary frame selection (Frames 1, 15, 60, 150, 264).
2. Comparison row generation and metric aggregation.
3. Markdown report formatting.
"""


from tools.run_canary_benchmark import (
    build_canary_comparison_row,
    format_comparison_markdown_table,
    is_fatal_flow_quota_error,
    select_canary_frames,
)


def test_is_fatal_flow_quota_error():
    assert is_fatal_flow_quota_error("لقد بلغت الحدّ الأقصى للاستخدام. يُرجى إعادة المحاولة لاحقًا.") is True
    assert is_fatal_flow_quota_error("You have reached your usage limit. You have not been charged.") is True
    assert is_fatal_flow_quota_error("Rate limit exceeded") is True
    assert is_fatal_flow_quota_error("Quota exceeded for this project") is True
    assert is_fatal_flow_quota_error("Element not found") is False
    assert is_fatal_flow_quota_error("") is False
    assert is_fatal_flow_quota_error(None) is False



def test_select_canary_frames():
    mock_frames = [{"index": i, "timestamp": f"[{i:02d}:00]"} for i in range(1, 300)]
    selected = select_canary_frames(mock_frames, target_indices=[1, 15, 60, 150, 264])
    assert len(selected) == 5
    assert [f["index"] for f in selected] == [1, 15, 60, 150, 264]


def test_select_canary_frames_missing_index():
    mock_frames = [{"index": 1}, {"index": 15}]
    selected = select_canary_frames(mock_frames, target_indices=[1, 15, 999])
    assert len(selected) == 2
    assert [f["index"] for f in selected] == [1, 15]


def test_build_canary_comparison_row():
    row = build_canary_comparison_row(
        frame_idx=1,
        timestamp="[00:00]",
        archetype="Scientific Rigor",
        baseline_text="Host in studio",
        socratic_text="Host in studio with 1-2-3 shape hierarchy and Sfumato",
        has_text_collision=False,
        ocr_text_found="",
        upper_80_clear=True,
    )
    assert row["frame_index"] == 1
    assert row["archetype"] == "Scientific Rigor"
    assert row["upper_80_clear"] is True
    assert row["has_text_collision"] is False


def test_format_comparison_markdown_table():
    rows = [
        {
            "frame_index": 1,
            "timestamp": "[00:00]",
            "archetype": "Host Hook",
            "has_text_collision": False,
            "upper_80_clear": True,
            "ocr_text_found": "NONE",
            "socratic_features": "1-2-3 shape hierarchy, Sfumato chiaroscuro, 24mm optics",
        },
        {
            "frame_index": 15,
            "timestamp": "[00:45]",
            "archetype": "Debunk Dissection",
            "has_text_collision": False,
            "upper_80_clear": True,
            "ocr_text_found": "NONE",
            "socratic_features": "Bifurcated stage, 1-2-3 shape hierarchy",
        },
    ]
    md = format_comparison_markdown_table(rows)
    assert "| Frame |" in md
    assert "Host Hook" in md
    assert "Debunk Dissection" in md
    assert "PASS" in md


def test_parse_frame_spec():
    from tools.run_canary_benchmark import parse_frame_spec

    # 'all' expands to full range
    assert parse_frame_spec("all", total_count=10) == list(range(1, 11))
    assert parse_frame_spec("", total_count=5) == [1, 2, 3, 4, 5]

    # Ranges
    assert parse_frame_spec("1-5", total_count=10) == [1, 2, 3, 4, 5]
    assert parse_frame_spec("1-3, 7-9", total_count=10) == [1, 2, 3, 7, 8, 9]

    # Mixed ranges and singletons
    assert parse_frame_spec("1, 5, 8-10", total_count=10) == [1, 5, 8, 9, 10]

    # Out of bounds and deduplication
    assert parse_frame_spec("0-3, 3, 999", total_count=5) == [1, 2, 3]


def test_viewer_generator_basic(tmp_path):
    import json

    from tools.viewer_generator import generate_comparison_viewer_html

    run_dir = str(tmp_path)
    socratic_file = tmp_path / "flow_prompts_socratic.json"
    baseline_file = tmp_path / "flow_prompts.json"
    canary_dir = tmp_path / "canary_images"
    canary_dir.mkdir()

    mock_prompts = [{"index": 1, "timestamp": "[00:00]", "visual_prompt": "Test prompt"}]
    with open(socratic_file, "w", encoding="utf-8") as f:
        json.dump(mock_prompts, f)
    with open(baseline_file, "w", encoding="utf-8") as f:
        json.dump(mock_prompts, f)

    out_html = generate_comparison_viewer_html(run_dir, str(canary_dir))
    assert out_html.endswith("canary_comparison_viewer.html")
    with open(out_html, encoding="utf-8") as f:
        content = f.read()
    assert "Socratic Visual Prompt Comparison Studio" in content
    assert "const frames =" in content

