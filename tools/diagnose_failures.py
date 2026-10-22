"""Print compact digests of recorded failures, or triage a historic log file (offline)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from youtube_automation.core import failure_record as fr  # noqa: E402

_FRAME_RE = re.compile(r'^\s*File "(.+?)", line (\d+), in (.+)$')


def record_from_log(log: Path, stage: str) -> dict[str, Any] | None:
    """Build a record from the final Python traceback in a log (never appended)."""
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.startswith("Traceback (most recent call last):")]
    if not starts:
        return None
    frame, final = None, None
    for ln in lines[starts[-1] + 1 :]:
        m = _FRAME_RE.match(ln)
        if m:
            rel = fr._rel_frame_path(m.group(1))
            if rel:
                frame = {"file": rel, "line": int(m.group(2)), "function": m.group(3)}
        elif ln.strip() and not ln.startswith((" ", "\t")):
            final = ln
            break
    if final is None:
        return None
    name, _, message = final.partition(":")
    exc = type(name.strip().rsplit(".", 1)[-1], (Exception,), {})(message.strip())
    return fr.build_record(exc, stage=stage, frame=frame, evidence=[log.as_posix()])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--last", action="store_true")
    group.add_argument("--all", type=int, metavar="N")
    group.add_argument("--stage", metavar="NAME")
    ap.add_argument("--path")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log", metavar="FILE")
    args = ap.parse_args(argv)
    if args.log:
        rec = record_from_log(Path(args.log), args.stage or "log")
        records = [rec] if rec else []
    else:
        if args.last:
            record = fr.load_last_record(args.path)
            records = [record] if record else []
        else:
            records = fr.load_records(args.path)
        if args.all:
            records = records[-args.all :]
        elif args.stage:
            records = [r for r in records if r.get("stage") == args.stage][-1:]
        else:
            records = records[-1:]
    if not records:
        print("No failure records.")
        return 0
    for rec in records:
        print(json.dumps(fr.sanitize_record(rec), ensure_ascii=False) if args.json else fr.digest(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
