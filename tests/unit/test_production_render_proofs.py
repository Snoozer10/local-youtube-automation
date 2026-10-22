from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def _install_fake_run(
    tmp_path,
    monkeypatch,
    *,
    fail=False,
    omit_last=False,
    corrupt_png=False,
    wrong_dimensions=False,
):
    from youtube_automation.production import render_proofs as proofs

    shot_a = SimpleNamespace(
        shot_id="shot_a",
        asset_id="asset_a",
        start_frame=0,
        end_frame=20,
        motion="push",
        zoom=1.0,
        overlays=[SimpleNamespace(
            kind="timer",
            start_frame=2,
            end_frame=18,
            clock_start_frame=6,
            motion_to=(0.8, 0.8),
            motion_end_frame=7,
        )],
    )
    shot_b = SimpleNamespace(
        shot_id="shot_b",
        asset_id="asset_b",
        start_frame=20,
        end_frame=35,
        motion="hold",
        zoom=1.0,
        overlays=[SimpleNamespace(kind="cue", start_frame=2, end_frame=8, clock_start_frame=None)],
    )
    plan = SimpleNamespace(shots=[shot_a, shot_b], total_frames=35, fps=1)
    brief = SimpleNamespace(version=3)
    receipts = {
        "asset_a": {"path": "assets/a.png", "sha256": "a" * 64, "dimensions": [1920, 1080]},
        "asset_b": {"path": "assets/b.png", "sha256": "b" * 64, "dimensions": [1920, 1080]},
    }
    for path in (tmp_path / "assets/a.png", tmp_path / "assets/b.png"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG_HEADER + b"source")
    (tmp_path / "timeline.json").write_text(
        json.dumps({"audio_file": "audio.wav", "word_start_frame": 10, "cue_end_frame": 28}),
        encoding="utf-8",
    )
    (tmp_path / "shot_plan.json").write_text("{}", encoding="utf-8")
    (tmp_path / "audio.wav").write_bytes(b"wav")

    monkeypatch.setattr(proofs, "load_brief", lambda root: brief)
    monkeypatch.setattr(proofs.ShotPlan, "model_validate_json", classmethod(lambda cls, raw: plan))
    monkeypatch.setattr(proofs, "validate_plan", lambda *args: None)
    monkeypatch.setattr(proofs, "require_editorial_review", lambda *args: None)
    monkeypatch.setattr(proofs, "enforce_visual_budget", lambda *args: SimpleNamespace(max_images=4))
    monkeypatch.setattr(proofs, "verify_generated_assets", lambda *args: None)
    monkeypatch.setattr(proofs, "asset_storage_id", lambda shot: shot.asset_id)
    monkeypatch.setattr(proofs, "read_shot_receipt", lambda root, shot: receipts[shot.asset_id])
    monkeypatch.setattr(proofs, "_audio_duration", lambda path: 35.0)
    config_calls = []
    monkeypatch.setattr(proofs, "load_video_config", lambda path: config_calls.append(path) or {
        "OUTPUT_WIDTH": 1920,
        "OUTPUT_HEIGHT": 1080,
        "CPU_CRF": 17,
    })
    selected_recipe = {"video_codec": "h264_qsv", "encoder_args": ["-look_ahead", "0"]}
    monkeypatch.setattr(proofs, "current_render_inputs", lambda *args, **kwargs: {
        "renderer_version": 14,
        "tool": "ffmpeg-build-for-test",
        "encoder_recipe": selected_recipe,
        "plan": "plan-fingerprint",
    })
    monkeypatch.setattr(proofs, "fingerprint", lambda plan: "plan-fingerprint")
    camera_sizes = []

    def fake_camera_filter(*args, source_size=None):
        camera_sizes.append(source_size)
        return "null"

    monkeypatch.setattr(proofs, "camera_filter", fake_camera_filter)
    monkeypatch.setattr(proofs, "overlay_filter_recipe", lambda *args: SimpleNamespace(passes=(), filter_chain=lambda files: ""))
    monkeypatch.setattr(proofs, "_normalize_color_range_filter", lambda pixel_format: "format=yuv420p,setparams=range=tv")
    monkeypatch.setattr(proofs, "_pixel_format_for_encoder", lambda recipe: "yuv420p")

    lease = {"acquired": 0, "released": 0}

    @contextmanager
    def fake_lease(*args):
        lease["acquired"] += 1
        try:
            yield
        finally:
            lease["released"] += 1

    monkeypatch.setattr(proofs, "leased_resource", fake_lease)
    monkeypatch.setattr(proofs, "resource_database", lambda: tmp_path / "leases.sqlite")
    from youtube_automation.production import ledger

    publication_database = tmp_path.parent / (tmp_path.name + "-publication.sqlite3")
    monkeypatch.setattr(ledger, "resource_database", lambda: publication_database)

    def fake_run(args, cwd, log_path):
        assert "-/filter_complex" in args
        assert "-filter_complex_script" not in args
        graph_path = Path(args[args.index("-/filter_complex") + 1])
        assert graph_path.is_file()
        if fail:
            raise RuntimeError("synthetic FFmpeg failure")
        count = int(args[args.index("-frames:v") + 1])
        if omit_last:
            count -= 1
        pattern = Path(args[-1])
        for index in range(count):
            output_path = cwd / pattern.name.replace("%05d", f"{index:05d}")
            if corrupt_png:
                output_path.write_bytes(PNG_HEADER + b"corrupt payload")
            else:
                size = (1918, 1080) if wrong_dimensions else (1920, 1080)
                Image.new("RGB", size, color=(index % 255, 0, 0)).save(
                    output_path, format="PNG"
                )
        log_path.write_text("synthetic ffmpeg log", encoding="utf-8")

    monkeypatch.setattr(proofs, "_run_sample_command", fake_run)
    return proofs, lease, config_calls, selected_recipe, camera_sizes


def test_current_proofs_write_complete_run_contained_samples_and_leave_canonical_state(tmp_path, monkeypatch):
    proofs, lease, config_calls, selected_recipe, camera_sizes = _install_fake_run(tmp_path, monkeypatch)
    (tmp_path / "visual_audit.json").write_text('{"status":"stale"}', encoding="utf-8")
    canonical_before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    first = proofs.render_current_proofs(tmp_path)
    second = proofs.render_current_proofs(tmp_path)

    assert first != second
    assert first.is_relative_to(tmp_path / ".adaptive_diagnostics" / "render_proofs")
    assert second.is_relative_to(tmp_path / ".adaptive_diagnostics" / "render_proofs")
    assert config_calls == ["video_config.txt", "video_config.txt"]
    assert lease == {"acquired": 2, "released": 2}
    assert camera_sizes == [(1920, 1080)] * 4
    for output in (first, second):
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        expected = {
            (item["shot_id"], item["local_frame_index"], item["global_frame_index"])
            for item in manifest["expected_samples"]
        }
        actual = {
            (item["shot_id"], item["local_frame_index"], item["global_frame_index"])
            for item in manifest["samples"]
        }
        assert actual == expected
        assert {item["shot_id"] for item in manifest["samples"]} == {"shot_a", "shot_b"}
        assert any("word_start_frame_boundary_at" in item["reasons"] for item in manifest["samples"])
        assert any("timer_boundary" in item["reasons"] for item in manifest["samples"])
        assert any(
            item["shot_id"] == "shot_a"
            and item["local_frame_index"] == 4
            and "timer:overlay_motion_mid" in item["reasons"]
            for item in manifest["samples"]
        )
        assert any(
            item["shot_id"] == "shot_a"
            and item["local_frame_index"] == 7
            and "timer:overlay_motion_arrival" in item["reasons"]
            for item in manifest["samples"]
        )
        assert 7 != (20 // 2) and 7 != (20 - 1)
        assert any(
            item["shot_id"] == "shot_a"
            and item["local_frame_index"] == 8
            and "timer:overlay_motion_arrival_plus_one" in item["reasons"]
            for item in manifest["samples"]
        )
        assert any(
            item["shot_id"] == "shot_a"
            and item["local_frame_index"] == 12
            and "timer:overlay_motion_hold" in item["reasons"]
            for item in manifest["samples"]
        )
        assert manifest["selected_encoder_recipe"] == selected_recipe
        assert manifest["production_h264_encoder_executed"] is False
        assert manifest["full_moving_preview_proof"] is False
        assert manifest["encoding_or_pacing_approval"] is False
        assert manifest["visual_budget"]["counted_proof_frames_as_stills"] is False
        assert any("motion_arrival" in item["reasons"] for item in manifest["samples"])
        assert all((output / item["path"]).read_bytes().startswith(PNG_HEADER) for item in manifest["samples"])

    canonical_after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and ".adaptive_diagnostics" not in path.parts
    }
    assert canonical_after == canonical_before


def test_current_proofs_reject_missing_samples_without_success_manifest(tmp_path, monkeypatch):
    proofs, _, _, _, _ = _install_fake_run(tmp_path, monkeypatch, omit_last=True)
    with pytest.raises(RuntimeError, match="produced"):
        proofs.render_current_proofs(tmp_path)
    outputs = list((tmp_path / ".adaptive_diagnostics" / "render_proofs").iterdir())
    assert outputs
    assert not (outputs[0] / "manifest.json").exists()


@pytest.mark.parametrize("output_issue", ["corrupt", "wrong_dimensions"])
def test_current_proofs_reject_invalid_png_samples_before_manifest(
    tmp_path, monkeypatch, output_issue
):
    proofs, _, _, _, _ = _install_fake_run(
        tmp_path,
        monkeypatch,
        corrupt_png=output_issue == "corrupt",
        wrong_dimensions=output_issue == "wrong_dimensions",
    )
    with pytest.raises(RuntimeError, match="invalid PNG sample"):
        proofs.render_current_proofs(tmp_path)
    outputs = list((tmp_path / ".adaptive_diagnostics" / "render_proofs").iterdir())
    assert outputs
    assert not (outputs[0] / "manifest.json").exists()


def test_current_proofs_release_encoder_lease_after_render_failure(tmp_path, monkeypatch):
    proofs, lease, _, _, _ = _install_fake_run(tmp_path, monkeypatch, fail=True)
    with pytest.raises(RuntimeError, match="synthetic FFmpeg failure"):
        proofs.render_current_proofs(tmp_path)
    assert lease == {"acquired": 1, "released": 1}


def test_current_proofs_keep_two_runs_in_separate_diagnostic_roots(tmp_path, monkeypatch):
    first_run = tmp_path / "first"
    second_run = tmp_path / "second"
    first_run.mkdir()
    second_run.mkdir()
    proofs, _, _, _, _ = _install_fake_run(first_run, monkeypatch)
    first_output = proofs.render_current_proofs(first_run)
    _install_fake_run(second_run, monkeypatch)
    second_output = proofs.render_current_proofs(second_run)
    assert first_output.is_relative_to(first_run)
    assert second_output.is_relative_to(second_run)
    assert not second_output.is_relative_to(first_run)


def test_proof_output_rejects_symlinked_destination(tmp_path):
    from youtube_automation.production.render_proofs import _contained_path

    root = tmp_path.resolve()
    target = root / "real"
    target.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(ValueError, match="symlink"):
        _contained_path(root, link / "proofs")


def test_word_span_and_cue_seconds_become_canonical_frame_boundaries():
    from youtube_automation.production.render_proofs import _samples_for_shot, _timeline_boundaries

    boundaries = _timeline_boundaries(
        {
            "words": [{"start": 0.0, "end": 0.16}],
            "spans": [{"start": 0.16, "end": 0.5}],
            "cues": [{"start": 0.2, "end": 0.4}],
            "word_start_frame": 9,
            "cue_start_frame": 10,
            "metadata": {"score": 99, "duration": 12.5},
        },
        fps=30,
    )
    assert "words_start_seconds" in boundaries[0]
    assert "words_end_seconds" in boundaries[5]
    assert "spans_start_seconds" in boundaries[5]
    assert "cues_start_seconds" in boundaries[6]
    assert "word_start_frame" in boundaries[9]
    assert 99 not in boundaries and 375 not in boundaries

    shot = SimpleNamespace(
        shot_id="short", start_frame=0, end_frame=10, motion="hold", overlays=[]
    )
    samples = _samples_for_shot(shot, 30, boundaries)
    assert all(0 <= frame < 10 for frame in samples)
    assert "words_end_seconds_boundary_at" in samples[5]
    assert "cues_start_seconds_boundary_at" in samples[6]
    assert "cue_start_frame_boundary_pre" in samples[9]
    next_shot = SimpleNamespace(
        shot_id="next", start_frame=10, end_frame=20, motion="hold", overlays=[]
    )
    assert "cue_start_frame_boundary_at" in _samples_for_shot(next_shot, 30, boundaries)[0]


def test_current_inputs_use_real_default_recipe_storage_ids_and_fingerprint(tmp_path, monkeypatch):
    from youtube_automation.production import render
    from youtube_automation.production import render_proofs as proofs
    from youtube_automation.production.assets import asset_storage_id, file_digest
    from youtube_automation.production.contracts import fingerprint
    from youtube_automation.production.shots import EditorialPolicy, Shot, ShotPlan

    def shot(shot_id, asset_id, start, end, span):
        return Shot(
            shot_id=shot_id,
            scene_id=f"scene_{shot_id}",
            asset_id=asset_id,
            entity_ids=[f"entity_{shot_id}"],
            span_ids=[span],
            start_frame=start,
            end_frame=end,
            purpose="Explain the beat",
            treatment="subject_scene",
            subject="A person",
            visible_state="Looking at the evidence",
            setting="A simple studio",
            framing="medium",
            composition="Centered subject with clear negative space",
        )

    plan = ShotPlan(
        shots=[shot("real_a", "real_asset_a", 0, 20, 0), shot("real_b", "real_asset_b", 20, 35, 1)],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=1,
        total_frames=35,
        editorial_policy=EditorialPolicy(
            cadence="balanced",
            target_shot_seconds=5,
            max_shot_seconds=10,
            max_consecutive_framing=3,
            max_motion_fraction=0.5,
        ),
    )
    brief = SimpleNamespace(version=2)
    real_load_video_config = proofs.load_video_config

    default_config_path = Path("video_config.txt").resolve()
    test_config_path = tmp_path / "video_config.txt"
    test_config_path.write_bytes(
        default_config_path.read_bytes() + "\nOUTPUT_PROFILE=تجربة افتراضية\n".encode()
    )
    monkeypatch.chdir(tmp_path)
    config = real_load_video_config("video_config.txt")
    assert config["OUTPUT_PROFILE"] == "تجربة افتراضية"
    selected_encoder = {
        "video_codec": "libx264",
        "encoder_name": "libx264",
        "hwaccel": "none",
        "encoder_args": ["-crf", "17"],
    }
    receipts = {}
    for current_shot, color in zip(plan.shots, (b"a", b"b"), strict=True):
        asset_path = tmp_path / "assets" / f"{current_shot.shot_id}.png"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(PNG_HEADER + color)
        receipts[current_shot.asset_id] = {
            "path": asset_path.relative_to(tmp_path).as_posix(),
            "sha256": file_digest(asset_path),
            "dimensions": [config["OUTPUT_WIDTH"], config["OUTPUT_HEIGHT"]],
        }
    (tmp_path / "timeline.json").write_text(
        json.dumps({"audio_file": "audio.wav", "words": [{"start": 0.0, "end": 0.2}]}),
        encoding="utf-8",
    )
    (tmp_path / "shot_plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"real audio digest input")

    monkeypatch.setattr(proofs, "load_brief", lambda root: brief)
    monkeypatch.setattr(proofs, "validate_plan", lambda *args: None)
    monkeypatch.setattr(proofs, "enforce_visual_budget", lambda *args: SimpleNamespace(max_images=10))
    monkeypatch.setattr(proofs, "verify_generated_assets", lambda *args: None)
    monkeypatch.setattr(proofs, "read_shot_receipt", lambda root, current: receipts[current.asset_id])
    monkeypatch.setattr(proofs, "_audio_duration", lambda path: 35.0)
    detector_calls = []
    lease_state = {"held": False}

    @contextmanager
    def tracked_encoder_lease(*args):
        assert not lease_state["held"]
        lease_state["held"] = True
        try:
            yield
        finally:
            lease_state["held"] = False

    monkeypatch.setattr(proofs, "leased_resource", tracked_encoder_lease)
    def detect_default_encoder(current_config):
        assert lease_state["held"]
        detector_calls.append(dict(current_config))
        return dict(selected_encoder)

    monkeypatch.setattr(render, "detect_hardware_encoder", detect_default_encoder)
    monkeypatch.setattr(render, "render_tool_version", lambda: "ffmpeg-native-probe-faked")
    monkeypatch.setattr(proofs, "camera_filter", lambda *args, **kwargs: "null")
    monkeypatch.setattr(
        proofs,
        "overlay_filter_recipe",
        lambda *args: SimpleNamespace(passes=(), filter_chain=lambda files: ""),
    )
    monkeypatch.setattr(proofs, "_normalize_color_range_filter", lambda value: "format=yuv420p")
    monkeypatch.setattr(proofs, "_pixel_format_for_encoder", lambda recipe: "yuv420p")
    monkeypatch.setattr(proofs, "resource_database", lambda: tmp_path / "leases.sqlite")

    def fake_run(args, cwd, log_path):
        assert lease_state["held"]
        count = int(args[args.index("-frames:v") + 1])
        for index in range(count):
            Image.new("RGB", (1920, 1080), color=(index % 255, 0, 0)).save(
                cwd / f"frame_{index:05d}.png", format="PNG"
            )
        log_path.write_text("synthetic", encoding="utf-8")

    monkeypatch.setattr(proofs, "_run_sample_command", fake_run)
    output = proofs.render_current_proofs(tmp_path)
    assert lease_state["held"] is False
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    actual_inputs = manifest["current_render_inputs"]
    expected_assets = {
        asset_storage_id(current_shot): receipts[current_shot.asset_id]["sha256"]
        for current_shot in plan.shots
    }
    assert config["OUTPUT_PROFILE"] == actual_inputs["config"]["OUTPUT_PROFILE"]
    assert detector_calls[0]["OUTPUT_FPS"] == plan.fps
    assert actual_inputs["assets"] == expected_assets
    assert actual_inputs["audio"] == file_digest(audio)
    assert actual_inputs["config"] == dict(config, OUTPUT_FPS=plan.fps)
    assert actual_inputs["encoder_recipe"] == selected_encoder
    assert actual_inputs["plan"] == fingerprint(plan)
    assert manifest["current_render_inputs_sha256"] == fingerprint(actual_inputs)
    assert len(detector_calls) == 1
    assert output.name.startswith(fingerprint(selected_encoder)[:12])

    unicode_inputs = render.current_render_inputs(
        plan,
        expected_assets,
        audio,
        dict(config, OUTPUT_PROFILE="تجربة افتراضية"),
        encoder_config=selected_encoder,
    )
    assert unicode_inputs["config"]["OUTPUT_PROFILE"] == "تجربة افتراضية"
    default_json_digest = hashlib.sha256(
        json.dumps(unicode_inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert fingerprint(unicode_inputs) != default_json_digest


def test_proofs_cli_exits_before_stage_runner(tmp_path, monkeypatch, capsys):
    from youtube_automation.production import cli, render_proofs

    called = []
    monkeypatch.setattr(render_proofs, "render_current_proofs", lambda root: called.append(root) or tmp_path / "proofs")
    monkeypatch.setattr(cli, "_run_stage_attempt", lambda *args: pytest.fail("stage runner must not run"))
    cli.main(["proofs", "--run-dir", str(tmp_path)])
    assert called == [tmp_path.resolve()]
    assert "proofs" in capsys.readouterr().out


@pytest.mark.parametrize("stage", ["preview", "render"])
def test_normal_preview_and_master_cli_still_require_current_audit(tmp_path, monkeypatch, stage):
    from youtube_automation.production import cli, visual_gate

    (tmp_path / "visual_budget.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "_validated_plan", lambda root: (object(), object(), {}))
    monkeypatch.setattr(
        visual_gate,
        "require_visual_audit",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("audit is stale")),
    )
    monkeypatch.setattr(cli, "_run_stage_attempt", lambda *args: pytest.fail("stage runner must not run"))
    with pytest.raises(ValueError, match="audit is stale"):
        cli.main([stage, "--run-dir", str(tmp_path)])
