# AGY09 G6 Run Assembly Brief

ROOT = "C:/Users/Snoozer/Downloads/Antigravity/Youtube Automation 2/buckup/Version 4 before deepseek implementation plan/image_generation". Resolve every repository-relative path below against ROOT and quote all paths containing spaces. Read root AGENTS.md, GEMINI.md, HANDOFF.md and this brief before starting. Lead as coordinator with one bounded native implementer and one independent verifier;this scratch-only scope overrides generic HANDOFF/DOX/master closeout writes.

## Task Capsule

- **Task ID:** AGY09-G6-RUN-ASSEMBLY
- **Scope & ownership:** Antigravity 2.0 may assemble one offline, scratch-only D2 candidate under `.runtime/antigravity_offline_queue_20261013/AGY09_attempt01/`. Keep candidate artifacts in `run_candidate/`; logs, helpers, verifier output, return record, and seals stay within the same attempt root.
- **Goal & acceptance:** Produce a source-bound full-timeline and interval candidate with continuous coverage from time zero through the source end, including silence. Record measured gaps and uncertainty honestly. This is preparatory evidence only; do not promote it or close any production checkbox.
- **Guidance:** Follow this brief and current `GEMINI.md`/applicable `AGENTS.md` contracts. Do not broaden the task or infer missing content.

## Pinned Inputs

Before staging, hash each original, then copy into the attempt input area and verify the staged byte count and SHA-256 against these pins. Hash originals again after copying. Stop and preserve drift evidence if any comparison fails or an attempt directory already exists; do not overwrite or resume it.

| Input | Original | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Source audio | `C:/Users/Snoozer/Downloads/YouTube Stuff/Channels/Explainintions categories/Content/18 Done/Do These 7 Brain Exercises NOW & Watch Your Focus Explode/full_episode_voice.wav` | 24452138 | `967f539225482772a7f4c7e9571023c293d33ad9871ba10114841e8fe858b203` |
| Refined script | Same source folder, `refined_script.txt` | 10751 | `90134bd2ef690e50cec5c99ab323c06ab84ed25ee4b385a0f38bcf2307ec1488` |
| Subtitle proxy | Same source folder, `subtitle_chunks.srt` | 16075 | `02a0cc4b4e82c5f78ece4b74272d270a2366093c827383821c0d706d947cc74f` |
| AGY07 coverage proxy | `.runtime/antigravity_offline_queue_20261013/AGY07_attempt01/coverage.csv` | 56791 | `bd2e583cfc858d688f75a63047c167dd7e22170313c59d26cb3055b0ab8b4360` |
| AGY07 validation proxy | `.runtime/antigravity_offline_queue_20261013/AGY07_attempt01/coverage_validation.json` | 545 | `50b8dc3da8839b166eede4572be38c829b06243822bb779ab125bdb29bf1ffbc` |

The subtitle and AGY07 files are proxies, not authoritative ASR or listening evidence. Preserve their provenance and do not relabel them as verified transcription.

## Allowed Work

- Work only from staged, hash-verified copies and existing local evidence. No new model inference is authorized (`inference_cap=0`). If a reliable input is absent, mark the relevant result `PARTIAL` or `BLOCKED` and state why.
- Inspect the actual pure API signatures in `src/youtube_automation/timeline/engine.py` before use. Do not invent a CLI, call a persistence path, or let an API write outside this attempt root. Stop if scratch-only execution cannot be established.
- Produce candidate source, script, timeline and any required shims only when the real API supports them. Keep each artifact explicitly labeled candidate/unpromoted.
- Cover the complete source from `0` to the measured end, including silence. Intervals must preserve source spans, provenance, and uncertainty; do not fabricate words or endpoints to make coverage appear complete.
- At 30 fps, `round(509.418625 * 30) = 15283` frames. That is `509.433333...` seconds, about `14.708 ms` longer than the exact sample duration. Record this nearest-frame rounding; do not claim mathematical zero-duration discrepancy.
- Record word timing provenance in `word_timing_provenance.json`: distinguish aligner estimates from actual ASR anchors, identify which evidence supports each timing, and leave unsupported words/times uncertain. Audio fidelity remains `OPEN`; no listening occurred.
- Keep D1 and C7 dependencies `OPEN`. A complete candidate, validator output, or second-agent review does not close them.

## Prohibited Work

- No voice generation, DSP/mastering, GUI or browser action, provider/network call, rendering, canonical database or graph write, production promotion, or checkbox closure.
- No new episode model strategy or plan from mutable Canvas drafts.
- No fabricated `PASS`, listening, factual verification, OCR result, approved production brief, source-audio receipt, or successful production-stage receipt. Missing production CLI/run interfaces are an explicit gap.
- No Git mutations,commits,branch changes,source/test/project-doc edits,installs,downloads or tool reconfiguration. No writes, caches, temporary files, bytecode, or helpers outside the attempt root. Set `PYTHONDONTWRITEBYTECODE=1` and use `-B`; route temp/cache directories into the attempt root. Stop if containment cannot be guaranteed.

## Required Attempt Contents

- `INPUTS.json`: original/staged paths, sizes, hashes, copy verification, and before/after source hashes.
- `run_candidate/`: staged source/script and candidate timeline/interval artifacts; include only outputs actually produced by supported local APIs.
- `run_candidate/word_timing_provenance.json`, `intervals.csv` (source spans and uncertainty), and `validation.json` with explicit partial/open findings.
- `TASK_STATUS.json`: candidate-only status, D1/C7 still open, audio fidelity open, inference cap and actual count, and any blocked steps.
- Frozen helper source and SHA-256 captured before invocation; separate implementer and independent verifier scratch areas. The verifier must not modify candidate output.
- Raw invocation logs recording exact argv, cwd, relevant environment, stdout, stderr, exit code, and timestamps. Preserve failures and do not replace earlier evidence.
- `verification_report.md`, `RETURN.md`, `OUTPUT_MANIFEST.json`, and `SEAL.json`. The return must report gaps, non-runs, and failures without asserting production success.

## Evidence Closure

1. Check for an existing attempt directory; stop if present.
2. Hash and stage pinned inputs; verify source stability before and after copying.
3. Freeze and hash helpers before running them. Run one bounded implementer pass and one independent verifier pass in disjoint scratch locations; record exact commands and retain all raw logs.
4. The verifier checks hashes, interval ordering, source bounds, continuous `0..end` coverage including silence, frame arithmetic, provenance labels, uncertainty, and containment. It must not claim audio fidelity or human review.
5. The supervising parent must wait for every child/helper to exit and close stdout/stderr capture,including any sealer log. Never hash a still-open sealer log. Close all logs, candidate files, verifier output, and `RETURN.md` before generating `OUTPUT_MANIFEST.json`. Hash every closed payload in the manifest. Then seal the manifest and return record in `SEAL.json`; exclude `SEAL.json` from its own hash set.
6. Make no changes after sealing. If correction is needed, preserve the original attempt evidence and create an additive correction record; do not rewrite prior bytes or seals.

Stop on input drift, pre-existing attempt state, unsupported API, any out-of-root write, failed containment, missing reliable evidence, or failed verifier check. Return the scratch path and exact limitation; never repair by guessing.
