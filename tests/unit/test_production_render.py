from youtube_automation.production.render import camera_filter, overlay_ass
from youtube_automation.production.shots import SCHULTE_6X6, Overlay, Shot


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
    assert "\\clip(" in ass
    assert all(f"}}{number}\n" in ass or f"}}{number}\r\n" in ass for number in map(str, range(1, 37)))


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
    calls = []
    original_run = render.run_command

    def recorded_run(args, cwd, timeout=600):
        calls.append((args, Path(cwd)))
        return original_run(args, cwd, timeout)

    monkeypatch.setattr(render, "run_command", recorded_run)
    render_plan(tmp_path, config, preview=True)
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
    monkeypatch.setattr(
        render,
        "run_command",
        lambda *_args, **_kwargs: pytest.fail("verified orphan should activate without re-encoding"),
    )
    recovered = render_plan(tmp_path, dict(config, CPU_CRF=28), preview=True)
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
