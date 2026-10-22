import json
from pathlib import Path


def main() -> None:
    root = Path("youtube_runs/adaptive-soldiers-ledger-samar-original-20261009")
    p_dict = json.load(open(root / "shot_plan.json", encoding="utf-8"))
    for i, s in enumerate(p_dict["shots"]):
        print(f"Shot {i+1} ({s['shot_id']}): mode={s.get('visual_mode')}, framing={s.get('framing')}, beat={s.get('beat_kind')}")

if __name__ == "__main__":
    main()
