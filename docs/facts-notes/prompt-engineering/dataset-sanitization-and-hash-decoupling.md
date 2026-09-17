# Note: Dataset Sanitization and Collision Disambiguation

**Category:** Prompt Engineering & Dataset Hygiene  
**Date Logged:** 2026-09-16  
**Relevant Code Files:** `tools/sanitize_flow_dataset.py`, `tools/run_canary_benchmark.py`, `tests/unit/test_flow_dataset_sanitizer.py`, `youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/flow_prompts_socratic.json`, `youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/master_roadmap_socratic.jsonl`  
**Audit Reference:** Section 2.3 (Systemic Subject Collapse & Hash Collision Analysis), Section 4.4, Module 6B  

### 1. Core Rule in Plain English
When regenerating prompts and frames for long-form video production:
1. **Hash Collision Disambiguation**: Frames identified with identical visual hashes or duplicate subject matter (specifically Frames 16, 18, 20, 33, 34, 44, 49) must have their sequence metadata decoupled (`sequence_type = "STANDALONE"`, `total_frames_in_set = 1`), and their root and visual prompt subjects assigned unique, non-colliding entities and continuity IDs (`SUBJ_DISAMBIG_{idx:02d}`).
2. **Preset Summoning Decoupling**: Because `resolve_target_character()` checks root-level `item["subject"]` and `item["continuity_id"]`, disambiguated diagram frames must decouple root-level character IDs to prevent false Google Flow character preset chip summoning.
3. **Pervasive 2K Oversampling Injection**: Directives for 2K oversampling (`master 2K widescreen resolution (2560x1440 px), ultra-sharp stroke fidelity`) must be injected directly into `composition` and `composition_layout` (which are consumed by `flatten_visual_prompt_to_diffusion_text()`) as well as `camera_specifications`.
4. **Idempotence and Automated Recovery**: Regeneration runners must provide a `--force-overwrite` CLI parameter to bypass existing file checks when deliberate re-generation of colliding assets is requested.

### 2. The Failure Mode It Prevents
- **Subject Collapse & Visual Stagnation**: Progressive build sets sharing the same character preset generate visually indistinguishable assets across distinct audio arguments, causing viewer fatigue.
- **Accidental Preset Summoning**: If `item["subject"]` retains `CHARACTER_HOST_MAIN` while `vp["subject"]` describes a standalone diagram, browser automation erroneously summons character chips, ruining abstract infographics with unwanted host cartoons.
- **4K Upscaling Blur**: Generating source rasters at standard 1080p produces soft bicubic interpolation blur when pan-and-zoom kinematics are rendered on large 4K displays.
- **Stale Asset Skips**: Standard pipelines skip generation if a frame exists on disk, preventing targeted regeneration of corrupted or duplicate assets without manual file deletion.

### 3. Implementation Specification
Implemented in `tools/sanitize_flow_dataset.py`:
```python
COLLISION_DISAMBIGUATION_MAP: dict[int, dict[str, str]] = {
    16: {
        "subject": "stylized mathematical proportion wave curves",
        "action": "dissolving smoothly into abstract geometric ratio balance blocks on light limbo ground (#F8F8FA)",
        "visual_concept": "Stylized mathematical proportion wave curves dissolving smoothly into abstract geometric ratio balance blocks on light limbo ground (#F8F8FA). 1-2-3 shape hierarchy with razor-sharp shadow falloff, zero gradients.",
    },
    18: {
        "subject": "CHARACTER_SKEPTIC_ABO_HMEED",
        "action": "gesturing with inquisitive raised eyebrow beside a comparative split diagram showing a marked U-turn trajectory",
        "visual_concept": "Abo Hmeed gesturing with inquisitive raised eyebrow beside a comparative split diagram showing a marked U-turn trajectory on warm dark mahogany workbench (#2A2420).",
    },
    20: {
        "subject": "CHARACTER_CLERK_BUREAUCRAT",
        "action": "holding a heavy brass master key beside a locked archive cabinet placard on studio workbench (#2A2420)",
        "visual_concept": "The Science Bureaucrat holding a heavy brass master key beside a locked archive cabinet placard on studio workbench (#2A2420).",
    },
    33: {
        "subject": "oversized vector magnifying glass",
        "action": "inspecting a glowing quantum node linkage cluster resting on light limbo studio table (#F8F8FA)",
        "visual_concept": "An oversized vector magnifying glass inspecting a glowing quantum node linkage cluster resting on light limbo studio table (#F8F8FA).",
    },
    34: {
        "subject": "retro mathematical calculation ledger",
        "action": "open flat on studio drafting desk (#F8F8FA) with comparative calculation indicator meters",
        "visual_concept": "A retro mathematical calculation ledger open flat on studio drafting desk (#F8F8FA) with comparative calculation indicator meters.",
    },
    44: {
        "subject": "precision vector micrometer",
        "action": "measuring an exact microscopic tolerance gap marked with an energetic green checkmark (#00E676) on white studio substrate",
        "visual_concept": "A precision vector micrometer measuring an exact microscopic tolerance gap marked with an energetic green checkmark (#00E676) on white studio substrate.",
    },
    49: {
        "subject": "complex algebraic ratio balance blocks",
        "action": "displaying an illuminated vector bridge connecting cubic and linear proportion meters on light limbo ground (#F8F8FA)",
        "visual_concept": "Complex algebraic ratio balance blocks displaying an illuminated vector bridge connecting cubic and linear proportion meters on light limbo ground (#F8F8FA).",
    },
}
```

In `tools/run_canary_benchmark.py`:
```python
def run_canary_benchmark(
    run_dir: str,
    target_indices: list[int] = DEFAULT_CANARY_INDICES,
    output_dir: str | None = None,
    cdp_port: int = 9222,
    dry_run: bool = False,
    force_overwrite: bool = False,
) -> dict[str, Any]:
...
    if not force_overwrite and os.path.exists(save_image_path) and ...:
        print(f"\n[CANARY] Frame {idx} already exists and verified on disk: {save_image_path}")
    else:
        # Generate new asset via CDP loopback
```

### 4. Verification & Validation Evidence
1. **Unit Test Suite**: `tests/unit/test_flow_dataset_sanitizer.py` (4/4 tests PASS):
   - `test_sanitize_flow_item_disambiguation`: Verifies all 7 collision frames decouple sequence metadata and assign unique subjects/continuity IDs.
   - `test_sanitize_camera_and_safe_zones`: Verifies 24mm/perspective migration, 16:9 safe zone boundaries, and 2K oversampling injection.
   - `test_sfumato_and_negative_hygiene`: Verifies complete Sfumato abolition and parenthesis-safe negative prompt cleanup.
   - `test_idempotence_and_dataset_roundtrip`: Verifies repeated runs yield identical outputs with zero duplication.
2. **Full Unit Regression Gate**: 482/482 tests PASS in 41.56s (`python -m pytest tests/unit -v`).
3. **Scaffold Linter Gate**: 35/35 exercise files verified clean (`python tools/lint_exercises.py`).
4. **Dataset Execution**: `python tools/sanitize_flow_dataset.py` processed all 293 flow prompt frames and 293 roadmap entries on disk.
