import json
from pathlib import Path


def main() -> None:
    root = Path("youtube_runs/adaptive-soldiers-ledger-samar-original-20261009")
    p = json.load(open(root / "shot_plan.json", encoding="utf-8"))
    for i, s in enumerate(p["shots"]):
        start_s = s["start_frame"] / 30.0
        end_s = s["end_frame"] / 30.0
        dur_s = end_s - start_s
        print(f"Shot {i+1} ({s['shot_id']}): [{start_s:.2f}s - {end_s:.2f}s] ({dur_s:.2f}s) '{s.get('narration_excerpt', '')[:30]}'")

if __name__ == "__main__":
    main()
