# 0006: Unified Video Compilation Engine (Ports & Adapters + Deep Module)

Video compilation logic was fragmented and duplicated across two parallel subsystems: `src/youtube_automation/video/compiler.py` (2,055 LOC) and `src/youtube_automation/production/render.py` (1,117 LOC). Both maintained independent FFmpeg subprocess loops, hardware encoder probing, filtergraph script generation, color range normalizations, and `ffprobe` verifications. Furthermore, `test_production_render.py` required 12 brittle monkeypatches of private internal functions. We consolidate the entire media synthesis subsystem into a single deep module inside `src/youtube_automation/video/` behind an explicit Ports & Adapters execution seam.

## Decision

- **Canonical Module Location (`video/`)**: All physical video compilation, clip assembly, filtergraph building, and media verification logic lives canonically in `src/youtube_automation/video/`. The `production/` package is relieved of all raw encoder mechanics, focusing strictly on channel identity, editorial briefs, visual budgeting, and signing `active_master.json` receipts.
- **Unified Interface Contract (`compile_video`)**: The module presents a single, declarative entrypoint:
  `compile_video(request: CompilationRequest, runner: MediaRunner | None = None) -> CompilationResult`
  accepting an in-memory `CompilationRequest` (spans, audio path, asset mapping, overlays, and `CompilationProfile`) decoupled from ambient filesystem paths.
- **Two Adapters at the Execution Seam (Ports & Adapters)**: External tool interactions (`ffmpeg`, `ffprobe`) are governed by the `MediaRunner` protocol.
  - `SubprocessMediaRunner`: Production adapter handling Windows process arguments, UTF-8 line buffering, and TV color range flags.
  - `FakeMediaRunner`: Test adapter simulating deterministic clip outputs and frame metadata in-memory without spawning OS processes or requiring host GPU drivers.
- **Unified Mode Handling**: Fast preview compilation (CFR 30fps single-pass) and broadcast master compilation (multi-rendition 1440p/1080p ladder per ADR 0002) are parameterized as `CompilationProfile.PREVIEW` and `CompilationProfile.BROADCAST_MASTER` within the same engine, guaranteeing strictly identical Ken Burns kinematics, duration scaling, and color formatting.
- **Internal Seam Hiding**: `filter_graph.py`, `ken_burns.py`, `encoder.py`, and `subtitles.py` are strictly private implementation modules. External callers interact exclusively through `VideoCompiler` and `compile_video`.
- **Unified Resumable Checkpoint Journal**: Standardizes on an atomic, content-addressed clip journal (`<work_dir>/<generation_hash>/_render_journal.json` + `clip_{index:05d}.mp4`) recording clip index, asset SHA-256, duration, and output artifact hash for zero-redundant-re-encode resumption across all production paths.
- **Consolidated Overlay Engine**: ASS subtitle generation and graphic visual copy (Schulte matrices, timer events, text cues) are unified into `video/subtitles.py` and composed in a single filtergraph pass.
- **Backward-Compatible Facades**: Root CLI `compile_video.py` and `production/render.py` are preserved as thin adapters translating legacy CLI arguments and run directories into the in-memory request object.

## Considered Options

- **Retaining Parallel Subprocess Loops in `production/render.py`**: Rejected; maintaining dual FFmpeg invocations resulted in constant regression churn, divergent color range handling, and doubled maintenance overhead.
- **Single Subprocess Implementation Without Adapter Port**: Rejected; testing without an execution seam required 12 fragile monkeypatches across test files and made tests dependent on host FFmpeg installations.
- **Exposing Internal Filtergraph Builders to Callers**: Rejected; exposing filtergraph construction leaks private implementation details across the seam and violates module depth.

## Consequences

- **Locality**: All encoding, filtergraph generation, and hardware fallback bugs concentrate in `src/youtube_automation/video/`.
- **Leverage**: Callers pass declarative in-memory contracts; one compilation interface serves broadcast master, review preview, and test runners.
- **Testing**: Eliminates fragile monkeypatches in `test_production_render.py`. Unit tests exercise the full compilation lifecycle against `FakeMediaRunner`.
- **Phased Migration**: Implemented in two verified stages: (1) author deep module, adapters, and interface tests; (2) rewire callers and convert `production/render.py` and `compile_video.py` into thin delegation shims.

Status: accepted
