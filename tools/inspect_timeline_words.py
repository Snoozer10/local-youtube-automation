import json
from pathlib import Path


def main() -> None:
    root = Path("youtube_runs/adaptive-soldiers-ledger-samar-original-20261009")
    t = json.load(open(root / "timeline.json", encoding="utf-8"))
    for _i, w in enumerate(t["words"]):
        if 10.0 <= w["start"] <= 16.0 or 10.0 <= w["end"] <= 16.0:
            print(f"[{w['start']:.2f}s - {w['end']:.2f}s] {w['text']}")

if __name__ == "__main__":
    main()
