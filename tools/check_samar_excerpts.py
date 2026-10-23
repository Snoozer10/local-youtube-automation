import json
from pathlib import Path

from youtube_automation.production.shots import _normalize_excerpt, narration_excerpt_for_frames


def main() -> None:
    root = Path("youtube_runs/adaptive-soldiers-ledger-samar-original-20261009")
    t = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    p_dict = json.load(open(root / "shot_plan.json", encoding="utf-8"))
    for shot in p_dict["shots"]:
        expected = narration_excerpt_for_frames(t, shot["start_frame"], shot["end_frame"])
        actual = shot.get("narration_excerpt", "")
        if _normalize_excerpt(actual) != _normalize_excerpt(expected):
            print(f"{shot['shot_id']}: expected '{expected}' vs actual '{actual}'")

if __name__ == "__main__":
    main()
