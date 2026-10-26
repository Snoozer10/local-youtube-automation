"""Unified Video Compilation Engine.

Core orchestrator providing a deep, single-entrypoint interface for media
synthesis across preview and broadcast master profiles, conforming to ADR 0002
and ADR 0006.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..production.ledger import lease_database, owned_resource, publication_guard
from .encoder import EncoderConfig, _build_encoder_config, detect_hardware_encoder
from .filter_graph import build_span_filter_graph
from .journal import RenderJournal, compute_generation_fingerprint, get_file_sha256
from .runner import MediaExecutionError, MediaRunner, SubprocessMediaRunner
from .schema import (
    CompilationError,
    CompilationProfile,
    CompilationRequest,
    CompilationResult,
    CompilationTarget,
    DialogueCue,
)


class VideoCompiler:
    """Core video compilation engine orchestrating clip rendering and assembly."""

    def __init__(
        self,
        runner: MediaRunner | None = None,
        base_config: Mapping[str, Any] | None = None,



    ) -> None:
        self.runner: MediaRunner = (
            runner if runner is not None else SubprocessMediaRunner()
        )
        self.base_config: dict[str, Any] = dict(base_config or {})

    def resolve_target(self, request: CompilationRequest) -> CompilationTarget:
        """Resolve final compilation target dimensions and frame rates."""
        if request.target is not None:
            return request.target

        if request.profile == CompilationProfile.BROADCAST_MASTER:
            # ADR 0002: Broadcast master renders at 2560x1440@30fps
            return CompilationTarget(
                width=2560,
                height=1440,
                fps=30,
                pixel_format="nv12",
                color_range="tv",
            )

        # Default PREVIEW profile: 1920x1080@30fps CFR
        return CompilationTarget(
            width=1920,
            height=1080,
            fps=30,
            pixel_format="yuv420p",
            color_range="tv",
        )

    def detect_encoder(
        self,
        config: Mapping[str, Any],
        override: str | None = None,
    ) -> EncoderConfig:
        """Negotiate encoder with priority fallback chain (h264_qsv -> h264_nvenc -> libx264)."""
        with owned_resource(lease_database(), "encoder"):
            if override:
                return _build_encoder_config(override, config)
            return detect_hardware_encoder(config, runner=self.runner)

    def compile(self, request: CompilationRequest) -> CompilationResult:
        """Compile under one encoder claim, including probes and publication."""
        with owned_resource(lease_database(), "encoder"):
            return self._compile(request)

    def _compile(self, request: CompilationRequest) -> CompilationResult:
        request.validate()
        target = self.resolve_target(request)
        if target.color_range not in {"tv", "limited"} or target.pixel_format not in {"nv12", "yuv420p"}:
            raise CompilationError(
                f"Unsupported target: {target.pixel_format}/{target.color_range}; "
                "H.264 output requires yuv420p/tv (nv12 upload surfaces are supported)",
                stage="validation",
            )
        expected_frames = sum(span.duration_frames for span in request.spans)
        expected_duration = expected_frames / target.fps
        frame_tolerance = 1.0 / target.fps + 1e-6
        source_audio = self.runner.probe(request.audio_path, require_audio=True)
        audio_duration = (
            source_audio.audio_duration
            if source_audio.audio_duration is not None
            else source_audio.duration
        )
        if (
            not source_audio.has_audio
            or not math.isfinite(audio_duration)
            or audio_duration <= 0
            or abs(audio_duration - expected_duration) > frame_tolerance
        ):
            raise CompilationError(
                f"Audio duration mismatch: timeline {expected_duration:.6f}s, "
                f"audio {audio_duration:.6f}s",
                stage="validation",
            )

        render_config = dict(self.base_config)
        render_config.update(request.extra_config)
        render_config["OUTPUT_WIDTH"] = target.width
        render_config["OUTPUT_HEIGHT"] = target.height
        render_config["OUTPUT_FPS"] = target.fps

        encoder_override = request.encoder_override or render_config.get("ENCODER_FORCE")
        encoder: EncoderConfig
        if "ENCODER_CONFIG" in request.extra_config:
            raw_cfg = request.extra_config["ENCODER_CONFIG"]
            encoder = {
                "video_codec": str(raw_cfg["video_codec"]),
                "encoder_name": str(raw_cfg.get("encoder_name", raw_cfg["video_codec"])),
                "hwaccel": str(raw_cfg.get("hwaccel", "none")),
                "encoder_args": list(raw_cfg.get("encoder_args", [])),
            }
        else:
            encoder = self.detect_encoder(render_config, override=encoder_override)

        # Compute deterministic generation fingerprint
        generation_hash = compute_generation_fingerprint(
            request=request,
            target=target,
            encoder=encoder,
        )

        # Setup isolated scratch directory and journal
        journal_generation = str(request.extra_config.get("GENERATION_OVERRIDE", generation_hash))
        execution_validator = request.extra_config.get("EXECUTION_VALIDATOR")

        if request.work_dir is not None:
            base_work_dir = Path(request.work_dir)
            if (
                request.extra_config.get("EXACT_WORK_DIR", False)
                or base_work_dir.name == generation_hash
                or base_work_dir.name == journal_generation
                or (base_work_dir / "_render_journal.json").exists()
            ):
                work_dir = base_work_dir
            else:
                work_dir = base_work_dir / generation_hash
        else:
            base_work_dir = request.output_path.parent / ".compiler_scratch"
            work_dir = base_work_dir / generation_hash
        work_dir.mkdir(parents=True, exist_ok=True)

        journal = RenderJournal(
            work_dir=work_dir,
            generation=journal_generation,
            total_spans=len(request.spans),
            profile=request.profile.value,
            target=target,
            execution_validator=execution_validator,
        )

        clips: list[Path] = []
        fallback_occurred = False
        fallback_from: str | None = None
        current_encoder = encoder
        reused_clip_count = 0

        cpu_encoder: EncoderConfig | None = None
        cpu_validator = execution_validator
        if encoder["video_codec"] in {"h264_qsv", "h264_nvenc"}:
            if "CPU_FALLBACK_CONFIG" in request.extra_config:
                raw_cpu = request.extra_config["CPU_FALLBACK_CONFIG"]
                cpu_encoder = {
                    "video_codec": str(raw_cpu["video_codec"]),
                    "encoder_name": str(raw_cpu.get("encoder_name", raw_cpu["video_codec"])),
                    "hwaccel": str(raw_cpu.get("hwaccel", "none")),
                    "encoder_args": list(raw_cpu.get("encoder_args", [])),
                }
            else:
                cpu_encoder = _build_encoder_config("libx264", render_config)
            if cpu_encoder["video_codec"] != "libx264":
                raise CompilationError("CPU fallback must use libx264", stage="validation")
            expected_cpu = dict(cpu_encoder, encoder_args=list(cpu_encoder["encoder_args"]))
            expected_fallback = request.extra_config.get("FALLBACK_FROM_VALUE", encoder["video_codec"])

            def valid_cpu_execution(value: Any) -> bool:
                return (
                    isinstance(value, Mapping)
                    and value.get("encoder_recipe") == expected_cpu
                    and value.get("fallback_from") == expected_fallback
                    and (execution_validator is None or bool(execution_validator(value)))
                )

            cpu_validator = valid_cpu_execution
            override = request.extra_config.get("GENERATION_OVERRIDE")
            if isinstance(override, str) and override and callable(execution_validator):
                # Profiles label final renditions; identical resolved clip recipes
                # may share a proven production fallback. Derive only the two
                # known profile identities, never scan arbitrary cache folders.
                best_count = 0
                for cache_profile in CompilationProfile:
                    cache_hash = compute_generation_fingerprint(
                        request=replace(request, profile=cache_profile),
                        target=target,
                        encoder=cpu_encoder,
                    )
                    cache_dir = base_work_dir / cache_hash
                    if not cache_dir.is_dir():
                        continue
                    cache_journal = RenderJournal(
                        work_dir=cache_dir,
                        generation=override,
                        total_spans=len(request.spans),
                        profile=cache_profile.value,
                        target=target,
                        execution_validator=valid_cpu_execution,
                    )
                    valid_count = sum(
                        cache_journal.is_clip_valid(
                            index=index,
                            clip_path=cache_dir / f"clip_{index:05d}.mp4",
                            expected_asset_sha256=get_file_sha256(request.asset_paths[span.asset_id]),
                            expected_frames=span.duration_frames,
                        )
                        for index, span in enumerate(request.spans)
                    )
                    if valid_count > best_count:
                        best_count = valid_count
                        work_dir, journal, generation_hash = cache_dir, cache_journal, cache_hash
                        current_encoder = cpu_encoder
                        fallback_occurred = True
                        fallback_from = encoder["video_codec"]

        # Compile individual visual spans
        span_idx = 0
        while span_idx < len(request.spans):
            span = request.spans[span_idx]
            frames = span.duration_frames
            asset_path = request.asset_paths[span.asset_id]
            asset_sha = get_file_sha256(asset_path)
            clip_path = work_dir / f"clip_{span_idx:05d}.mp4"
            temp_clip_path = work_dir / f"clip_{span_idx:05d}.pending.mp4"

            # Check if clip is already compiled and verified in journal
            if journal.is_clip_valid(
                index=span_idx,
                clip_path=clip_path,
                expected_asset_sha256=asset_sha,
                expected_frames=frames,
            ):
                clips.append(clip_path)
                reused_clip_count += 1
                span_idx += 1
                continue

            # Slice dialogue cues for this span if request has dialogue_events
            span_dialogue = getattr(span, "dialogue_events", ()) or ()
            if not span_dialogue and request.dialogue_events:
                span_start = span.start_frame
                span_end = span.end_frame
                sliced_cues = []
                for ev in request.dialogue_events:
                    ev_start = int(
                        getattr(ev, "start_frame", 0)
                        if not isinstance(ev, Mapping)
                        else ev.get("start_frame", 0)
                    )
                    ev_end = int(
                        getattr(ev, "end_frame", 0)
                        if not isinstance(ev, Mapping)
                        else ev.get("end_frame", 0)
                    )
                    ev_text = str(
                        getattr(ev, "text", "")
                        if not isinstance(ev, Mapping)
                        else ev.get("text", "")
                    )
                    ev_style = str(
                        getattr(ev, "style", "Default")
                        if not isinstance(ev, Mapping)
                        else ev.get("style", "Default")
                    )
                    if ev_end > span_start and ev_start < span_end:
                        sliced_cues.append(
                            DialogueCue(
                                start_frame=max(0, ev_start - span_start),
                                end_frame=min(frames, ev_end - span_start),
                                text=ev_text,
                                style=ev_style,
                            )
                        )
                if sliced_cues:
                    span = replace(span, dialogue_events=tuple(sliced_cues))

            filter_res = build_span_filter_graph(
                span=span,
                target=target,
                encoder_config=current_encoder,
                work_dir=work_dir,
                source_size=span.metadata.get("source_size"),
                font=request.font,
                external_subtitles_path=request.subtitles_path,
            )
            cmd_args = [
                "-nostdin",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(asset_path),
                *filter_res.args,
                "-frames:v",
                str(frames),
                "-an",
                "-c:v",
                current_encoder["video_codec"],
                *current_encoder["encoder_args"],
                "-bsf:v",
                "h264_metadata=video_full_range_flag=0",
                str(temp_clip_path),
            ]

            try:
                self.runner.run_ffmpeg(cmd_args, cwd=work_dir)
                if temp_clip_path.exists():
                    clip_sha = get_file_sha256(temp_clip_path)
                    if clip_path.exists():
                        clip_path.unlink()
                    temp_clip_path.replace(clip_path)
                    fallback_from_val = (
                        request.extra_config.get("FALLBACK_FROM_VALUE", fallback_from)
                        if fallback_occurred
                        else None
                    )
                    clip_execution = {
                        "encoder_recipe": dict(
                            current_encoder,
                            encoder_args=list(current_encoder.get("encoder_args", [])),
                        ),
                        "fallback_from": fallback_from_val,
                    }
                    journal.record_clip(
                        index=span_idx,
                        shot_id=span.shot_id,
                        asset_id=span.asset_id,
                        asset_sha256=asset_sha,
                        duration_frames=frames,
                        clip_path=clip_path,
                        clip_sha256=clip_sha,
                        encoder=current_encoder["video_codec"],
                        fps=target.fps,
                        execution=clip_execution,
                    )
                clips.append(clip_path)
                span_idx += 1
            except (MediaExecutionError, RuntimeError) as exc:
                if temp_clip_path.exists():
                    try:
                        temp_clip_path.unlink()
                    except OSError:
                        pass

                # Automatic fallback from hardware encoder to software libx264
                if current_encoder["video_codec"] in {"h264_qsv", "h264_nvenc"}:
                    fallback_occurred = True
                    fallback_from = current_encoder["video_codec"]
                    assert cpu_encoder is not None
                    current_encoder = cpu_encoder
                    # Preserve the complete hardware generation and its evidence.
                    # Even an exact production work directory needs a distinct CPU
                    # generation so hardware clips cannot satisfy the CPU recipe.
                    generation_hash = compute_generation_fingerprint(
                        request=request,
                        target=target,
                        encoder=current_encoder,
                    )
                    journal_generation = str(request.extra_config.get("GENERATION_OVERRIDE", generation_hash))
                    work_dir = base_work_dir / generation_hash
                    work_dir.mkdir(parents=True, exist_ok=True)
                    journal = RenderJournal(
                        work_dir=work_dir,
                        generation=journal_generation,
                        total_spans=len(request.spans),
                        profile=request.profile.value,
                        target=target,
                        execution_validator=cpu_validator,
                    )
                    clips.clear()
                    reused_clip_count = 0
                    span_idx = 0
                    continue

                stderr_msg = exc.stderr if isinstance(exc, MediaExecutionError) else str(exc)
                cmd_list = exc.cmd if isinstance(exc, MediaExecutionError) else cmd_args
                ret_code = exc.returncode if isinstance(exc, MediaExecutionError) else 1
                raise CompilationError(
                    f"Clip {span_idx} compilation failed ({current_encoder['video_codec']}): {stderr_msg}",
                    stage="clip_encode",
                    clip_index=span_idx,
                    cmd=cmd_list,
                    returncode=ret_code,
                    stderr=stderr_msg,
                ) from exc

        # Assemble final video with audio stream
        concat_file = work_dir / "concat.txt"
        concat_lines = "".join(f"file '{clip.resolve().as_posix()}'\n" for clip in clips)
        concat_file.write_text(concat_lines, encoding="utf-8")

        temp_output = request.output_path.with_suffix(
            f".pending_{uuid.uuid4().hex[:8]}.mp4"
        )
        concat_args = [
            "-nostdin",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-i",
            str(request.audio_path),
            "-map",
            "0:v",
            "-map",
            "1:a",
            *(
                [
                    "-vf",
                    "scale=w=iw:h=ih:in_range=auto:out_range=tv,format=yuv420p,setparams=range=tv",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    str(render_config.get("CPU_CRF", 17)),
                    "-pix_fmt",
                    "yuv420p",
                    "-color_range",
                    "tv",
                    "-bsf:v",
                    "h264_metadata=video_full_range_flag=0",
                    "-r",
                    str(target.fps),
                    "-fps_mode",
                    "cfr",
                ]
                if render_config.get("ASSEMBLY_CODEC") == "libx264"
                else ["-c:v", "copy"]
            ),
            "-c:a",
            "aac",
            "-b:a",
            "320k",
            str(temp_output),
        ]

        try:
            self.runner.run_ffmpeg(concat_args)
            if not temp_output.is_file() or temp_output.stat().st_size == 0:
                raise CompilationError("Final video assembly produced no media", stage="assembly")
        except (MediaExecutionError, RuntimeError) as exc:
            if temp_output.exists():
                try:
                    temp_output.unlink()
                except OSError:
                    pass
            stderr_msg = exc.stderr if isinstance(exc, MediaExecutionError) else str(exc)
            cmd_list = exc.cmd if isinstance(exc, MediaExecutionError) else concat_args
            ret_code = exc.returncode if isinstance(exc, MediaExecutionError) else 1
            raise CompilationError(
                f"Final video assembly failed: {stderr_msg}",
                stage="assembly",
                cmd=cmd_list,
                returncode=ret_code,
                stderr=stderr_msg,
            ) from exc

        # Verify final compiled artifact
        probe = self.runner.probe(temp_output, require_audio=True)
        if abs(probe.total_frames - expected_frames) > 1:
            raise CompilationError(
                f"Frame count mismatch: expected {expected_frames}, got {probe.total_frames}",
                stage="verification",
            )
        if not math.isfinite(probe.fps) or abs(probe.fps - target.fps) > 1e-6:
            raise CompilationError(
                f"Frame rate mismatch: expected {target.fps}, got {probe.fps}",
                stage="verification",
            )
        if probe.color_range != "tv":
            raise CompilationError(
                f"Color range mismatch: expected 'tv', got '{probe.color_range}'",
                stage="verification",
            )
        if (probe.width, probe.height) != (target.width, target.height):
            raise CompilationError(
                f"Output dimensions mismatch: expected {target.width}x{target.height}, "
                f"got {probe.width}x{probe.height}",
                stage="verification",
            )
        # NV12 is the QSV input surface format; decoded H.264 is planar 4:2:0.
        expected_format = "yuv420p" if target.pixel_format == "nv12" else target.pixel_format
        if probe.pix_fmt != expected_format:
            raise CompilationError(
                f"Pixel format mismatch: expected {target.pixel_format}, got {probe.pix_fmt}",
                stage="verification",
            )
        if not probe.has_audio:
            raise CompilationError("Required audio stream missing", stage="verification")
        video_duration = probe.video_duration if probe.video_duration is not None else probe.duration
        encoded_audio_duration = probe.audio_duration if probe.audio_duration is not None else probe.duration
        for label, actual, expected in (
            ("Container", probe.duration, expected_duration),
            ("Video", video_duration, expected_duration),
            ("Audio", encoded_audio_duration, audio_duration),
        ):
            if not math.isfinite(actual) or actual <= 0 or abs(actual - expected) > frame_tolerance:
                raise CompilationError(
                    f"{label} duration mismatch: expected {expected:.6f}s, got {actual:.6f}s",
                    stage="verification",
                )

        # A rejected candidate remains available for diagnosis; the destination
        # changes only after all verification succeeds.
        sha256_hash = get_file_sha256(temp_output)
        with publication_guard():
            temp_output.replace(request.output_path)

        return CompilationResult(
            output_path=request.output_path,
            profile=request.profile,
            total_frames=probe.total_frames,
            fps=int(round(probe.fps)),
            duration=probe.duration,
            width=probe.width,
            height=probe.height,
            encoder_used=current_encoder["video_codec"],
            fallback_occurred=fallback_occurred,
            fallback_from=fallback_from,
            verified=True,
            sha256=sha256_hash,
            clip_count=len(clips),
            generation_hash=generation_hash,
            reused_clip_count=reused_clip_count,
            clip_executions=tuple(
                {
                    "index": entry.index,
                    "sha256": entry.clip_sha256,
                    "execution": entry.execution,
                }
                for entry in sorted(journal.entries.values(), key=lambda e: e.index)
            ),
        )


def compile_video(
    request: CompilationRequest,
    runner: MediaRunner | None = None,
    base_config: Mapping[str, Any] | None = None,
) -> CompilationResult:
    """Compile a video artifact from a declarative request."""
    compiler = VideoCompiler(runner=runner, base_config=base_config)
    return compiler.compile(request)


def detect_encoder(
    config: Mapping[str, Any],
    runner: MediaRunner | None = None,
    override: str | None = None,
) -> EncoderConfig:
    """Detect available encoder with priority fallback chain."""
    return VideoCompiler(runner=runner).detect_encoder(config, override=override)
