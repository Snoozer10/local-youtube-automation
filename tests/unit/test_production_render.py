import pytest

from youtube_automation.production.render import camera_filter, overlay_ass
from youtube_automation.production.shots import SCHULTE_6X6, Overlay, Shot


def _copy_compiled_artifact(source, destination):
    import shutil

    from youtube_automation.video import verification_receipt_path, verify_compilation_receipt

    verify_compilation_receipt(source)
    shutil.copyfile(source, destination)
    receipt = verification_receipt_path(destination)
    receipt.parent.mkdir(exist_ok=True)
    shutil.copyfile(verification_receipt_path(source), receipt)
    verify_compilation_receipt(destination)


def _lineage_fixture(tmp_path, monkeypatch):
    import json
    from contextlib import nullcontext
    from types import SimpleNamespace

    from youtube_automation.production import cli, flow, render, review
    from youtube_automation.production.contracts import fingerprint
    from youtube_automation.production.shots import EditorialPolicy, ShotPlan

    shot = fixture_shot(end_frame=30, overlays=[
        Overlay(kind="label", start_frame=0, end_frame=30, text="Visible copy")
    ])
    plan = ShotPlan(
        shots=[shot], brief_sha256="a" * 64, timeline_sha256="b" * 64,
        fps=30, total_frames=30,
        editorial_policy=EditorialPolicy(
            cadence="balanced", target_shot_seconds=5, max_shot_seconds=10,
            max_consecutive_framing=3, max_motion_fraction=0.5,
        ),
    )
    brief = SimpleNamespace(version=2, source_sha256="c" * 64)
    timeline = {"audio_file": "audio.wav"}
    (tmp_path / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    (tmp_path / "shot_plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"canonical audio")
    artifact = tmp_path / "preview.mp4"
    artifact.write_bytes(b"verified preview")
    assets = {"asset": "d" * 64}
    config = {"OUTPUT_WIDTH": 640, "OUTPUT_HEIGHT": 360, "CPU_CRF": 17}
    # The fake compiler must publish the same durable evidence as the live seam.
    from PIL import Image

    from youtube_automation.video.engine import compile_video
    from youtube_automation.video.runner import FakeMediaRunner
    from youtube_automation.video.schema import (
        CompilationRequest,
        CompilationSpan,
        CompilationTarget,
    )

    image = tmp_path / "lineage-image.png"
    Image.new("RGB", (640, 360), "#304560").save(image)
    compile_video(
        CompilationRequest(
            spans=(CompilationSpan(0, "lineage", 0, 30, "image"),),
            audio_path=audio,
            asset_paths={"image": image},
            output_path=artifact,
            target=CompilationTarget(width=640, height=360, fps=30),
            encoder_override="libx264",
        ),
        runner=FakeMediaRunner(default_total_frames=30, default_duration=1.0,
                               default_width=640, default_height=360, default_fps=30.0,
                               default_pix_fmt="yuv420p"),
        base_config=config,
    )
    monkeypatch.setattr(render, "render_code_fingerprint", lambda: "e" * 64)
    monkeypatch.setattr(render, "render_tool_version", lambda: "FFmpeg test build")
    monkeypatch.setattr("youtube_automation.video.compiler.load_video_config", lambda *_: dict(config))
    monkeypatch.setattr(review, "review_context", lambda _: (brief, plan))
    monkeypatch.setattr(cli, "_validated_plan", lambda _: (brief, plan, timeline))
    monkeypatch.setattr(review, "load_brief", lambda _: brief)
    monkeypatch.setattr(review, "verify_generated_assets", lambda *_: None)
    monkeypatch.setattr(flow, "verify_generated_assets", lambda *_: None)
    monkeypatch.setattr(review, "read_shot_receipt", lambda *_: {"sha256": assets["asset"]})
    monkeypatch.setattr(cli, "read_shot_receipt", lambda *_: {"sha256": assets["asset"]})
    monkeypatch.setattr(review, "publication_guard", nullcontext)
    monkeypatch.setattr(render, "publication_guard", nullcontext)
    monkeypatch.setattr(render, "probe_video", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(cli, "probe_video", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        render, "detect_hardware_encoder",
        lambda cfg: {"video_codec": "libx264", "encoder_name": "libx264", "hwaccel": "none", "encoder_args": ["-crf", str(cfg["CPU_CRF"])]},
    )
    inputs = render.current_render_inputs(plan, assets, audio, config)
    pointer = {
        "path": artifact.name, "sha256": render.file_digest(artifact),
        "inputs": inputs, "generation": fingerprint(inputs), "frames": 30,
        "editorial_status": "pending",
        "encoder_execution": {"version": 1, "assembly": inputs["encoder_policy"]["assembly"],
                              "clips": [{"index": 0, "sha256": "d" * 64,
                                         "execution": {"encoder_recipe": inputs["encoder_recipe"], "fallback_from": None}}]},
    }
    (tmp_path / "adaptive_preview.json").write_text(json.dumps(pointer), encoding="utf-8")
    return plan, config, pointer


@pytest.mark.parametrize("change", ["code", "tool", "overlay", "config", "audio", "encoder"])
def test_current_lineage_rejects_stale_cache_and_approval(tmp_path, monkeypatch, change):
    from youtube_automation.production import cli, render, review

    _, config, _ = _lineage_fixture(tmp_path, monkeypatch)
    assert cli._render_output_complete(tmp_path, preview=True)
    if change == "encoder":
        monkeypatch.setattr(render, "_build_encoder_config", lambda *_: {
            "video_codec": "libx264", "encoder_name": "libx264", "hwaccel": "none", "encoder_args": ["-crf", "17"],
        })
        monkeypatch.setattr(render, "detect_hardware_encoder", lambda _cfg: {
            "video_codec": "h264_nvenc", "encoder_name": "h264_nvenc", "hwaccel": "cuda", "encoder_args": ["-cq", "19"],
        })
    elif change == "code":
        monkeypatch.setattr(render, "render_code_fingerprint", lambda: "f" * 64)
    elif change == "tool":
        monkeypatch.setattr(render, "render_tool_version", lambda: "FFmpeg revised build")
    elif change == "overlay":
        original = render.overlay_filter_recipe
        monkeypatch.setattr(render, "overlay_filter_recipe", lambda *a: original(*a, font="Different font"))
    elif change == "config":
        config["CPU_CRF"] = 28
    else:
        (tmp_path / "audio.wav").write_bytes(b"different canonical audio")
    assert not cli._render_output_complete(tmp_path, preview=True)
    with pytest.raises(ValueError, match="stale"):
        review.approve_review(tmp_path, "Human")
    assert not (tmp_path / "editorial_approval.json").exists()


def test_current_lineage_reuses_unchanged_preview_and_approves(tmp_path, monkeypatch):
    from youtube_automation.production import cli, review

    _lineage_fixture(tmp_path, monkeypatch)
    assert cli._render_output_complete(tmp_path, preview=True)
    review.approve_review(tmp_path, "Human")
    assert (tmp_path / "editorial_approval.json").is_file()
    assert cli._render_output_complete(tmp_path, preview=True)


def _explicit_approval_recipe_fixture(tmp_path, monkeypatch, *, asset_identity="storage"):
    import json

    from youtube_automation.production import render
    from youtube_automation.production.assets import asset_storage_id
    from youtube_automation.production.contracts import fingerprint

    plan, _, pointer = _lineage_fixture(tmp_path, monkeypatch)
    config = {"OUTPUT_WIDTH": 640, "OUTPUT_HEIGHT": 360, "OUTPUT_FPS": 30}
    encoder = {"video_codec": "libx264", "encoder_args": ["-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p"]}
    assets = pointer["inputs"]["assets"]
    if asset_identity == "shot":
        assets = {shot.shot_id: assets[asset_storage_id(shot)] for shot in plan.shots}
    inputs = render.current_render_inputs(
        plan, assets, tmp_path / "audio.wav", config,
        encoder_config=encoder,
    )
    pointer["inputs"] = inputs
    pointer["generation"] = fingerprint(inputs)
    pointer["encoder_execution"]["assembly"] = inputs["encoder_policy"]["assembly"]
    pointer["encoder_execution"]["clips"][0]["execution"]["encoder_recipe"] = inputs["encoder_recipe"]
    (tmp_path / "adaptive_preview.json").write_text(json.dumps(pointer), encoding="utf-8")
    return config, encoder, pointer


def test_approval_accepts_explicit_executed_recipe_without_default_detection(tmp_path, monkeypatch):
    from youtube_automation.production import render, review

    config, encoder, pointer = _explicit_approval_recipe_fixture(tmp_path, monkeypatch)

    def unexpected_defaults(*_args):
        pytest.fail("Explicit approval recipes must not load or detect unrelated defaults")

    monkeypatch.setattr("youtube_automation.video.compiler.load_video_config", unexpected_defaults)
    monkeypatch.setattr(render, "detect_hardware_encoder", unexpected_defaults)
    review.approve_review(tmp_path, "Human", config=config, encoder_config=encoder)
    assert (tmp_path / "editorial_approval.json").is_file()
    assert render.file_digest(tmp_path / pointer["path"]) == pointer["sha256"]
    assert config == {"OUTPUT_WIDTH": 640, "OUTPUT_HEIGHT": 360, "OUTPUT_FPS": 30}
    assert encoder["encoder_args"] == ["-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p"]


@pytest.mark.parametrize(
    "change,reason",
    [("config", "stale"), ("encoder", "stale"), ("missing_execution", "Missing current encoder")],
)
def test_explicit_approval_rejects_recipe_mismatch_and_missing_execution(
    tmp_path, monkeypatch, change, reason,
):
    import json

    from youtube_automation.production import review

    config, encoder, pointer = _explicit_approval_recipe_fixture(tmp_path, monkeypatch)
    if change == "config":
        config = dict(config, OUTPUT_WIDTH=800)
    elif change == "encoder":
        encoder = dict(encoder, encoder_args=["-crf", "18"])
    else:
        pointer.pop("encoder_execution")
        (tmp_path / "adaptive_preview.json").write_text(json.dumps(pointer), encoding="utf-8")
    with pytest.raises(ValueError, match=reason):
        review.approve_review(tmp_path, "Human", config=config, encoder_config=encoder)
    assert not (tmp_path / "editorial_approval.json").exists()


@pytest.mark.parametrize("asset_identity", ["storage", "shot"])
def test_explicit_approval_asset_namespace_preserves_exact_preview_recipe(tmp_path, monkeypatch, asset_identity):
    import json

    from youtube_automation.production import review

    config, encoder, pointer = _explicit_approval_recipe_fixture(
        tmp_path, monkeypatch, asset_identity=asset_identity,
    )
    review.approve_review(
        tmp_path, "Human", config=config, encoder_config=encoder, asset_identity=asset_identity,
    )
    assert json.loads((tmp_path / "adaptive_preview.json").read_text()) == pointer
    approval = json.loads((tmp_path / "editorial_approval.json").read_text())
    assert approval["generation"] == pointer["generation"]
    assert approval["preview_sha256"] == pointer["sha256"]


@pytest.mark.parametrize("change", ["wrong_alias", "missing", "extra", "hash", "wrong_mode"])
def test_explicit_shot_asset_aliases_cannot_change_receipt_bindings(tmp_path, monkeypatch, change):
    import json

    from youtube_automation.production import review
    from youtube_automation.production.contracts import fingerprint

    config, encoder, pointer = _explicit_approval_recipe_fixture(tmp_path, monkeypatch, asset_identity="shot")
    assets = pointer["inputs"]["assets"]
    key = next(iter(assets))
    mode = "shot"
    if change == "wrong_alias":
        pointer["inputs"]["assets"] = {"unrelated_shot": assets[key]}
    elif change == "missing":
        pointer["inputs"]["assets"] = {}
    elif change == "extra":
        assets["extra_shot"] = assets[key]
    elif change == "hash":
        assets[key] = "f" * 64
    else:
        mode = "storage"
    pointer["generation"] = fingerprint(pointer["inputs"])
    (tmp_path / "adaptive_preview.json").write_text(json.dumps(pointer), encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        review.approve_review(
            tmp_path, "Human", config=config, encoder_config=encoder, asset_identity=mode,
        )
    assert not (tmp_path / "editorial_approval.json").exists()


def test_approval_rejects_unknown_asset_namespace(tmp_path):
    from youtube_automation.production import review

    with pytest.raises(ValueError, match="Unknown render asset identity"):
        review.approve_review(tmp_path, "Human", asset_identity="unknown")


def test_tampered_approved_preview_blocks_master_cache_and_orphan(tmp_path, monkeypatch):
    import json

    from youtube_automation.production import cli, render, review

    _, _, pointer = _lineage_fixture(tmp_path, monkeypatch)
    review.approve_review(tmp_path, "Human")
    generation = pointer["generation"]
    destination = tmp_path / "adaptive_renders" / generation / ("master-" + pointer["sha256"] + ".mp4")
    destination.parent.mkdir(parents=True)
    _copy_compiled_artifact(tmp_path / pointer["path"], destination)
    master = dict(pointer, editorial_status="approved", path=str(destination.relative_to(tmp_path)))
    (tmp_path / "active_master.json").write_text(json.dumps(master), encoding="utf-8")
    assert cli._render_output_complete(tmp_path, preview=False)
    (tmp_path / pointer["path"]).write_bytes(b"tampered preview bytes")
    assert not cli._render_output_complete(tmp_path, preview=False)
    journal = render._render_journal_path(tmp_path, generation, False)
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({"version": 1, "kind": "master", "pointer": master}), encoding="utf-8")
    with pytest.raises(ValueError, match="Preview is stale or changed"):
        render._recover_render_publication(tmp_path, generation, pointer["inputs"], 30, 30, preview=False)
    assert json.loads((tmp_path / "active_master.json").read_text()) == master


def test_preview_is_rehashed_inside_approval_publication_guard(tmp_path, monkeypatch):
    from contextlib import contextmanager

    from youtube_automation.production import review

    _, _, pointer = _lineage_fixture(tmp_path, monkeypatch)

    from youtube_automation.production import render

    inputs_computed = False
    real_inputs = render.current_render_inputs

    def current_inputs(*args, **kwargs):
        nonlocal inputs_computed
        result = real_inputs(*args, **kwargs)
        inputs_computed = True
        return result

    @contextmanager
    def tamper_before_publication():
        if inputs_computed:
            (tmp_path / pointer["path"]).write_bytes(b"concurrently changed preview")
        yield

    monkeypatch.setattr(render, "current_render_inputs", current_inputs)

    monkeypatch.setattr(review, "publication_guard", tamper_before_publication)
    with pytest.raises(ValueError, match="Preview is stale or changed"):
        review.approve_review(tmp_path, "Human")
    assert not (tmp_path / "editorial_approval.json").exists()


def test_executable_source_lineage_ignores_comments_and_crlf_but_not_code(tmp_path, monkeypatch):
    from youtube_automation.production import render

    package_root = tmp_path / "youtube_automation"
    production_root = package_root / "production"
    video_root = package_root / "video"
    production_root.mkdir(parents=True)
    video_root.mkdir()
    monkeypatch.setattr(render, "__file__", str(production_root / "render.py"))
    monkeypatch.setattr(render.video_encoder, "__file__", str(video_root / "encoder.py"))

    dependencies = (
        production_root / "render.py",
        production_root / "graphic_cues.py",
        production_root / "pictograms.py",
        video_root / "encoder.py",
        video_root / "engine.py",
        video_root / "filter_graph.py",
        video_root / "subtitles.py",
        video_root / "ken_burns.py",
        video_root / "journal.py",
        video_root / "runner.py",
        video_root / "receipt.py",
        video_root / "schema.py",
    )
    for path in dependencies:
        path.write_bytes(b"value = 1\n")

    baseline = render.render_code_fingerprint()
    (production_root / "render.py").write_bytes(b"# harmless comment\r\nvalue = 1\r\n")
    assert render.render_code_fingerprint() == baseline

    for path in dependencies:
        path.write_bytes(b"value = 2\n")
        assert render.render_code_fingerprint() != baseline, path.name
        path.write_bytes(b"value = 1\n")
        assert render.render_code_fingerprint() == baseline, path.name

def test_renderer_dependency_changes_invalidate_current_render_inputs(tmp_path, monkeypatch):
    from youtube_automation.production import render

    original_fingerprint = render.render_code_fingerprint
    plan, config, _ = _lineage_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(render, "render_code_fingerprint", original_fingerprint)

    package_root = tmp_path / "isolated_checkout" / "youtube_automation"
    production_root = package_root / "production"
    video_root = package_root / "video"
    production_root.mkdir(parents=True)
    video_root.mkdir()
    monkeypatch.setattr(render, "__file__", str(production_root / "render.py"))
    monkeypatch.setattr(render.video_encoder, "__file__", str(video_root / "encoder.py"))

    dependencies = (
        production_root / "render.py",
        production_root / "graphic_cues.py",
        production_root / "pictograms.py",
        video_root / "encoder.py",
        video_root / "engine.py",
        video_root / "filter_graph.py",
        video_root / "subtitles.py",
        video_root / "ken_burns.py",
        video_root / "journal.py",
        video_root / "runner.py",
        video_root / "receipt.py",
        video_root / "schema.py",
    )
    for path in dependencies:
        path.write_bytes(b"value = 1\n")

    encoder = {
        "video_codec": "libx264",
        "encoder_name": "libx264",
        "hwaccel": "none",
        "encoder_args": ["-crf", "17"],
    }
    audio = tmp_path / "audio.wav"
    assets = {"asset": "d" * 64}
    baseline = render.current_render_inputs(
        plan, assets, audio, config, encoder_config=encoder
    )

    unrelated = package_root / "unrelated.py"
    unrelated.write_bytes(b"value = 2\n")
    assert render.current_render_inputs(
        plan, assets, audio, config, encoder_config=encoder
    ) == baseline

    for path in dependencies:
        path.write_bytes(b"value = 2\n")
        changed = render.current_render_inputs(
            plan, assets, audio, config, encoder_config=encoder
        )
        assert changed["render_code_sha256"] != baseline["render_code_sha256"], path.name
        assert changed != baseline, path.name
        path.write_bytes(b"value = 1\n")
        assert render.current_render_inputs(
            plan, assets, audio, config, encoder_config=encoder
        ) == baseline, path.name


def test_ass_fingerprint_is_checkout_independent():
    from youtube_automation.production.render import OverlayAssPass

    assert OverlayAssPass(0, False, "a\nb\n").sha256 == OverlayAssPass(0, False, "a\r\nb\r\n").sha256


@pytest.mark.parametrize("separator", ["\u2028", "\u0085", "\v", "\f", "\x1c", "\x1d", "\x1e"])
def test_high_rate_recipe_preserves_unicode_text_separators(separator):
    from youtube_automation.production.render import overlay_filter_recipe

    text = "before" + separator + "after"
    shot = fixture_shot(end_frame=120, overlays=[
        Overlay(kind="label", start_frame=0, end_frame=120, text=text),
        Overlay(kind="timer", start_frame=0, end_frame=120, text="00:01",
                value_from=1, clock_start_frame=0),
    ])
    rendered = "\n".join(item.ass_text for item in overlay_filter_recipe(shot, 640, 360, 120).passes)
    assert text in rendered


def test_review_recipe_declares_canonical_canvas():
    from youtube_automation.production.render import overlay_filter_recipe, overlay_review_evidence

    shot = fixture_shot(overlays=[Overlay(kind="label", start_frame=0, end_frame=180, text="Label")])
    evidence = overlay_review_evidence(shot, 30)["overlay_recipe"]
    assert evidence["canvas"] == {"width": 1920, "height": 1080}
    assert evidence["fingerprint"] == overlay_filter_recipe(shot, 1920, 1080, 30).fingerprint
    assert evidence["fingerprint"] != overlay_filter_recipe(shot, 640, 360, 30).fingerprint


def test_archived_rejection_blocks_approval_cache_and_orphan_activation(tmp_path, monkeypatch):
    import json

    from youtube_automation.production import cli, render, review

    plan, _, pointer = _lineage_fixture(tmp_path, monkeypatch)
    review.approve_review(tmp_path, "Human")
    review.record_preview_rejection(tmp_path, "Human", ["Rejected first preview"], overall_rating=1.5)
    (tmp_path / "human_review_rejection.json").unlink()
    master = dict(pointer, editorial_status="approved")
    (tmp_path / "active_master.json").write_text(json.dumps(master), encoding="utf-8")
    with pytest.raises(ValueError, match="Human rejected"):
        review.approve_review(tmp_path, "Human")
    with pytest.raises(ValueError, match="Human rejected"):
        review.record_preview_scorecard(tmp_path, "Human", {})
    with pytest.raises(ValueError, match="Human rejected"):
        cli._render_output_complete(tmp_path, preview=False)
    generation = pointer["generation"]
    destination = tmp_path / "adaptive_renders" / generation / ("master-" + pointer["sha256"] + ".mp4")
    destination.parent.mkdir(parents=True)
    _copy_compiled_artifact(tmp_path / pointer["path"], destination)
    master["path"] = str(destination.relative_to(tmp_path))
    journal = render._render_journal_path(tmp_path, generation, False)
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({"version": 1, "kind": "master", "pointer": master}), encoding="utf-8")
    with pytest.raises(ValueError, match="Human rejected"):
        render._recover_render_publication(tmp_path, generation, pointer["inputs"], 30, 30, preview=False)
    assert json.loads((tmp_path / "active_master.json").read_text()) == dict(pointer, editorial_status="approved")
    review.require_no_human_rejection(tmp_path, review.fingerprint(plan), "f" * 64)
    preview_destination = tmp_path / "adaptive_renders" / generation / ("preview-" + pointer["sha256"] + ".mp4")
    _copy_compiled_artifact(tmp_path / pointer["path"], preview_destination)
    preview_pointer = dict(pointer, path=str(preview_destination.relative_to(tmp_path)))
    preview_journal = render._render_journal_path(tmp_path, generation, True)
    preview_journal.write_text(json.dumps({"version": 1, "kind": "preview", "pointer": preview_pointer}), encoding="utf-8")
    before_preview = (tmp_path / "adaptive_preview.json").read_bytes()
    with pytest.raises(ValueError, match="Human rejected"):
        render._recover_render_publication(tmp_path, generation, pointer["inputs"], 30, 30, preview=True)
    assert (tmp_path / "adaptive_preview.json").read_bytes() == before_preview
    assert preview_journal.exists()
    assert preview_destination.exists()


def test_fixation_and_cue_badge_hold_the_same_state_across_cuts():
    kinds = ["fixation_cue", "start_transition"]
    first = fixture_shot(end_frame=120, overlays=[
        Overlay(kind=kind, start_frame=90, end_frame=120, text="ابدأ" if kind == "start_transition" else "")
        for kind in kinds
    ])
    second = fixture_shot(start_frame=120, end_frame=180, overlays=[
        Overlay(kind=kind, start_frame=0, end_frame=30, text="ابدأ" if kind == "start_transition" else "")
        for kind in kinds
    ])
    contents = []
    for shot in (first, second):
        ass = overlay_ass(shot, 1920, 1080, 30)
        assert "\\t(" not in ass and "\\fad(" not in ass
        contents.append([line.split(",", 9)[9] for line in ass.split("\n") if line.startswith("Dialogue:")])
    assert contents[0] == contents[1]


def test_semantic_title_templates_retain_copy_in_rendered_ass():
    import json
    from pathlib import Path

    from youtube_automation.production.shots import SemanticGraphic, _graphic_overlays

    case = json.loads((Path(__file__).parents[1] / "fixtures" / "semantic_graphic_copy_v1.json").read_text())
    assert case["version"] == 1
    for template in case["templates"]:
        graphic = SemanticGraphic.model_validate({**case["graphic"], "template": template})
        overlays = _graphic_overlays(graphic, 180)
        shot = fixture_shot(local_composition=template, overlays=overlays)
        rendered = overlay_ass(shot, 1920, 1080, 30)
        assert graphic.primary_text in rendered
        assert graphic.secondary_text in rendered
        import re

        assert min(int(size) for size in re.findall(r"\\an5\\b1\\fs(\d+)", rendered)) >= 64
        assert "\\pos(960,508)" in rendered
        assert "\\pos(960,777)" in rendered
        if template == "focus_sweep":
            assert "\\move(" in rendered


def fixture_shot(**updates):
    return Shot(
        **(
            {
                "shot_id": "s",
                "scene_id": "scene",
                "asset_id": "asset",
                "entity_ids": ["cat"],
                "span_ids": [0],
                "start_frame": 0,
                "end_frame": 180,
                "purpose": "Explain",
                "treatment": "subject_scene",
                "subject": "Cat",
                "visible_state": "Looking at hand",
                "setting": "Garden",
                "framing": "close_up",
                "composition": "Close-up",
            }
            | updates
        )
    )


def test_hold_and_focal_motion():
    hold = camera_filter(fixture_shot(), 640, 360, 30)
    assert "z='1.0'" in hold
    assert "on" not in hold
    moving = camera_filter(fixture_shot(motion="push", zoom=1.04, focal_x=0.3), 640, 360, 30)
    assert "clip(on,0,179)" in moving
    assert "iw*0.3" in moving
    assert "1.25" not in moving


def test_motion_needs_visible_travel_and_pan_preserves_focal_subject():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="requires zoom above 1"):
        fixture_shot(motion="pan_right")
    with pytest.raises(ValueError, match="No safe pan travel"):
        camera_filter(fixture_shot(motion="pan_right", zoom=1.05, focal_x=0.01), 640, 360, 30)
    graph = camera_filter(fixture_shot(motion="pan_left", zoom=1.05), 640, 360, 30)
    assert "0.75*iw/zoom" in graph
    assert "0.25*iw/zoom" in graph


def test_real_aspect_crop_keeps_off_center_subject(tmp_path):
    import shutil
    import subprocess

    import pytest
    from PIL import Image, ImageDraw

    if not shutil.which("ffmpeg"):
        pytest.skip("Real FFmpeg unavailable")
    cases = [
        ((640, 480), (280, 435, 360, 475), {"focal_y": 0.92}),
        ((800, 360), (745, 140, 795, 220), {"focal_x": 0.96}),
    ]
    for index, (source_size, subject_box, focal) in enumerate(cases):
        source = tmp_path / f"off-center-{index}.png"
        image = Image.new("RGB", source_size, "black")
        ImageDraw.Draw(image).rectangle(subject_box, fill="red")
        image.save(source)
        graph = camera_filter(fixture_shot(end_frame=1, **focal), 640, 360, 30, source_size)
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(source), "-vf", graph, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True,
            timeout=30,
            check=True,
        )
        frame = Image.frombytes("RGB", (640, 360), result.stdout)
        red_pixels = sum(
            1 for red, green, blue in frame.getdata() if red > 150 and green < 80 and blue < 80
        )
        assert red_pixels > 1000


def test_arabic_overlay_is_local_and_escapes_ass_commands():
    shot = fixture_shot(
        overlays=[Overlay(kind="label", start_frame=30, end_frame=60, text="عين القط {\\pos(0,0)}")]
    )
    ass = overlay_ass(shot, 640, 360, 30)
    assert "عين القط" in ass
    assert "0:00:01.00,0:00:02.00" in ass
    assert "{\\pos(0,0)}" not in ass


def test_schulte_grid_and_timer_are_deterministic_local_graphics():
    shot = fixture_shot(
        overlays=[
            Overlay(
                kind="data_grid",
                preset="schulte_6x6",
                start_frame=0,
                end_frame=180,
                x=0.2,
                y=0.1,
                width=0.6,
                height=0.8,
                highlight_cells=[0, 10],
            ),
            Overlay(
                kind="timer",
                start_frame=0,
                end_frame=180,
                text="00:40",
                x=0.82,
                y=0.05,
                width=0.15,
                height=0.1,
            ),
        ]
    )
    ass = overlay_ass(shot, 1920, 1080, 30)
    assert "00:40" in ass
    assert "m 0 0 l 1344 0 1344 756" in ass
    assert all(f"}}{number}\n" in ass or f"}}{number}\r\n" in ass for number in map(str, range(1, 37)))
    from youtube_automation.production.render import overlay_review_evidence

    evidence = overlay_review_evidence(shot, 30)
    assert evidence["camera_motion"] == "hold"
    assert evidence["local_property_animation"] is False
    assert evidence["local_fade_animation"] is False
    assert evidence["start_transition_behavior"] is None
    assert evidence["timer_behavior"] == "fixed readout"


def test_schulte_grid_values_are_replaced_with_the_deterministic_preset():
    overlay = Overlay(
        kind="data_grid",
        preset="schulte_6x6",
        cells=[str(value) for value in range(36)],
        rows=6,
        columns=6,
        start_frame=0,
        end_frame=30,
    )
    assert overlay.cells == SCHULTE_6X6


def test_editorial_overlay_primitives_render_deterministic_motion_and_states():
    shot = fixture_shot(
        end_frame=240,
        overlays=[
            Overlay(kind="card", start_frame=0, end_frame=240, text="Memory"),
            Overlay(kind="progress_ring", start_frame=0, end_frame=120, progress=0.75),
            Overlay(
                kind="tile_reveal",
                start_frame=15,
                end_frame=135,
                rows=2,
                columns=2,
                cells=["A", "B", "C", "D"],
                reveal_cells=[0, 3],
            ),
            Overlay(kind="focus_sweep", start_frame=30, end_frame=90),
            Overlay(
                kind="comparison",
                start_frame=60,
                end_frame=180,
                text="Before",
                secondary_text="After",
            ),
            Overlay(
                kind="trace_path",
                start_frame=90,
                end_frame=210,
                x=0,
                y=0,
                width=1,
                height=1,
                points=[(0.0, 0.8), (0.5, 0.2), (1.0, 0.6)],
            ),
            Overlay(
                kind="counter",
                start_frame=120,
                end_frame=240,
                value_from=1,
                value_to=3,
                text="/ 3",
            ),
        ],
    )

    ass = overlay_ass(shot, 1000, 600, 30)

    assert "Memory" in ass
    assert "Before" in ass and "After" in ass
    assert "\\move(" in ass
    assert "m 0 480 l 500 120 1000 360" in ass
    assert "}1 / 3" in ass and "}3 / 3" in ass
    assert ass.count("Dialogue:") >= 12


def test_branded_schulte_challenge_renders_rule_fixation_target_and_start_transition():
    shot = fixture_shot(
        end_frame=300,
        narrative_role="diagram",
        framing="diagram",
        operation="local_canvas",
        local_composition="schulte_challenge",
        overlays=[
            Overlay(kind="challenge_frame", start_frame=0, end_frame=300, text="اختبار التركيز"),
            Overlay(kind="rule_reveal", start_frame=0, end_frame=90, text="ابحث من 1 إلى 36"),
            Overlay(kind="fixation_cue", start_frame=60, end_frame=150),
            Overlay(kind="target_indicator", start_frame=90, end_frame=210, target_cell=10),
            Overlay(kind="start_transition", start_frame=150, end_frame=180, text="ابدأ"),
            Overlay(
                kind="data_grid",
                preset="schulte_6x6",
                start_frame=0,
                end_frame=300,
            ),
        ],
    )

    ass = overlay_ass(shot, 1920, 1080, 30)

    assert "اختبار التركيز" in ass
    assert "ابحث من 1 إلى 36" in ass
    assert "ابدأ" in ass
    assert "\\t(" in ass
    assert "\\pos(960,57)" in ass
    assert "\\clip(" not in ass
    assert "m 0 0 l 1920 0 1920 1080" not in ass
    from youtube_automation.production.render import overlay_review_evidence

    evidence = overlay_review_evidence(shot, 30)
    assert evidence["local_property_animation"] is True
    assert evidence["local_fade_animation"] is True
    assert evidence["start_transition_behavior"] == "static cue-bound header badge; grid unobscured"
    assert all(f"}}{number}\n" in ass or f"}}{number}\r\n" in ass for number in map(str, range(1, 37)))


def test_real_schulte_render_keeps_grid_lines_and_numbers_visible(tmp_path):
    import shutil
    import subprocess

    import pytest
    from PIL import Image

    from youtube_automation.production.shots import SemanticGraphic, _graphic_overlays

    if not shutil.which("ffmpeg"):
        pytest.skip("Real FFmpeg unavailable")
    shot = fixture_shot(narrative_role="diagram", framing="diagram", operation="local_canvas",
                        local_composition="schulte_challenge", overlays=_graphic_overlays(
                            SemanticGraphic(template="schulte_challenge", primary_text="Find in order",
                                            secondary_text="Get ready", timer_text="00:40"), 180))
    from youtube_automation.production.shots import Overlay

    # This pixel fixture explicitly supplies its intended time limit; the
    # semantic compiler no longer invents timed UI without canonical words.
    timer = Overlay(kind="timer", start_frame=0, end_frame=180, text="00:40",
                    x=0.82, y=0.025, width=0.15, height=0.08)
    shot.overlays.append(timer)
    grid = next(o for o in shot.overlays if o.kind == "data_grid")
    assert timer.y + timer.height < grid.y
    (tmp_path / "grid.ass").write_text(overlay_ass(shot, 1920, 1080, 30), encoding="utf-8-sig")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=white:s=1920x1080:r=30", "-vf", "ass=grid.ass",
                    "-frames:v", "1", "-update", "1", "grid.png"],
                   cwd=tmp_path, check=True, timeout=30, capture_output=True)
    with Image.open(tmp_path / "grid.png") as frame:
        pixels = frame.convert("RGB")
        assert max(pixels.getpixel((513, 250))) < 100
        assert max(pixels.getpixel((700, 289))) < 100
        assert any(max(pixels.getpixel((x, y))) < 100
                   for x in range(375, 425) for y in range(210, 240))


def test_real_ffmpeg_preview_and_approval_gate(tmp_path, monkeypatch):
    import json
    import shutil
    import wave
    from pathlib import Path

    import pytest
    from PIL import Image

    from youtube_automation.core.utils import atomic_write_json
    from youtube_automation.production import assets, render
    from youtube_automation.production.contracts import Analysis, Brief, Channel, fingerprint
    from youtube_automation.production.render import probe_video, render_plan
    from youtube_automation.production.review import approve_review
    from youtube_automation.production.shots import ShotPlan, resolve_editorial_policy
    from youtube_automation.video.compiler import load_video_config

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Real FFmpeg tools unavailable")
    monkeypatch.setattr(render, "resource_database", lambda: tmp_path / "render.sqlite3")
    raw = "A calm scene"
    (tmp_path / "raw_transcript.txt").write_text(raw, encoding="utf-8")
    channel = Channel(
        channel_id="test",
        name="Test",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="voice",
        tone="calm",
        style="illustration",
        allowed_treatments=["subject_scene"],
    )
    brief = Brief(
        source_sha256=fingerprint(raw),
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=Analysis(
            topics=["test"],
            claim_basis="factual",
            form="explanation",
            proposition="Scene",
            narrative_strategy="Observe",
            treatments=["subject_scene"],
            rationale="Concrete",
        ),
    )
    atomic_write_json(str(tmp_path / "episode_brief.json"), brief.model_dump())
    timeline = {
        "audio_file": "voice.wav",
        "fps": 30,
        "total_frames": 30,
        "spans": [{"index": 0, "start_frame": 0, "end_frame": 30}],
    }
    atomic_write_json(str(tmp_path / "timeline.json"), timeline)
    with wave.open(str(tmp_path / "voice.wav"), "wb") as audio:
        audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 48000)
    shot = fixture_shot(
        end_frame=30,
        overlays=[
            Overlay(kind="label", start_frame=10, end_frame=25, text="عين القط"),
            Overlay(
                kind="data_grid",
                preset="schulte_6x6",
                start_frame=0,
                end_frame=30,
                x=0.2,
                y=0.1,
                width=0.55,
                height=0.8,
                highlight_cells=[10],
            ),
            Overlay(
                kind="timer",
                start_frame=0,
                end_frame=30,
                text="00:40",
                x=0.78,
                y=0.1,
                width=0.18,
                height=0.12,
            ),
        ],
    )
    plan = ShotPlan(
        shots=[shot],
        brief_sha256=fingerprint(brief),
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=30,
        editorial_policy=resolve_editorial_policy(brief),
    )
    atomic_write_json(str(tmp_path / "shot_plan.json"), plan.model_dump())
    image = tmp_path / "asset.png"
    Image.new("RGB", (640, 360), "#304560").save(image)
    monkeypatch.setattr(assets, "_detect_via_pytesseract", lambda *_: [])
    assets.register_asset(tmp_path, shot, brief, image)
    config = load_video_config()
    config.update(OUTPUT_WIDTH=640, OUTPUT_HEIGHT=360, ENCODER_FORCE="libx264", ENABLE_VBV=False)
    cfg_text = "\n".join(f"{k}={v}" for k, v in config.items())
    (tmp_path / "video_config.txt").write_text(cfg_text, encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        render_plan(tmp_path, config)
    before = (tmp_path / "timeline.json").read_bytes()
    result = render_plan(tmp_path, config, preview=True)
    assert result.is_file()
    probe_video(result, 30, 30, require_audio=True)
    assert (tmp_path / "timeline.json").read_bytes() == before
    assert not (tmp_path / "active_master.json").exists()
    pointer = json.loads((tmp_path / "adaptive_preview.json").read_text())
    assert pointer["editorial_status"] == "pending"

    # A same-duration but edited clip must not be accepted merely because ffprobe passes.
    clip = result.parent / "clip_00000.mp4"
    clip.write_bytes(clip.read_bytes() + b"tampered")
    from youtube_automation.video.runner import SubprocessMediaRunner

    calls = []

    class RecordingRunner(SubprocessMediaRunner):
        def run_ffmpeg(
            self,
            args: list[str],
            *,
            cwd: Path | str | None = None,
            timeout: float | None = None,
        ) -> tuple[str, str]:
            res = super().run_ffmpeg(args, cwd=cwd, timeout=timeout)
            calls.append((args, self.last_execution_cwd or (Path(cwd) if cwd is not None else Path.cwd())))
            return res

    rec_runner = RecordingRunner()
    render_plan(tmp_path, config, preview=True, runner=rec_runner)
    assert any("-/filter_complex" in args for args, _ in calls)
    assert any(
        cwd.name.startswith("youtube-overlay-")
        for args, cwd in calls
        if "-/filter_complex" in args
    )
    approve_review(tmp_path, "Human reviewer")
    master = render_plan(tmp_path, config)
    assert master.name.startswith("master-") and master.suffix == ".mp4"
    active = json.loads((tmp_path / "active_master.json").read_text())
    assert active["editorial_status"] == "approved"
    with pytest.raises(ValueError, match="settings or audio changed"):
        render_plan(tmp_path, dict(config, CPU_CRF=28))
    assert json.loads((tmp_path / "active_master.json").read_text()) == active
    # A crash after the immutable video is written must leave the old pointer usable.
    original_write = render.atomic_write_json
    previous_preview = (tmp_path / "adaptive_preview.json").read_bytes()

    def interrupted_activation(path, value):
        if str(path).endswith("adaptive_preview.json"):
            raise OSError("simulated interrupted activation")
        return original_write(path, value)

    monkeypatch.setattr(render, "atomic_write_json", interrupted_activation)
    with pytest.raises(OSError, match="interrupted activation"):
        render_plan(tmp_path, dict(config, CPU_CRF=28), preview=True)
    assert (tmp_path / "adaptive_preview.json").read_bytes() == previous_preview
    assert assets.file_digest(tmp_path / active["path"]) == active["sha256"]
    monkeypatch.setattr(render, "atomic_write_json", original_write)

    class OrphanFailRunner(SubprocessMediaRunner):
        def run_ffmpeg(
            self,
            args: list[str],
            *,
            cwd: Path | str | None = None,
            timeout: float | None = None,
        ) -> tuple[str, str]:
            pytest.fail("verified orphan should activate without re-encoding")

    recovered = render_plan(tmp_path, dict(config, CPU_CRF=28), preview=True, runner=OrphanFailRunner())
    recovered_pointer = json.loads((tmp_path / "adaptive_preview.json").read_text())
    assert recovered == tmp_path / recovered_pointer["path"]
    assert assets.file_digest(recovered) == recovered_pointer["sha256"]
    assert not any((tmp_path / ".publication_journal" / "renders").glob("*.json"))
    # Accepted assets survive the provider overwriting its scratch candidate.
    image.write_bytes(b"overwritten provider scratch output")
    assert (
        assets.read_receipt(tmp_path, shot.asset_id)["sha256"]
        == pointer["inputs"]["assets"][shot.asset_id]
    )
    plan.shots[0].purpose = "Changed editorial intent"
    atomic_write_json(str(tmp_path / "shot_plan.json"), plan.model_dump())
    with pytest.raises(ValueError, match="stale"):
        approve_review(tmp_path, "Human reviewer")


def test_real_hold_produces_identical_decoded_frames(tmp_path):
    import shutil
    import subprocess

    import pytest
    from PIL import Image

    if not shutil.which("ffmpeg"):
        pytest.skip("Real FFmpeg unavailable")
    source = tmp_path / "source.png"
    image = Image.new("RGB", (640, 360))
    for x in range(640):
        for y in range(360):
            image.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
    image.save(source)
    graph = camera_filter(fixture_shot(end_frame=12), 640, 360, 30)
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(source),
            "-vf",
            graph,
            "-frames:v",
            "12",
            "-f",
            "framemd5",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    hashes = [
        line.rsplit(",", 1)[-1].strip()
        for line in result.stdout.splitlines()
        if line and not line.startswith("#")
    ]
    assert len(hashes) == 12
    assert len(set(hashes)) == 1


def test_timer_ass_time_boundary_quantization_and_ffmpeg_pixel_render(tmp_path):
    import shutil
    import subprocess

    from PIL import Image

    from youtube_automation.production.render import _ass_time, _timer_ass_time, overlay_ass
    from youtube_automation.production.shots import Overlay

    frame_rates = (24, 25, 30, 60)
    for fps in frame_rates:
        for frame in range(fps * 5):
            centiseconds = frame * 100 // fps
            expected = (
                f"{centiseconds // 360000}:"
                f"{centiseconds // 6000 % 60:02d}:"
                f"{centiseconds // 100 % 60:02d}.{centiseconds % 100:02d}"
            )
            time_str = _timer_ass_time(frame, fps)
            assert time_str == expected
            assert centiseconds / 100.0 <= frame / fps + 1e-9
            if frame > 0:
                assert (frame - 1) / fps < centiseconds / 100.0

    # Generic overlays retain rounded ASS timing; only running timer events floor.
    generic_overlay = Overlay(
        kind="label", start_frame=119, end_frame=150, text="generic", x=0.1, y=0.1
    )
    generic_ass = overlay_ass(fixture_shot(overlays=[generic_overlay]), 1920, 1080, 30)
    assert (
        "Dialogue: 0,0:00:03.97,0:00:05.00,Default,,0,0,0,,{\\pos(192,108)}generic"
        in generic_ass
    )
    assert _ass_time(119, 30) == "0:00:03.97"
    assert _timer_ass_time(119, 30) == "0:00:03.96"

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required for timer pixel-boundary verification")

    clock_start_frame = 89
    for fps in frame_rates:
        first_tick_frame = clock_start_frame + fps
        end_frame = first_tick_frame + fps + 2
        timer_overlay = Overlay(
            kind="timer",
            start_frame=0,
            end_frame=end_frame,
            text="00:40",
            x=0.82,
            y=0.025,
            width=0.15,
            height=0.08,
            value_from=40,
            clock_start_frame=clock_start_frame,
        )
        shot = fixture_shot(
            shot_id=f"timer-{fps}",
            start_frame=0,
            end_frame=end_frame,
            overlays=[timer_overlay],
        )
        rendered_ass = overlay_ass(shot, 1920, 1080, fps)
        assert f",{_timer_ass_time(first_tick_frame, fps)},Default" in rendered_ass

        ass_file = tmp_path / f"timer_test_{fps}.ass"
        ass_file.write_text(rendered_ass, encoding="utf-8")
        sampled_frames = [
            clock_start_frame - 1,
            clock_start_frame,
            clock_start_frame + 1,
            first_tick_frame - 1,
            first_tick_frame,
            first_tick_frame + 1,
        ]
        select = "+".join(f"eq(n\\,{frame})" for frame in sampled_frames)
        output_pattern = tmp_path / f"fps_{fps}_%d.png"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c=white:s=1920x1080:d=5:r={fps}",
                "-vf",
                f"ass={ass_file.name},select={select}",
                "-fps_mode",
                "passthrough",
                "-start_number",
                "0",
                "-frames:v",
                "6",
                str(output_pattern),
            ],
            cwd=str(tmp_path),
            timeout=30,
            check=True,
        )
        crops: dict[int, bytes] = {}
        for index, frame in enumerate(sampled_frames):
            out_frame = tmp_path / f"fps_{fps}_{index}.png"
            assert out_frame.exists()
            with Image.open(out_frame) as image:
                crops[frame] = image.crop((1620, 30, 1820, 110)).tobytes()

        assert crops[clock_start_frame - 1] == crops[clock_start_frame]
        assert crops[clock_start_frame] == crops[clock_start_frame + 1]
        assert crops[first_tick_frame - 1] != crops[first_tick_frame]
        assert crops[first_tick_frame] == crops[first_tick_frame + 1]


def test_high_rate_overlay_recipe_keeps_global_timer_phase_and_restores_pts(tmp_path):
    import re
    import shutil
    import subprocess

    import pytest
    from PIL import Image

    from youtube_automation.production.render import overlay_ass, overlay_filter_recipe
    from youtube_automation.production.shots import Overlay

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required high-rate timer pixel verification")

    def render_samples(recipe, fps, frames, work, prefix):
        work.mkdir(parents=True, exist_ok=True)
        ass_files = [f"overlay_{index:02d}.ass" for index in range(len(recipe.passes))]
        for ass_name, ass_pass in zip(ass_files, recipe.passes, strict=True):
            (work / ass_name).write_text(ass_pass.ass_text, encoding="utf-8")
        selection = "+".join(f"eq(n\\,{frame})" for frame in frames)
        graph = f"[0:v]{recipe.filter_chain(ass_files)},select={selection}[vout]"
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"color=c=white:s=640x480:r={fps}:d=3",
                "-filter_complex", graph, "-map", "[vout]", "-fps_mode", "passthrough",
                "-start_number", "0", "-frames:v", str(len(frames)),
                str(work / f"{prefix}_%03d.png"),
            ],
            cwd=str(work),
            timeout=90,
            check=True,
        )
        result = {}
        for index, frame in enumerate(frames):
            with Image.open(work / f"{prefix}_{index:03d}.png") as image:
                result[frame] = image.copy()
        return result

    def render_static_reference(overlays, fps, value, work, filename):
        reference_overlays = [
            Overlay(
                kind="timer",
                start_frame=0,
                end_frame=300,
                text=f"00:{value:02d}",
                x=overlay.x,
                y=overlay.y,
                width=overlay.width,
                height=overlay.height,
                value_from=value,
                clock_start_frame=1000,
            )
            for overlay in overlays
        ]
        reference_shot = fixture_shot(end_frame=300, overlays=reference_overlays)
        ass_path = work / f"{filename}.ass"
        ass_path.write_text(overlay_ass(reference_shot, 640, 480, fps), encoding="utf-8")
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"color=c=white:s=640x480:r={fps}:d=3",
                "-vf", f"ass={ass_path.name}", "-frames:v", "1", "-update", "1",
                str(work / f"{filename}.png"),
            ],
            cwd=str(work),
            timeout=30,
            check=True,
        )
        with Image.open(work / f"{filename}.png") as image:
            return image.copy()

    def timer_crop(image, timer):
        center_x = round((timer.x + timer.width / 2) * 640)
        center_y = round((timer.y + timer.height / 2) * 480)
        return image.crop((center_x - 90, center_y - 23, center_x + 90, center_y + 23)).tobytes()

    clocks = (1, 7, 13, 19, 109, 2, 103)
    for fps in (101, 119, 120):
        sample_frames = sorted(
            {
                frame
                for clock in clocks
                for frame in (
                    clock - 1, clock, clock + 1,
                    clock + fps - 1, clock + fps, clock + fps + 1,
                )
            }
        )
        frame_count = sample_frames[-1] + 1
        overlays = [
            Overlay(
                kind="timer",
                start_frame=0,
                end_frame=frame_count,
                text="00:40",
                x=0.70,
                y=0.12 + index * 0.11,
                width=0.25,
                height=0.08,
                value_from=40,
                clock_start_frame=clock,
            )
            for index, clock in enumerate(clocks)
        ]
        shot = fixture_shot(end_frame=frame_count, overlays=overlays)
        recipe = overlay_filter_recipe(shot, 640, 480, fps)
        assert len(recipe.passes) == 1
        assert recipe.passes[0].timer_pts_scaled
        assert recipe.filter_chain(["overlay_00.ass"]) == (
            "setpts=2*PTS,ass=overlay_00.ass,setpts=PTS/2"
        )

        work = tmp_path / f"fps_{fps}"
        images = render_samples(recipe, fps, sample_frames, work, "actual")
        reference_40 = render_static_reference(overlays, fps, 40, work, "reference_40")
        reference_39 = render_static_reference(overlays, fps, 39, work, "reference_39")

        for overlay, clock in zip(overlays, clocks, strict=True):
            assert timer_crop(images[clock - 1], overlay) == timer_crop(images[clock], overlay)
            assert timer_crop(images[clock], overlay) == timer_crop(images[clock + 1], overlay)
            first_tick = clock + fps
            assert first_tick - 1 in images
            assert first_tick in images
            assert first_tick + 1 in images
            assert timer_crop(images[first_tick - 1], overlay) == timer_crop(reference_40, overlay)
            assert timer_crop(images[first_tick], overlay) == timer_crop(reference_39, overlay)
            assert timer_crop(images[first_tick + 1], overlay) == timer_crop(reference_39, overlay)

        ass_files = [f"overlay_{index:02d}.ass" for index in range(len(recipe.passes))]
        for ass_name, ass_pass in zip(ass_files, recipe.passes, strict=True):
            (work / ass_name).write_text(ass_pass.ass_text, encoding="utf-8")
        graph = (
            "[0:v]format=rgba,"
            f"{recipe.filter_chain(ass_files)},showinfo[out]"
        )
        pts = subprocess.run(
            [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info",
                "-f", "lavfi", "-i", f"color=c=white:s=640x480:d=3:r={fps}",
                "-filter_complex", graph, "-map", "[out]", "-f", "null", "-",
            ],
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert pts.returncode == 0, f"{fps}fps FFmpeg showinfo failed: {pts.stderr[-4000:]}"
        records = [
            (int(frame_index), int(pts_value), float(pts_time))
            for frame_index, pts_value, pts_time in re.findall(
                r"\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:\s*([0-9.]+)",
                pts.stderr,
            )
        ]
        expected_pts = list(range(fps * 3))
        assert len(records) == fps * 3, (
            f"{fps}fps showinfo frame count {len(records)} != {fps * 3}: "
            f"{pts.stderr[-4000:]}"
        )
        assert [(frame_index, pts_value) for frame_index, pts_value, _ in records] == [
            (index, index) for index in expected_pts
        ], f"{fps}fps PTS did not restore exactly: {pts.stderr[-4000:]}"

    # A global clock starts at frame 7 and crosses into a shot at frame 125:
    # the first local tick is frame 2, with correct prior/tick/hold pixels.
    cut_overlay = Overlay(
        kind="timer", start_frame=0, end_frame=8, text="00:40",
        x=0.70, y=0.12, width=0.25, height=0.08,
        value_from=40, clock_start_frame=7,
    )
    cut_shot = fixture_shot(start_frame=125, end_frame=133, overlays=[cut_overlay])
    cut_recipe = overlay_filter_recipe(cut_shot, 640, 480, 120)
    cut_images = render_samples(cut_recipe, 120, [1, 2, 3], tmp_path / "cross_cut", "cut")
    cut_reference_40 = render_static_reference(
        [cut_overlay], 120, 40, tmp_path / "cross_cut", "reference_40"
    )
    cut_reference_39 = render_static_reference(
        [cut_overlay], 120, 39, tmp_path / "cross_cut", "reference_39"
    )
    assert timer_crop(cut_images[1], cut_overlay) == timer_crop(cut_reference_40, cut_overlay)
    assert timer_crop(cut_images[2], cut_overlay) == timer_crop(cut_reference_39, cut_overlay)
    assert timer_crop(cut_images[3], cut_overlay) == timer_crop(cut_reference_39, cut_overlay)


def test_high_rate_recipe_preserves_ass_layer_and_same_layer_order(tmp_path):
    import shutil
    import subprocess

    from PIL import Image

    from youtube_automation.production.render import _overlay_recipe_from_ass
    from youtube_automation.production.shots import Overlay

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required for ASS layer-order verification")

    timer = Overlay(
        kind="timer", start_frame=0, end_frame=120, text="00:40",
        x=0.20, y=0.20, width=0.35, height=0.15, value_from=40,
        clock_start_frame=0,
    )
    same_layer = Overlay(
        kind="label", start_frame=0, end_frame=120, text="same layer",
        x=0.20, y=0.20, width=0.35, height=0.15,
    )
    upper_layer = Overlay(
        kind="label", start_frame=0, end_frame=120, text="upper layer",
        x=0.20, y=0.20, width=0.35, height=0.15,
    )
    shot = fixture_shot(end_frame=120, overlays=[timer, same_layer, upper_layer])
    marked_ass = overlay_ass(shot, 1280, 720, 120, mark_timer_events=True)
    layer_ass = "\n".join(
        line.replace("Dialogue: 0,", "Dialogue: 1,", 1)
        if line.endswith("upper layer") else line
        for line in marked_ass.splitlines()
    ) + "\n"
    recipe = _overlay_recipe_from_ass(layer_ass, 120, scale_timer_events=True)
    assert [(item.layer, item.timer_pts_scaled) for item in recipe.passes] == [
        (0, True), (0, False), (1, False)
    ]
    assert "__timer_frame__" not in "".join(item.ass_text for item in recipe.passes)
    assert "same layer" in recipe.passes[1].ass_text
    assert "upper layer" in recipe.passes[2].ass_text

    work = tmp_path / "layer_order"
    work.mkdir()
    pass_files = [f"pass_{index:02d}.ass" for index in range(len(recipe.passes))]
    dialogues = []
    header = recipe.passes[0].ass_text.split("Dialogue: ", 1)[0]
    for ass_name, ass_pass in zip(pass_files, recipe.passes, strict=True):
        (work / ass_name).write_text(ass_pass.ass_text, encoding="utf-8")
        dialogues.extend(
            line for line in ass_pass.ass_text.splitlines()
            if line.startswith("Dialogue: ")
        )
    (work / "merged_reference.ass").write_text(
        header + "\n".join(dialogues) + "\n", encoding="utf-8"
    )
    frame = 5
    select = f"select=eq(n\\,{frame})"
    split_graph = f"[0:v]{recipe.filter_chain(pass_files)},{select}[vout]"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=white:s=1280x720:r=120",
            "-filter_complex", split_graph, "-map", "[vout]", "-frames:v", "1",
            str(work / "split.png"),
        ],
        cwd=str(work),
        timeout=30,
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=white:s=1280x720:r=120",
            "-vf", f"ass=merged_reference.ass,{select}", "-frames:v", "1",
            str(work / "merged.png"),
        ],
        cwd=str(work),
        timeout=30,
        check=True,
    )
    with Image.open(work / "split.png") as split, Image.open(work / "merged.png") as merged:
        assert split.tobytes() == merged.tobytes()


def test_moving_pictogram_uses_local_arrival_frame():
    from youtube_automation.production.shots import Overlay

    overlay = Overlay(
        kind="pictogram",
        start_frame=10,
        end_frame=40,
        icon="cursor",
        x=0.10,
        y=0.10,
        width=0.10,
        height=0.10,
        motion_to=(0.80, 0.70),
        motion_end_frame=20,
    )
    rendered = overlay_ass(fixture_shot(overlays=[overlay]), 1920, 1080, 30)
    assert "\\move(192,108,1536,756,0,333)" in rendered


def test_high_rate_generic_ass_timing_remains_unscaled(tmp_path):
    import shutil
    import subprocess

    import pytest
    from PIL import Image, ImageChops

    from youtube_automation.production.render import overlay_ass, overlay_filter_recipe
    from youtube_automation.production.shots import Overlay

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required high-rate generic fade pixel verification")

    for fps in (101, 119, 120):
        duration_frames = 2 * fps
        transition = Overlay(
            kind="rule_reveal",
            start_frame=0,
            end_frame=duration_frames,
            text="Ready",
            x=0.20,
            y=0.20,
            width=0.60,
            height=0.20,
        )
        timer = Overlay(
            kind="timer",
            start_frame=0,
            end_frame=duration_frames,
            text="00:40",
            x=0.70,
            y=0.12,
            width=0.25,
            height=0.08,
            value_from=40,
            clock_start_frame=duration_frames + fps,
        )
        shot = fixture_shot(end_frame=duration_frames, overlays=[transition, timer])
        original_ass = overlay_ass(shot, 640, 480, fps)
        recipe = overlay_filter_recipe(shot, 640, 480, fps)
        assert recipe.passes
        assert recipe.passes[0].timer_pts_scaled is False
        generic_ass = "\\n".join(
            ass_pass.ass_text
            for ass_pass in recipe.passes
            if not ass_pass.timer_pts_scaled
        )
        assert "\\fad(180,0)" in generic_ass
        assert "0:00:00.00,0:00:02.00" in generic_ass

        sample_frames = sorted(
            {
                0,
                round(fps * 0.04),
                round(fps * 0.08),
                round(fps * 0.20),
                duration_frames - round(fps * 0.16),
                duration_frames - round(fps * 0.08),
                duration_frames - 1,
            }
        )
        work = tmp_path / f"generic_fade_{fps}"
        work.mkdir()
        ass_files = [f"overlay_{index:02d}.ass" for index in range(len(recipe.passes))]
        for ass_name, ass_pass in zip(ass_files, recipe.passes, strict=True):
            (work / ass_name).write_text(ass_pass.ass_text, encoding="utf-8")
        (work / "original.ass").write_text(original_ass, encoding="utf-8")
        selection = "+".join(f"eq(n\\,{frame})" for frame in sample_frames)
        graphs = {
            "actual": f"[0:v]{recipe.filter_chain(ass_files)},select={selection}[vout]",
            "reference": f"[0:v]ass=original.ass,select={selection}[vout]",
        }
        for prefix, graph in graphs.items():
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c=white:s=640x480:r={fps}:d=3",
                    "-filter_complex", graph, "-map", "[vout]", "-fps_mode", "passthrough",
                    "-start_number", "0", "-frames:v", str(len(sample_frames)),
                    str(work / f"{prefix}_%03d.png"),
                ],
                cwd=str(work),
                timeout=90,
                check=True,
            )

        actual_frames = []
        reference_frames = []
        for index, _ in enumerate(sample_frames):
            with Image.open(work / f"actual_{index:03d}.png") as image:
                actual_frames.append(image.copy())
            with Image.open(work / f"reference_{index:03d}.png") as image:
                reference_frames.append(image.copy())
        for actual, reference in zip(actual_frames, reference_frames, strict=True):
            assert ImageChops.difference(actual, reference).getbbox() is None

        def fade_crop(image, overlay=transition):
            left, top = round(overlay.x * 640), round(overlay.y * 480)
            width, height = round(overlay.width * 640), round(overlay.height * 480)
            return image.crop((left + 4, top + 4, left + width - 4, top + height - 4)).tobytes()

        start_alpha = fade_crop(actual_frames[0])
        fully_visible = fade_crop(actual_frames[sample_frames.index(round(fps * 0.20))])
        fading_out = fade_crop(actual_frames[-1])
        assert start_alpha != fully_visible
        assert fully_visible == fading_out

@pytest.mark.parametrize("value", [None, [], "invalid pointer"])
def test_current_preview_requires_a_json_object(tmp_path, value):
    import json

    from youtube_automation.production import render

    (tmp_path / "adaptive_preview.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        render.require_current_preview(tmp_path, {}, 1)


def test_encoder_source_recipe_ignores_comments_but_tracks_executable_changes(tmp_path, monkeypatch):
    from youtube_automation.production import render

    source = tmp_path / "encoder.py"
    source.write_bytes(b"BITRATE = 1\n")
    monkeypatch.setattr(render.video_encoder, "__file__", str(source))
    baseline = render.render_code_fingerprint()
    source.write_bytes(b"BITRATE = 1\r\n# harmless comment\r\n")
    assert render.render_code_fingerprint() == baseline
    source.write_bytes(b"BITRATE = 2\n")
    assert render.render_code_fingerprint() != baseline




def _encoder_runtime_fixture(tmp_path, monkeypatch, hardware_failure):
    import json
    from contextlib import nullcontext
    from types import SimpleNamespace

    from PIL import Image

    from youtube_automation.production import cli, flow, render, review
    from youtube_automation.production.contracts import fingerprint
    from youtube_automation.production.shots import EditorialPolicy, Overlay, ShotPlan
    from youtube_automation.video.runner import FakeMediaRunner, MediaProbeResult

    shot = fixture_shot(end_frame=30, overlays=[
        Overlay(kind="label", start_frame=0, end_frame=30, text="Visible copy")
    ])
    plan = ShotPlan(
        shots=[shot], brief_sha256="a" * 64, timeline_sha256="b" * 64,
        fps=30, total_frames=30,
        editorial_policy=EditorialPolicy(
            cadence="balanced", target_shot_seconds=5, max_shot_seconds=10,
            max_consecutive_framing=3, max_motion_fraction=0.5,
        ),
    )
    brief = SimpleNamespace(version=2, source_sha256="c" * 64)
    timeline = {"audio_file": "audio.wav"}
    plan.timeline_sha256 = fingerprint(timeline)
    (tmp_path / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    (tmp_path / "shot_plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"canonical audio")
    image = tmp_path / "asset.png"
    Image.new("RGB", (640, 360), "#304560").save(image)
    assets = {"asset": "d" * 64}
    config = {"OUTPUT_WIDTH": 640, "OUTPUT_HEIGHT": 360, "CPU_CRF": 17}

    runner = FakeMediaRunner(
        available_encoders={"h264_qsv", "libx264"},
        error_on_encoder={"h264_qsv"} if hardware_failure else None,
        default_total_frames=30,
        default_duration=1.0,
        default_width=640,
        default_height=360,
        default_fps=30.0,
        default_pix_fmt="yuv420p",
    )
    runner.register_probe(
        audio,
        MediaProbeResult(
            duration=1.0,
            total_frames=30,
            width=0,
            height=0,
            fps=30.0,
            pix_fmt="",
            color_range="tv",
            has_audio=True,
        ),
    )
    monkeypatch.setattr("youtube_automation.video.runner._DEFAULT_RUNNER", runner)

    monkeypatch.setattr(render, "render_code_fingerprint", lambda: "e" * 64)
    monkeypatch.setattr(render, "render_tool_version", lambda: "FFmpeg test build")
    monkeypatch.setattr("youtube_automation.video.compiler.load_video_config", lambda *_: dict(config))
    monkeypatch.setattr(review, "review_context", lambda _: (brief, plan))
    monkeypatch.setattr(cli, "_validated_plan", lambda _: (brief, plan, timeline))
    monkeypatch.setattr(review, "load_brief", lambda _: brief)
    monkeypatch.setattr(render, "load_brief", lambda _: brief)
    monkeypatch.setattr(review, "verify_generated_assets", lambda *_: None)
    monkeypatch.setattr(flow, "verify_generated_assets", lambda *_: None)
    monkeypatch.setattr(render, "verify_generated_assets", lambda *_: None)
    monkeypatch.setattr(render, "validate_plan", lambda *_: None)
    monkeypatch.setattr(review, "read_shot_receipt", lambda *_: {"sha256": assets["asset"]})
    monkeypatch.setattr(cli, "read_shot_receipt", lambda *_: {"sha256": assets["asset"]})
    monkeypatch.setattr(render, "read_shot_receipt", lambda *_: {"dimensions": [640, 360], "path": "asset.png", "sha256": assets["asset"]})
    monkeypatch.setattr(render, "read_receipt", lambda *_: {"sha256": assets["asset"]})
    monkeypatch.setattr(render, "asset_storage_id", lambda _: "asset")
    monkeypatch.setattr("youtube_automation.production.visual_gate.require_visual_audit", lambda *_, **__: None)
    monkeypatch.setattr(review, "publication_guard", nullcontext)
    monkeypatch.setattr(render, "publication_guard", nullcontext)

    def get_calls():
        return [
            cmd[cmd.index("-c:v") + 1]
            for cmd in runner.commands_run
            if "-c:v" in cmd and "null" not in cmd and "lavfi" not in cmd
        ]

    return plan, config, runner, get_calls, json


@pytest.mark.parametrize("hardware_failure", [False, True])
def test_encoder_runtime_execution_binds_hardware_and_cpu_fallback(tmp_path, monkeypatch, hardware_failure):
    from youtube_automation.production import cli, render, review

    plan, config, runner, get_calls, json = _encoder_runtime_fixture(tmp_path, monkeypatch, hardware_failure)
    render._render_plan(tmp_path, config, preview=True, runner=runner)
    pointer = json.loads((tmp_path / "adaptive_preview.json").read_text())
    expected = "libx264" if hardware_failure else "h264_qsv"
    execution = pointer["encoder_execution"]["clips"][0]["execution"]
    assert pointer["inputs"]["encoder_recipe"]["video_codec"] == "h264_qsv"
    assert execution["encoder_recipe"]["video_codec"] == expected
    assert execution["fallback_from"] == (pointer["inputs"]["encoder_recipe"] if hardware_failure else None)
    assert get_calls() == (["h264_qsv", "libx264", "libx264"] if hardware_failure else ["h264_qsv", "libx264"])
    assert cli._render_output_complete(tmp_path, preview=True, runner=runner)
    review.approve_review(tmp_path, "Human", runner=runner)
    before = len(get_calls())
    render._render_plan(tmp_path, config, preview=False, runner=runner)
    assert get_calls()[before:] == ["libx264"]  # Proven clip cache reused; assembly still encodes.
    assert cli._render_output_complete(tmp_path, preview=False, runner=runner)
    master = json.loads((tmp_path / "active_master.json").read_text())
    master["encoder_execution"]["clips"][0]["execution"]["encoder_recipe"] = {"video_codec": "unapproved"}
    (tmp_path / "active_master.json").write_text(json.dumps(master))
    assert not cli._render_output_complete(tmp_path, preview=False, runner=runner)
    render.require_current_preview(tmp_path, pointer["inputs"], plan.total_frames)


def test_encoder_runtime_rejects_wrong_cache_and_orphan_execution(tmp_path, monkeypatch):
    from youtube_automation.production import render

    plan, config, runner, get_calls, json = _encoder_runtime_fixture(tmp_path, monkeypatch, True)
    render._render_plan(tmp_path, config, preview=True, runner=runner)
    pointer = json.loads((tmp_path / "adaptive_preview.json").read_text())
    generation = pointer["generation"]
    work = tmp_path / "adaptive_renders" / generation
    active_clip = pointer["encoder_execution"]["clips"][0]
    matching_receipts = [
        candidate for candidate in work.rglob("clip_00000.json")
        if (data := json.loads(candidate.read_text()))["clip_sha256"] == active_clip["sha256"]
        and data["execution"] == active_clip["execution"]
    ]
    assert len(matching_receipts) == 1
    receipt_path = matching_receipts[0]
    cache = json.loads(receipt_path.read_text())
    cache["execution"]["fallback_from"] = None
    receipt_path.write_text(json.dumps(cache))
    before = len(get_calls())
    render._render_plan(tmp_path, config, preview=True, runner=runner)
    assert get_calls()[before:] == ["h264_qsv", "libx264", "libx264"]
    pointer = json.loads((tmp_path / "adaptive_preview.json").read_text())
    journal = render._render_journal_path(tmp_path, generation, True)
    bad = json.loads(json.dumps(pointer))
    bad["encoder_execution"]["clips"][0]["execution"]["fallback_from"] = None
    journal.write_text(json.dumps({"version": 1, "kind": "preview", "pointer": bad}))
    before_pointer = (tmp_path / "adaptive_preview.json").read_bytes()
    assert render._recover_render_publication(tmp_path, generation, pointer["inputs"], plan.total_frames, plan.fps, preview=True, runner=runner) is None
    assert (tmp_path / "adaptive_preview.json").read_bytes() == before_pointer
    assert journal.exists()
    journal.write_text(json.dumps({"version": 1, "kind": "preview", "pointer": pointer}))
    assert render._recover_render_publication(tmp_path, generation, pointer["inputs"], plan.total_frames, plan.fps, preview=True, runner=runner) == tmp_path / pointer["path"]
    bad["encoder_execution"]["assembly"]["crf"] = "99"
    (tmp_path / "adaptive_preview.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="encoder execution"):
        render.require_current_preview(tmp_path, pointer["inputs"], plan.total_frames)


@pytest.mark.parametrize("damage", ["missing", "malformed", "wrong_frame_count", "wrong_dimensions"])
def test_receipt_required_for_preview_approval_and_stage_completion(tmp_path, monkeypatch, damage):
    import json

    from youtube_automation.production import cli, render

    plan, _, pointer = _lineage_fixture(tmp_path, monkeypatch)
    artifact = tmp_path / pointer["path"]
    receipt = artifact.parent / ".compilation-receipts" / (pointer["sha256"] + ".json")
    if damage == "missing":
        receipt.unlink(missing_ok=True)
    else:
        receipt.parent.mkdir(exist_ok=True)
        if damage == "malformed":
            receipt.write_text("{", encoding="utf-8")
        else:
            data = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
            if damage == "wrong_dimensions":
                data["width"] = 2
            else:
                data["total_frames"] = 90
            receipt.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="[Rr]eceipt"):
        render.require_current_preview(tmp_path, pointer["inputs"], plan.total_frames)
    assert not cli._render_output_complete(tmp_path, preview=True)
