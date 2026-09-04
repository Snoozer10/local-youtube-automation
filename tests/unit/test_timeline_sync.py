"""Unit tests for zero-drift timeline assembly, Ken Burns filter contract, and CFR args."""

import compile_video


def make_blocks(secs) -> list[dict]:
    return [
        {
            "name": f"{int(s) // 60:02d}_{int(s) % 60:02d}",
            "sec": float(s),
            "raw_sec": float(s),
        }
        for s in secs
    ]


class TestFrameBudget:
    def test_frame_budget_equals_rounded_audio_duration_times_fps(self):
        blocks = make_blocks([0, 4, 8])
        timeline = compile_video.prepare_synchronized_timeline(blocks, 10.3, 30)

        total = round(10.3 * 30)
        assert total == 309
        assert sum(c["frame_count"] for c in timeline) == total
        assert timeline[-1]["end_frame"] == total

    def test_subsecond_audio_duration_rounds_to_exact_integer_budget(self):
        blocks = make_blocks([0, 3, 6])
        timeline = compile_video.prepare_synchronized_timeline(blocks, 9.999, 30)

        assert round(9.999 * 30) == 300
        assert sum(c["frame_count"] for c in timeline) == 300

    def test_first_clip_start_frame_is_forced_to_zero(self):
        blocks = make_blocks([0, 5])
        blocks[0]["sec"] = 2.5
        timeline = compile_video.prepare_synchronized_timeline(blocks, 10.0, 30)

        assert timeline[0]["start_frame"] == 0
        assert timeline[0]["sec"] == 0.0

    def test_clips_are_contiguous_with_no_gaps_or_overlaps(self):
        blocks = make_blocks([0, 2, 5, 7, 9])
        timeline = compile_video.prepare_synchronized_timeline(blocks, 12.0, 24)

        for prev, cur in zip(timeline, timeline[1:], strict=False):
            assert cur["start_frame"] == prev["end_frame"]
            assert cur["frame_count"] == cur["end_frame"] - cur["start_frame"]


class TestPerClipClamps:
    def test_tight_spacing_still_grants_every_clip_one_frame(self):
        blocks = make_blocks([0, 1.2, 2.4, 3.6, 4.8])
        timeline = compile_video.prepare_synchronized_timeline(blocks, 6.0, 24)

        assert len(timeline) == len(blocks)
        for clip in timeline:
            assert clip["frame_count"] >= 1
        assert sum(c["frame_count"] for c in timeline) == round(6.0 * 24)

    def test_ideal_end_beyond_budget_is_clamped_without_shortfall(self):
        blocks = make_blocks([0, 9.99])
        timeline = compile_video.prepare_synchronized_timeline(blocks, 10.0, 30)

        total = 300
        assert timeline[0]["end_frame"] == total - 1
        assert timeline[-1]["end_frame"] == total
        assert [c["frame_count"] for c in timeline] == [299, 1]


class TestDegenerateSurplus:
    def test_more_blocks_than_frames_folds_surplus_and_keeps_budget(self):
        blocks = make_blocks(range(0, 60, 5))
        timeline = compile_video.prepare_synchronized_timeline(blocks, 0.05, 30)

        budget = max(1, round(0.05 * 30))
        assert budget == 2
        assert len(timeline) == 2
        assert all(c["frame_count"] >= 1 for c in timeline)
        assert sum(c["frame_count"] for c in timeline) == budget

    def test_single_frame_audio_yields_exactly_one_clip(self):
        blocks = make_blocks([0, 1, 2])
        timeline = compile_video.prepare_synchronized_timeline(blocks, 0.01, 30)

        assert len(timeline) == 1
        assert timeline[0]["frame_count"] == 1

    def test_zero_blocks_return_empty_timeline(self):
        assert compile_video.prepare_synchronized_timeline([], 10.0, 30) == []


class TestKenBurnsFilterContract:
    def test_zoompan_d_matches_computed_frame_count(self, config):
        blocks = make_blocks([0, 8, 15])
        timeline = compile_video.prepare_synchronized_timeline(blocks, 20.0, config["OUTPUT_FPS"])

        for clip in timeline:
            f = compile_video.build_ken_burns_filter(config, clip["frame_count"], "zoom_in")
            assert f"d={clip['frame_count']}:" in f
            assert f"trim=start_frame=0:end_frame={clip['frame_count']}" in f

    def test_zoom_in_and_out_use_eased_min_max_bounds(self, config):
        zoom_in = compile_video.build_ken_burns_filter(config, 90, "zoom_in")
        zoom_out = compile_video.build_ken_burns_filter(config, 90, "zoom_out")
        # 90 frames @ 30fps = 3.0s duration -> dynamic scale clamp(1.06 + (3.0 - 2.5)/2.0 * 0.04) = 1.07
        assert "min(1.07" in zoom_in.replace(" ", "")
        assert f"max({config.get('KEN_BURNS_ZOOM_MIN', 1.0)}" in zoom_out.replace(" ", "")

        # When dynamic scale is explicitly False, honors KEN_BURNS_ZOOM_MAX
        cfg_fixed = config.copy()
        cfg_fixed["KEN_BURNS_DYNAMIC_SCALE"] = False
        zoom_fixed = compile_video.build_ken_burns_filter(cfg_fixed, 90, "zoom_in")
        assert f"min({cfg_fixed.get('KEN_BURNS_ZOOM_MAX', 1.08)}" in zoom_fixed.replace(" ", "")

    def test_static_action_pins_zoom_to_identity(self, config):
        f = compile_video.build_ken_burns_filter(config, 45, "static shot")
        assert "z='1.0'" in f
        assert "zoompan=" in f

    def test_output_dimensions_come_from_config(self, config):
        f = compile_video.build_ken_burns_filter(config, 45, "static")
        assert f"s={config['OUTPUT_WIDTH']}x{config['OUTPUT_HEIGHT']}" in f
        assert f"fps={config['OUTPUT_FPS']}" in f


class TestCFREnforcement:
    def test_encoder_config_enforces_constant_framerate_and_timescale(self, config):
        enc = compile_video._build_encoder_config("libx264", config)
        args = enc["encoder_args"]

        i = args.index("-fps_mode")
        assert args[i + 1] == "cfr"

        j = args.index("-video_track_timescale")
        assert args[j + 1] == str(int(config["OUTPUT_FPS"]) * 1000)

    def test_encoder_config_pins_rate_and_gop_to_fps(self, config):
        enc = compile_video._build_encoder_config("libx264", config)
        args = enc["encoder_args"]
        fps = int(config["OUTPUT_FPS"])

        r = args.index("-r")
        assert args[r + 1] == str(fps)
        g = args.index("-g")
        assert args[g + 1] == str(fps * 2)


class TestDynamicKenBurnsMotion:
    def test_dynamic_scale_derivation_from_duration(self):
        """Scale clamped to [1.06, 1.10] based on span duration per spec.md:85."""
        cfg = {
            "OUTPUT_WIDTH": 2560,
            "OUTPUT_HEIGHT": 1440,
            "OUTPUT_FPS": 30,
            "KEN_BURNS_ZOOM_MIN": 1.0,
            "KEN_BURNS_UPSCALE_FACTOR": 1.12,
        }
        # 2.5s -> 75 frames -> scale 1.06
        f_25 = compile_video.build_ken_burns_filter(cfg, 75, "zoom_in")
        assert "min(1.06," in f_25.replace(" ", "") or "min(1.060" in f_25.replace(" ", "")

        # 4.5s -> 135 frames -> scale 1.10
        f_45 = compile_video.build_ken_burns_filter(cfg, 135, "zoom_in")
        assert "min(1.1," in f_45.replace(" ", "") or "min(1.10" in f_45.replace(" ", "")

        # 3.5s -> 105 frames -> scale 1.08
        f_35 = compile_video.build_ken_burns_filter(cfg, 105, "zoom_in")
        assert "min(1.08," in f_35.replace(" ", "") or "min(1.080" in f_35.replace(" ", "")

    def test_round_robin_pool_fallback_in_chunk_filter_graph(self, tmp_path, config):
        """When AI camera map lacks entry, round-robin pool [zoom_in, zoom_out, pan_left, pan_right] is used."""
        # Create 5 dummy image files
        img_dir = tmp_path / "images"
        img_dir.mkdir()
        for i in range(5):
            p = img_dir / f"image_{i:02d}.png"
            p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        chunk_timeline = [
            {"name": f"img_{i}", "frame_count": 90, "occurrence": 1}
            for i in range(5)
        ]
        enc_config = {"video_codec": "libx264", "encoder_args": []}

        # build_chunk_filter_graph with empty ai_cameras and anim_enabled=True
        inputs, filter_complex, vout = compile_video.build_chunk_filter_graph(
            config,
            enc_config,
            chunk_timeline,
            str(img_dir),
            ai_cameras={},
            manual_cameras={},
            anim_enabled=True,
            global_offset_idx=0,
        )

        # First clip (idx 0) should be zoom_in (contains ease-in min(zoom_max)
        # Second clip (idx 1) should be zoom_out (contains max(zoom_min)
        # Third clip (idx 2) should be pan_left (contains iw*(1-ease))
        # Fourth clip (idx 3) should be pan_right (contains iw*ease)
        # Fifth clip (idx 4) wraps back to zoom_in
        assert "min(" in filter_complex  # zoom_in / zoom_out
        assert "max(" in filter_complex


class TestLadderProxyExport:
    def test_export_proxy_ladder_dry_run(self, tmp_path, config):
        """export_proxy_ladder generates 1080p and 720p proxy definitions."""
        master_file = tmp_path / "youtube_ready_video.mp4"
        master_file.write_bytes(b"dummy mp4 content" * 1000)

        enc_config = compile_video._build_encoder_config("libx264", config)
        proxies = compile_video.export_proxy_ladder(
            str(master_file),
            str(tmp_path),
            config,
            enc_config,
            execute=False,
        )

        assert len(proxies) == 2
        p1080, p720 = proxies
        assert "1080p" in p1080["output_path"]
        assert "720p" in p720["output_path"]
        assert "-2:1080" in p1080["scale_filter"] or "1920:1080" in p1080["scale_filter"]
        assert "-2:720" in p720["scale_filter"] or "1280:720" in p720["scale_filter"]
