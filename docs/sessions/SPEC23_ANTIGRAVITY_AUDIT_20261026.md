# Spec #23 Antigravity delivery audit — 2026-10-26

## Review basis

- User-approved baseline: `70213c1880ccdb0fc194b18202243c7835eab71d`. It is also current `HEAD`; the delivery itself is uncommitted and includes modified tracked files and new files. Therefore the reviewed change is the frozen working-tree scope in `.runtime/spec23_review_20261026T033201Z/BASELINE.json`, compared with that commit; `git diff 70213c1...HEAD` alone is empty and would miss it.
- The review covered Spec #23 and tickets #24–#30, the applicable current AGENTS/contracts, the scoped code and tests, and separate independent Standards and Spec reviews.
- Frozen source/test/ADR inputs remained byte-identical during final checks: all 27 before/after SHA-256 entries match. The exact snapshot and full scoped status are recorded in `.runtime/spec23_review_20261026T033201Z/`.
- Source tree was not modified by this audit.

## Standards

**4 findings. No code-smell findings were reported.**

- **[P1] Rendering dependency changes escape cache and approval lineage** — `src/youtube_automation/production/render.py:274`. `render_code_fingerprint()` hashes the old renderer files and encoder module, but not the new authoritative engine, filter graph, subtitles, journal, runner or schema modules. A rendering fix can leave prior cache and editorial approval identities current. This violates `production/AGENTS.md` lineage and approval rules. Include the actual rendering dependency closure and test invalidation.
- **[P1] Public compilation bypasses the encoder lease** — `src/youtube_automation/video/engine.py:82`. Public `VideoCompiler.compile()` and `compile_video()` can probe hardware and run FFmpeg without the installation-wide encoder lease required by `src/youtube_automation/AGENTS.md`. Enforce the lease at the public boundary and cover probes through verification.
- **[P1] Failed verification destroys the previous output** — `src/youtube_automation/video/engine.py:388`. Assembly unlinks and replaces an existing output before verifying the candidate. Preserve the old bytes until the pending file passes validation, then atomically promote it.
- **[P2] Hardware fallback deletes resumable evidence** — `src/youtube_automation/video/engine.py:283`. Removing the failed hardware work directory deletes successful clips, journal, sidecars and diagnostics. This conflicts with root `AGENTS.md` and `CONTRIBUTING.md` preservation and recovery rules. Retain the failed generation while writing CPU output separately.

## Spec

**5 findings.**

- **[P1] Audio is silently truncated while compilation reports success** — `src/youtube_automation/video/engine.py:382,410`. Spec #23 requires rejecting audio/video duration mismatch beyond one frame. Native FFmpeg 8.1.2 received a 2-second WAV and a 30-frame (1-second) span; it returned a 1-second video with a 0.96-second audio stream and `verified=True`. Check source audio duration and final stream durations.
- **[P1] The previous output is replaced before candidate verification** — `src/youtube_automation/video/engine.py:388`. Ticket #27 promises atomic resumable rendering. An injected 999-frame probe caused `CompilationError`, but the old sentinel output had already become a 1,024-byte candidate. Validate the pending artifact before atomic replacement.
- **[P1] Rendering changes can keep stale production approval valid** — `src/youtube_automation/production/render.py:274–281,323`. Ticket #29 requires preview scoring and editorial approval checks to remain intact. The fingerprint omits the new renderer implementation files; edits there do not change current render identity. Cover invalidation through the production seam.
- **[P2] Requested output target is not verified** — `src/youtube_automation/video/engine.py:410–426`. Spec #23 requires a verified compilation result. A fake probe reporting 640×480/yuv444p was accepted for a 128×72/yuv420p request. Check dimensions, pixel format, color range, FPS, frame count and duration before publication.
- **[P2] Supplied ASS subtitles are ignored** — `src/youtube_automation/video/compiler.py:2523–2527,2587`; `src/youtube_automation/video/engine.py:209–216`. The legacy request builder supplies an existing ASS path, but the engine does not consume it. A fake-runner compile completed with no ASS filter or generated subtitle graph. Implement or explicitly reject this input, and include its contents in generation identity.

## Verification and decision

- Focused compilation tests: **136 passed**.
- Full suite: **2,058 passed, 9 skipped**.
- `mypy --strict src/`: passed, 77 source files.
- `ruff check .`: passed.
- `python -m build --no-isolation --sdist --wheel`: passed; output contains wheel and sdist for 4.5.1. The build reported a license metadata deprecation warning.
- Final input hashes before and after the gates matched. Existing checks pass but do not cover the reproduced and statically confirmed failure boundaries above.
- Reproduction scripts: .runtime/spec23_review_20261026T033201Z/audit_probes.py and .runtime/spec23_review_20261026T033201Z/audit_more_probes.py. Probe outputs: .runtime/spec23_review_20261026T033201Z/probes/results.json, .runtime/spec23_review_20261026T033201Z/probes/additional-results.json and .runtime/spec23_review_20261026T033201Z/probes/real-duration-ffprobe.stdout.json. Gate commands, raw output and hashes are under .runtime/spec23_review_20261026T033201Z/verification/. FFmpeg/Python research: .runtime/spec23_review_20261026T033201Z/RESEARCH_RECEIPT.json.
- Tracker update is complete: Spec #23 and tickets #25–#29 are open with the audit findings posted and exact comments read back. Tickets #24 and #30 remain closed. Parent: https://github.com/Snoozer10/local-youtube-automation/issues/23#issuecomment-6407764525. Ticket comments: #25 https://github.com/Snoozer10/local-youtube-automation/issues/25#issuecomment-6407765640; #26 https://github.com/Snoozer10/local-youtube-automation/issues/26#issuecomment-6407766743; #27 https://github.com/Snoozer10/local-youtube-automation/issues/27#issuecomment-6407767823; #28 https://github.com/Snoozer10/local-youtube-automation/issues/28#issuecomment-6407768934; #29 https://github.com/Snoozer10/local-youtube-automation/issues/29#issuecomment-6407770203.

## Ownership and documentation

- No Antigravity attribution beyond the returned delivery was inferred.
- Root `AGENTS.md` and domain contracts were left unchanged because this review found implementation defects, not a changed ownership or durable project policy.
- QMD was left unchanged per prior user direction; its coverage was stale, so this audit used direct current reads.
