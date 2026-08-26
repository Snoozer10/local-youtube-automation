# Resilient Gemini Automation & Generation Pipeline — Implementation Plan

> **For agentic workers:** Execute bottom-up. Each task lists interfaces later tasks consume. Verified against `docs/Prompts/Technical Implementation Plan Resilient Gemini Automation & Generation Pipeline.md` + 4 review rounds.

**Goal:** Replace monolithic/stateful Gemini-web planning in `flow_image_generator.py` with paged roadmaps, ephemeral stateless sessions, CDP-safe injection, multi-tier JSON repair, manifest checkpointing, and pre-render integrity gates — without touching Flow rendering logic.

## Global Constraints

- Windows-only, Python 3.10+, Playwright sync API over CDP `127.0.0.1:9222` (never `localhost`).
- Style: black `-l 100`, ruff `E,W,F,I,B,C4,UP`, mypy `--strict --ignore-missing-imports`. No inline comments.
- All disk writes atomic: `NamedTemporaryFile(dir=target_dir)` + `flush` + `os.fsync` + `os.replace`.
- UTF-8 everywhere (`encoding="utf-8"`); Arabic-safe.
- Flow rendering invariants untouchable: `FLOW_ASSET_PRESETS`, `setup_flow_characters_and_scenes`, `summon_asset_in_prompt`, `wait_for_flow_generation_handshake`, `extract_high_res_image` tiers, `FlowSelectors`, workspace resume, failover rotation.
- `script_image_generator.py` untouched.

## Locked Decisions

| ID | Decision |
|----|----------|
| D1 | `pydantic>=2.0.0` adopted |
| D2 | Legacy `master_roadmap.txt` auto-migrates to `.jsonl`; corrupt/mismatch ⇒ regenerate |
| D3 | Injection ladder: `keyboard.insert_text` → clipboard(grant_permissions)+Ctrl+V → `execCommand('insertText')` → `fill()` (<500 chars only) |
| D4 | Weak timestamp monotonicity: `TS[i] <= TS[i+1]`; equality ⇒ strict (`index`,`frame_index`) progression |
| D5 | M1 ephemeral sessions for roadmap pages AND planning chunks |
| D6 | M2 tri-factor: stop-absent + 3x-stability@500ms HARD; action-bar SOFT |
| D7 | M3 post-injection readback gate ≥95% length via `inner_text()` (never `input_value`) |
| D8 | M4 preamble built from injected `FLOW_ASSET_PRESETS` (no circular import) |
| D9 | `script_hash` = SHA256(transcript + prompt_template + asset_presets texts); mismatch ⇒ invalidate caches |
| D10 | Self-heal exhaustion ⇒ `ChunkStatus.FAILED`, dump `debug/malformed_chunk_{N}.json`, raise `ChunkPlanningError` |
| D11 | Anti-bot jitter `random.uniform(1.5, 3.0)`s between ephemeral sessions |

## Dependency DAG

```
pipeline_manifest ─┬─→ prompt_planner ─┐
json_sanitizer ────┤                   ├─→ flow_image_generator (rewire)
validator ─────────┘                   │
gemini_controller ←────────────────────┤
roadmap_orchestrator → gemini_controller
```

## Module Contracts

### pipeline_manifest.py
- `PhaseStatus(str,Enum)`: PENDING/IN_PROGRESS/COMPLETED/FAILED; `ChunkStatus(str,Enum)`: PENDING/VERIFIED/REPAIRED/FAILED
- `compute_script_hash(transcript_text, prompt_template_text, presets_text) -> str` (sha256, `\n\x00\n` separators)
- `PipelineManifest.load_or_create(folder, script_hash)`; `.save()` atomic; mutators: `mark_roadmap_page_complete`, `set_roadmap_status`, `get_chunk`, `set_chunk_status(chunk_id, indices, status, attempts)`, `record_rendered(index)`, `was_reset` flag on hash mismatch
- File: `youtube_runs/<Title>/pipeline_manifest.json`; schema per spec §3.1

### json_sanitizer.py
- `clean_and_repair_json(raw_text) -> list[dict]`; Tier1 direct parse → Tier2 unescaped-quote regex fix → Tier3 trailing-comma strip + bracket close → Tier4 brace-scanner object salvage (needs `index`+`visual_prompt`). Total failure ⇒ `ValueError`.

### gemini_controller.py
- `jitter_delay(lo=1.5, hi=3.0) -> float`
- `read_gemini_input_text(page) -> str` (inner_text only)
- `inject_prompt_via_cdp(page, text, fill_limit=500) -> bool` — ladder D3 + D7 readback gate
- `wait_for_gemini_turn_completion(page, timeout_s=180, stability_polls=3, poll_interval=0.5) -> str` — D6 factors; error-card ⇒ `""`; timeout ⇒ `TimeoutError`
- `reset_chat_session(page) -> bool` — SPA "+ New chat" click first, `goto(app)` fallback
- `open_ephemeral_session(page, target_model) -> bool` — reset + `select_gemini_model` pill verify + input-ready

### validator.py
- Pydantic v2: `SequenceMetadata`, `VisualPrompt` (subject_details/style_anchor required non-empty), `FrameItem` (index>0, `[MM:SS]`/`[HH:MM:SS]` ts)
- Receives relocated pure utils from fig: `purge_subtitle_phrases`, `enforce_arabic_in_prompt`, `flatten_visual_prompt_to_diffusion_text` (aliases remain in fig)
- `verify_pipeline_integrity(flow_prompts, expected_total) -> report`; auto-clean pass then `PipelineIntegrityError` w/ violations: index continuity `range(1,N+1)`, D4 monotonicity, subtitle/margin scan, Latin-typography ban on `text_overlay_arabic` (Arabic `\u0600-\u06FF` or `NONE`), style_anchor keywords (`3px`, vector, cel-shading)

### roadmap_orchestrator.py
- `RoadmapRow` dataclass (index,timestamp,script_line,sequence_type,layout,camera,visual_concept,color_text)
- `split_transcript_into_windows(sentences, window_size=25)`
- `parse_markdown_table_line(line) -> list[str]` (resilient pipe-splitter, skips `---`)
- `parse_roadmap_rows(md) -> list[RoadmapRow]`
- `build_page_prompt(window, start_idx, end_idx, anchor_row|None)` — spec §2.1 envelope
- `load_or_migrate_roadmap(folder, sentences, manifest)` — jsonl hit / legacy txt migrate / None
- `generate_master_roadmap(gemini_page, sentences, folder, manifest, window_size, planner_model, max_page_repairs=2)` — ephemeral pages, atomic rewrite jsonl+txt mirror per page, manifest updates

### prompt_planner.py
- `ChunkPlanningError(RuntimeError)`
- `extract_roadmap_slice(rows, start_idx, end_idx, buffer=1)`
- `build_compact_preamble(presets: dict) -> str` — STYLE_DNA/CHARACTERS/FORBIDDEN yaml-style
- `build_chunk_payload(preamble, slice_rows, script_lines) -> str` — single-turn, JSON schema contract embedded
- `plan_all_chunks(gemini_page, sentences, roadmap_rows, folder, manifest, chunk_size=15, planner_model, max_repair_attempts=2) -> list[dict]` — D5/D10/D11 loop; commits merged frames atomically to `flow_prompts.json`

### flow_image_generator.py rewiring (main() planning block only)
1. Compute D9 hash; load/create manifest (log reset)
2. Roadmap: migrate-or-generate
3. Planning: manifest-driven skip; else plan_all_chunks
4. Pre-render gate: `verify_pipeline_integrity(frames, len(sentences))`
5. `manifest.record_rendered(idx)` after successful image extraction
6. `localhost` → `127.0.0.1` (connect_over_cdp ×2)
7. Remove old ack handshake + monolithic template + full-roadmap injection

### Config
- `.env.example` += `ROADMAP_WINDOW_SIZE=25` (Stage 4A)

## Test Map

| File | Covers |
|------|--------|
| tests/unit/test_pipeline_manifest.py | roundtrip, atomic save, hash invalidation, enums |
| tests/unit/test_json_sanitizer.py | tiers 1-4 incl. spec quote case, garbage ⇒ ValueError |
| tests/unit/test_validator.py | continuity dup/gap, weak monotonicity, subtitle autoclean, Latin ban, kufic/NONE |
| tests/unit/test_roadmap_orchestrator.py | windowing edge (103⇒25×3+28? ⇒ [25,25,25,28]), parser variants, anchor text, migration paths |
| tests/unit/test_prompt_planner.py | slice buffer edges, payload assembly, exhaustion ⇒ ChunkPlanningError |
| tests/unit/test_gemini_controller.py | FakePage ladder escalation, readback rejection, tri-factor states, jitter bounds, SPA-first reset |

## Verification Gate

```powershell
python -m pytest tests/unit -v
ruff check . --fix ; ruff format .
black --check --line-length 100 .
mypy .
```
