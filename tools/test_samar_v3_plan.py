import json
from pathlib import Path

from tools.migrate_soldier_brief_v3 import migrate_brief
from youtube_automation.production.contracts import fingerprint
from youtube_automation.production.shots import (
    ShotPlan,
    narration_excerpt_for_frames,
    validate_plan,
)


def main() -> None:
    root = Path("youtube_runs/adaptive-soldiers-ledger-samar-original-20261009")
    brief_v3 = migrate_brief(root)
    t = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    p_dict = json.load(open(root / "shot_plan.json", encoding="utf-8"))
    p_dict["version"] = 3
    p_dict["brief_sha256"] = fingerprint(brief_v3)

    for shot in p_dict["shots"]:
        shot["narration_excerpt"] = narration_excerpt_for_frames(t, shot["start_frame"], shot["end_frame"])

    # Bind hook microbeats
    p_dict["shots"][0]["hook_beat_id"] = "c3_hook_problem"
    p_dict["shots"][0]["hook_function"] = "problem"

    p_dict["shots"][1]["hook_beat_id"] = "c3_hook_curiosity"
    p_dict["shots"][1]["hook_function"] = "curiosity"

    p_dict["shots"][2]["hook_beat_id"] = "c3_hook_promise"
    p_dict["shots"][2]["hook_function"] = "promise"

    p = ShotPlan.model_validate(p_dict)
    try:
        validate_plan(p, t, brief_v3)
        print("validate_plan for Samar v3 plan PASSED COMPLETELY!")
    except Exception:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
