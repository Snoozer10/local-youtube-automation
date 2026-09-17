"""Dataset Sanitization and Collision Disambiguation Tool (Audit §2.3, §4.4, §6.2).

Performs batch normalization across production JSON/JSONL datasets:
1. Purges legacy regex mutations and unanchored replacements.
2. Eliminates 24mm camera lens distortion in favor of Orthographic 2D projection.
3. Purges MAD negative token conflicts and applies parenthesis-aware negative token hygiene.
4. Enforces 16:9 Widescreen Foveal Safe Envelope (X: 180-1740, Y: 90-980, 10% bleed padding).
5. Disambiguates repeated SHA-256 colliding frames (16, 18, 20, 33, 34, 44, 49).
6. Injects 2K master resolution oversampling directives (2560x1440 px).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from youtube_automation.prompts.prompt_enhancer import (
    neutralize_surfaces,
    purge_banned_visual_keywords,
    sanitize_negative_prompt,
)

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

OVERSAMPLING_2K_DIRECTIVE = "master 2K widescreen resolution (2560x1440 px), ultra-sharp stroke fidelity"


def sanitize_flow_item(item: dict) -> dict:
    """Normalizes a single FrameItem object in flow_prompts.json / flow_prompts_socratic.json."""
    idx = item.get("index", 0)
    vp = item.get("visual_prompt", {})

    # 1. Disambiguate colliding frames and decouple sequence metadata
    if idx in COLLISION_DISAMBIGUATION_MAP:
        disambig = COLLISION_DISAMBIGUATION_MAP[idx]
        vp["subject"] = disambig["subject"]
        vp["subject_details"] = disambig["subject"]
        vp["action"] = disambig["action"]
        vp["subject_action_increment"] = disambig["action"]
        item["sequence_type"] = "STANDALONE"
        if "subject" in item:
            item["subject"] = disambig["subject"]
        if "continuity_id" in item:
            item["continuity_id"] = f"SUBJ_DISAMBIG_{idx:02d}"
        vp["continuity_id"] = f"SUBJ_DISAMBIG_{idx:02d}"
        if "sequence_metadata" in item and isinstance(item["sequence_metadata"], dict):
            item["sequence_metadata"]["total_frames_in_set"] = 1
            item["sequence_metadata"]["frame_index"] = 1

    # 2. Sanitize surfaces and purge banned keywords
    for key in ("subject", "subject_details", "action", "subject_action_increment"):
        if key in vp and isinstance(vp[key], str):
            vp[key] = purge_banned_visual_keywords(neutralize_surfaces(vp[key]))
    if "subject" in item and isinstance(item["subject"], str):
        item["subject"] = purge_banned_visual_keywords(neutralize_surfaces(item["subject"]))

    # 3. Migrate camera model to Orthographic 2D & 16:9 safe zones
    for key in ("composition", "composition_layout"):
        if key in vp and isinstance(vp[key], str):
            comp = vp[key]
            comp = re.sub(
                r"\b24\s*mm(\s+wide[- ]angle)?(\s+lens|\s+optics|\s+framing)?\b|\bwide[- ]angle(\s+lens|\s+optics|\s+framing|\s+perspective)?\b|\bwide\s+angle(\s+perspective)?\b|\bfisheye(\s+lens)?\b",
                "orthographic flat 2D projection plane, zero barrel distortion",
                comp,
                flags=re.IGNORECASE,
            )
            if "coordinates X: 180 to 1740" not in comp:
                comp, count = re.subn(
                    r"clean centered 16:9 widescreen framing,?\s*",
                    "clean 16:9 widescreen composition strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 980, leaving 10% peripheral bleed padding, ",
                    comp,
                )
                if count == 0:
                    safe_env = "clean 16:9 widescreen composition strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 980, leaving 10% peripheral bleed padding"
                    comp = f"{comp}, {safe_env}".strip(", ")
            vp[key] = comp

    # 4. Abolish Sfumato in lighting
    if "lighting" in vp and isinstance(vp["lighting"], str):
        vp["lighting"] = re.sub(
            r"Da Vinci Sfumato(\s+(inspired tone separation|chiaroscuro(\s+lighting)?|chiaroscuro))?",
            "razor-sharp shadow falloff, zero gradients",
            vp["lighting"],
            flags=re.IGNORECASE,
        )

    # 5. Cleanse negative prompt of MAD contradictions
    user_neg = vp.get("negative_prompt", "")
    vp["negative_prompt"] = sanitize_negative_prompt(user_neg)

    # 6. Inject 2K oversampling directive into composition and camera_specifications
    for comp_key in ("composition", "composition_layout"):
        if comp_key in vp and isinstance(vp[comp_key], str):
            if OVERSAMPLING_2K_DIRECTIVE not in vp[comp_key]:
                vp[comp_key] = f"{vp[comp_key]}, {OVERSAMPLING_2K_DIRECTIVE}".strip(", ")

    cam_specs = vp.get("camera_specifications", "")
    if isinstance(cam_specs, str) and OVERSAMPLING_2K_DIRECTIVE not in cam_specs:
        vp["camera_specifications"] = f"{cam_specs}, {OVERSAMPLING_2K_DIRECTIVE}".strip(", ")
    elif not cam_specs:
        vp["camera_specifications"] = OVERSAMPLING_2K_DIRECTIVE

    item["visual_prompt"] = vp
    return item


def sanitize_roadmap_item(item: dict) -> dict:
    """Normalizes a single roadmap entry in master_roadmap_socratic.jsonl."""
    idx = item.get("index", 0)
    vc = item.get("visual_concept", "")

    # 1. Disambiguate colliding frames
    if idx in COLLISION_DISAMBIGUATION_MAP:
        vc = COLLISION_DISAMBIGUATION_MAP[idx]["visual_concept"]

    # 2. Sanitize surfaces and keywords
    vc = purge_banned_visual_keywords(neutralize_surfaces(vc))

    # 3. Abolish Sfumato
    vc = re.sub(
        r"Da Vinci Sfumato(\s+(inspired tone separation|chiaroscuro(\s+lighting)?|chiaroscuro))?",
        "razor-sharp shadow falloff, zero gradients",
        vc,
        flags=re.IGNORECASE,
    )

    # 4. Camera optics
    vc = re.sub(
        r"\b24\s*mm(\s+wide[- ]angle)?(\s+lens|\s+optics|\s+framing)?\b|\bwide[- ]angle(\s+lens|\s+optics|\s+framing|\s+perspective)?\b|\bwide\s+angle(\s+perspective)?\b|\bfisheye(\s+lens)?\b",
        "orthographic flat 2D projection plane",
        vc,
        flags=re.IGNORECASE,
    )

    item["visual_concept"] = vc
    return item


def sanitize_flow_dataset(
    flow_json_path: str,
    roadmap_jsonl_path: str,
    out_flow_path: str | None = None,
    out_roadmap_path: str | None = None,
) -> tuple[int, int]:
    """Batch sanitizes flow JSON and roadmap JSONL datasets."""
    out_flow_path = out_flow_path or flow_json_path
    out_roadmap_path = out_roadmap_path or roadmap_jsonl_path

    flow_count = 0
    if os.path.exists(flow_json_path):
        with open(flow_json_path, "r", encoding="utf-8") as f:
            flow_data = json.load(f)
        sanitized_flow = [sanitize_flow_item(item) for item in flow_data]
        tmp_flow = out_flow_path + ".tmp"
        with open(tmp_flow, "w", encoding="utf-8") as f:
            json.dump(sanitized_flow, f, indent=2, ensure_ascii=False)
        os.replace(tmp_flow, out_flow_path)
        flow_count = len(sanitized_flow)

    roadmap_count = 0
    if os.path.exists(roadmap_jsonl_path):
        with open(roadmap_jsonl_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        sanitized_roadmap = [sanitize_roadmap_item(item) for item in lines]
        tmp_road = out_roadmap_path + ".tmp"
        with open(tmp_road, "w", encoding="utf-8") as f:
            for item in sanitized_roadmap:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        os.replace(tmp_road, out_roadmap_path)
        roadmap_count = len(sanitized_roadmap)

    return flow_count, roadmap_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Sanitize Flow and Roadmap Socratic Datasets")
    parser.add_argument(
        "--flow-json",
        default="youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/flow_prompts_socratic.json",
    )
    parser.add_argument(
        "--roadmap-jsonl",
        default="youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/master_roadmap_socratic.jsonl",
    )
    parser.add_argument("--out-flow", default=None)
    parser.add_argument("--out-roadmap", default=None)
    args = parser.parse_args()

    print(f"[SANITIZER] Sanitizing datasets:\n  Flow: {args.flow_json}\n  Roadmap: {args.roadmap_jsonl}")
    fc, rc = sanitize_flow_dataset(args.flow_json, args.roadmap_jsonl, args.out_flow, args.out_roadmap)
    print(f"[SANITIZER] Completed successfully: {fc} flow frames and {rc} roadmap rows sanitized.")


if __name__ == "__main__":
    main()
