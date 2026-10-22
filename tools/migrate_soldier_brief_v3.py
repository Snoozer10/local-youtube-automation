"""Migrate Soldier Samar episode brief to schema version 3."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure src is on sys.path
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from youtube_automation.core.utils import atomic_write_json  # noqa: E402
from youtube_automation.production.contracts import (  # noqa: E402
    Analysis,
    Brief,
    Channel,
    EpisodeVisualStrategy,
    HookMicrobeat,
    fingerprint,
    load_brief,
)


def migrate_brief(run_dir: Path) -> Brief:
    raw_path = run_dir / "raw_transcript.txt"
    raw = raw_path.read_text(encoding="utf-8-sig")
    raw_hash = fingerprint(raw)

    channel = Channel(
        version=3,
        channel_id="soldiers-ledger",
        name="The Soldier's Sledger",
        audience="Viewers of military history who value machines, tactics, human stakes, and clear distinctions between documented fact and dramatization",
        language="English",
        dialect="Measured international English documentary narration for this English-language pilot; the channel also publishes Arabic episodes",
        asr_language="en",
        voice="Charon",
        tone="Tense and cinematic without sensationalizing casualties or asserting disputed details as settled fact",
        style="Historically disciplined illustrated documentary: archival-paper grain, restrained olive, slate, bone and signal-red palette, plausible period uniforms and equipment, geographic orientation, maps and mechanical cutaways only when the script needs them. Separate source-backed facts from illustrative reconstruction; use local labels and map annotations. Avoid fake archive photographs, invented insignia, decorative HUDs, and generic battlefield explosions.",
        visual_directives=[
            "Ground naval engagements in documented historical coordinates, ship identities, and tactical formations",
            "Separate source-backed facts from illustrative reconstruction; use local labels and map annotations",
            "Render technical cutaways, tactical maps, and mechanical weapon systems only when the narration specifically requires them",
            "Maintain archival-paper grain and restrained olive, slate, bone and signal-red palette",
            "Never use fake archive photographs, invented insignia, decorative HUDs, or generic battlefield explosions",
            "Depict naval surface actions with plausible weather squalls, smoke screens, and period equipment",
        ],
        forbidden_motifs=[
            "fake archive photograph",
            "invented insignia",
            "decorative HUD",
            "generic battlefield explosion",
            "speculative dramatization",
            "floating icon",
            "neon grid",
            "white isolation",
            "presenter holding a board",
        ],
        forbidden_visual_families=[
            "false_authority",
            "generic_desk_task",
            "mechanical_cognition",
        ],
        repetition_limited_visual_families=[],
        max_visual_family_repetitions=3,
        max_non_diagram_scene_appearances=None,
        host_mode="NONE",
        host_description="",
        allowed_treatments=[
            "subject_scene",
            "detail",
            "mechanism",
            "comparison",
            "timeline_map",
        ],
        humor="none",
        max_zoom=1.05,
    )

    existing_brief = json.loads(
        (run_dir / "episode_brief.json").read_text(encoding="utf-8")
    )
    analysis = Analysis.model_validate(existing_brief["analysis"])

    strategy = EpisodeVisualStrategy(
        version=1,
        source_sha256=raw_hash,
        topic="Battle off Samar destroyer escort defense",
        viewer_question="How did outmatched escort carriers and small screening escorts turn back the Japanese Center Force off Samar?",
        central_promise="Battle off Samar destroyer escort defense",
        evidence_mode="explanatory",
        emotional_arc=[
            "Tense tactical surprise off Samar",
            "Desperate defensive destroyer smoke screens and torpedo runs",
            "Analytical clarification of Kurita recall decision",
        ],
        hook_archetype="mystery_gap",
        hook_microbeats=[
            HookMicrobeat(
                beat_id="c3_hook_problem",
                function="problem",
                duration_seconds=3.0,
                viewer_takeaway="A massive Japanese battle line bears down on the vulnerable Leyte landing beaches",
                visual_mode="timeline",
                local_ui=["highlight"],
            ),
            HookMicrobeat(
                beat_id="c3_hook_curiosity",
                function="curiosity",
                duration_seconds=4.0,
                viewer_takeaway="Outmatched escort carriers and screening escorts confront Yamato and heavy cruisers",
                visual_mode="environmental_detail",
                local_ui=["focus_sweep"],
            ),
            HookMicrobeat(
                beat_id="c3_hook_promise",
                function="promise",
                duration_seconds=4.0,
                viewer_takeaway="Battle off Samar destroyer escort defense and tactical decisions that prompted recall",
                visual_mode="comparison",
                local_ui=["cards"],
            ),
        ],
        visual_modes=["timeline", "environmental_detail", "mechanism", "comparison"],
        local_ui_kit=["cards", "highlight", "focus_sweep", "trace_path"],
        pacing="Deliberate, tense documentary pacing matching chronological naval engagement timestamps and tactical maneuvers",
        motion_grammar=[
            "Slow methodical pan across naval battle lines and tactical maps",
            "Subtle push-in on key command decisions and ship positions",
        ],
        max_consecutive_visual_mode=3,
        max_repeated_composition=2,
        characters=[],
    )

    brief_v3 = Brief(
        version=3,
        source_sha256=raw_hash,
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=analysis,
        visual_strategy=strategy,
    )

    atomic_write_json(
        str(run_dir / "episode_brief.json"), brief_v3.model_dump(mode="json")
    )
    return brief_v3


if __name__ == "__main__":
    target_dir = Path("youtube_runs/adaptive-soldiers-ledger-samar-original-20261009")
    b = migrate_brief(target_dir)
    loaded = load_brief(target_dir)
    print("Migration successful!")
    print("Brief version:", loaded.version)
    print("Brief v3 valid:", loaded.version == 3)
