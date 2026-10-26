"""Unified Advanced SubStation Alpha (.ass) subtitles and graphic overlay engine.

Conforms to ADR 0002 and ADR 0006.
Consolidates ASS subtitle styling, active-word highlights, and all graphic overlay
primitives (Schulte focus grids, timer countdowns, text cards, pictograms, and cues)
into a singlePass compositing engine.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Constants & Enums
# ---------------------------------------------------------------------------

_TIMER_FRAME_EVENT_PREFIX = "__timer_frame__:"

SCHULTE_6X6: list[str] = [
    "17", "3", "29", "12", "35", "8",
    "24", "31", "6", "19", "1", "27",
    "10", "22", "34", "15", "26", "5",
    "33", "14", "21", "7", "30", "18",
    "4", "28", "11", "36", "16", "23",
    "25", "9", "32", "2", "20", "13",
]

PictogramName = Literal["phone", "eye", "study_card", "cursor", "sequence"]

_BLUE = "66391E"
_WHITE = "FFFFFF"
_GOLD = "5AE0FF"

_PATHS: dict[str, list[tuple[str, str]]] = {
    "phone": [
        (_BLUE, "m .26 .04 l .74 .04 .80 .10 .80 .90 .74 .96 .26 .96 .20 .90 .20 .10 .26 .04"),
        (_WHITE, "m .26 .18 l .74 .18 .74 .80 .26 .80 .26 .18"),
        (_GOLD, "m .43 .85 l .57 .85 .57 .89 .43 .89 .43 .85"),
        (_BLUE, "m .40 .34 l .64 .49 .40 .64 .40 .34"),
    ],
    "eye": [
        (_BLUE, "m .03 .50 b .28 .05 .72 .05 .97 .50 b .72 .95 .28 .95 .03 .50"),
        (_WHITE, "m .12 .50 b .32 .17 .68 .17 .88 .50 b .68 .83 .32 .83 .12 .50"),
        (_BLUE, "m .50 .23 b .86 .23 .86 .77 .50 .77 b .14 .77 .14 .23 .50 .23"),
        (_GOLD, "m .50 .37 b .67 .37 .67 .63 .50 .63 b .33 .63 .33 .37 .50 .37"),
    ],
    "study_card": [
        (_BLUE, "m .13 .07 l .70 .07 .87 .24 .87 .93 .13 .93 .13 .07"),
        (_WHITE, "m .20 .15 l .65 .15 .65 .31 .80 .31 .80 .86 .20 .86 .20 .15"),
        (_GOLD, "m .70 .13 l .81 .25 .70 .25 .70 .13"),
        (_BLUE, "m .29 .43 l .71 .43 .71 .48 .29 .48 .29 .43"),
        (_BLUE, "m .29 .57 l .71 .57 .71 .62 .29 .62 .29 .57"),
        (_BLUE, "m .29 .71 l .57 .71 .57 .76 .29 .76 .29 .71"),
    ],
    "cursor": [
        (_BLUE, "m .18 .08 l .85 .55 .57 .61 .72 .89 .57 .97 .41 .67 .18 .84 .18 .08"),
        (_GOLD, "m .27 .25 l .66 .52 .47 .56 .27 .69 .27 .25"),
    ],
    "sequence": [
        (_GOLD, "m .13 .17 l .25 .17 .25 .29 .13 .29 .13 .17"),
        (_BLUE, "m .34 .19 l .86 .19 .86 .27 .34 .27 .34 .19"),
        (_GOLD, "m .13 .44 l .25 .44 .25 .56 .13 .56 .13 .44"),
        (_BLUE, "m .34 .46 l .74 .46 .74 .54 .34 .54 .34 .46"),
        (_GOLD, "m .13 .71 l .25 .71 .25 .83 .13 .83 .13 .71"),
        (_BLUE, "m .34 .73 l .62 .73 .62 .81 .34 .81 .34 .73"),
    ],
}


# ---------------------------------------------------------------------------
# Helpers & String Sanitization
# ---------------------------------------------------------------------------

def _safe_ass_text(value: str) -> str:
    """Escape ASS formatting control characters."""
    return (
        value.replace("\\", "＼")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r", "")
        .replace("\n", "\\N")
    )


def _format_cs(cs: int) -> str:
    """Format integer centiseconds as H:MM:SS.cc."""
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_time(frame: int, fps: int) -> str:
    """Format frame index as standard ASS timestamp H:MM:SS.cc."""
    return _format_cs(round(frame * 100 / fps))


def _timer_ass_time(frame: int, fps: int) -> str:
    """Format frame index as truncated centiseconds for timer sync."""
    return _format_cs(frame * 100 // fps)


def _scaled_timer_ass_time(frame: int, fps: int) -> str:
    """Serialize a timer frame on the doubled centisecond PTS axis."""
    return _format_cs(frame * 200 // fps)


def _get_prop(obj: Any, key: str, default: Any = None) -> Any:
    """Extract a property from either a dict or an object."""
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


# ---------------------------------------------------------------------------
# Pictograms & Timers
# ---------------------------------------------------------------------------

def pictogram_ass(
    name: PictogramName | str,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    move_to: tuple[int, int] | None = None,
    move_ms: int | None = None,
) -> list[str]:
    """Render allowlisted vector shapes with an optional shared move."""
    if (move_to is None) != (move_ms is None):
        raise ValueError("Pictogram movement destination and duration must be provided together")
    if move_to is not None:
        if (
            not isinstance(move_to, tuple)
            or len(move_to) != 2
            or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in move_to)
        ):
            raise ValueError("Pictogram movement destination must be two non-negative pixel coordinates")
        if not isinstance(move_ms, int) or isinstance(move_ms, bool) or move_ms <= 0:
            raise ValueError("Pictogram movement duration must be a positive integer")
        position_tag = f"\\move({x},{y},{move_to[0]},{move_to[1]},0,{move_ms})"
    else:
        position_tag = f"\\pos({x},{y})"

    if name not in _PATHS:
        raise ValueError(f"Unknown pictogram name: {name}")

    result = []
    for color, path in _PATHS[name]:
        scaled = []
        coordinate = 0
        for token in path.split():
            if token in {"m", "l", "b"}:
                scaled.append(token)
            else:
                scaled.append(str(round(float(token) * (width if coordinate % 2 == 0 else height))))
                coordinate += 1
        result.append(
            f"{{{position_tag}\\p1\\bord0\\1c&H{color}&\\fad(150,0)}}"
            + " ".join(scaled)
            + "{\\p0}"
        )
    return result


def timer_segments(
    start_frame: int,
    end_frame: int,
    shot_start_frame: int,
    clock_start_frame: int,
    seconds: int,
    fps: int,
) -> list[tuple[int, int, str]]:
    """Freeze the announced limit, then tick on the global clock phase across cuts."""
    if fps < 1 or end_frame <= start_frame or seconds < 1:
        raise ValueError("Timer requires positive frame budget, rate and time limit")
    segments = []
    cursor = start_frame
    while cursor < end_frame:
        elapsed = max(0, (shot_start_frame + cursor - clock_start_frame) // fps)
        remaining = max(0, seconds - elapsed)
        next_tick = clock_start_frame + (elapsed + 1) * fps - shot_start_frame
        finish = min(end_frame, max(cursor + 1, next_tick))
        segments.append((cursor, finish, f"{remaining // 60:02d}:{remaining % 60:02d}"))
        cursor = finish
    return segments


# ---------------------------------------------------------------------------
# Recipes & Passes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OverlayAssPass:
    """Individual ASS pass with timing semantics and digest."""

    layer: int
    timer_pts_scaled: bool
    ass_text: str

    @property
    def sha256(self) -> str:
        encoded = self.ass_text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class OverlayFilterRecipe:
    """Multi-pass overlay recipe generating filter chain expressions."""

    fps: int
    passes: tuple[OverlayAssPass, ...]

    @property
    def fingerprint(self) -> str:
        payload = {
            "fps": self.fps,
            "passes": [
                {
                    "layer": item.layer,
                    "timer_pts_scaled": item.timer_pts_scaled,
                    "ass_sha256": item.sha256,
                }
                for item in self.passes
            ],
        }
        return hashlib.sha256(str(sorted(payload.items())).encode("utf-8")).hexdigest()

    def filter_chain(self, ass_files: list[str] | tuple[str, ...]) -> str:
        if len(ass_files) != len(self.passes):
            raise ValueError("ASS file count does not match the overlay recipe")
        filters: list[str] = []
        for item, ass_file in zip(self.passes, ass_files, strict=True):
            if not ass_file or Path(ass_file).name != ass_file or any(c in ass_file for c in ",;[]"):
                raise ValueError("ASS pass filenames must be simple filter-safe names")
            if item.timer_pts_scaled:
                filters.append(f"setpts=2*PTS,ass={ass_file},setpts=PTS/2")
            else:
                filters.append(f"ass={ass_file}")
        return ",".join(filters)


# ---------------------------------------------------------------------------
# Overlay ASS Document Generation
# ---------------------------------------------------------------------------

def overlay_ass(
    shot: Any,
    width: int,
    height: int,
    fps: int,
    font: str = "Arial",
    *,
    mark_timer_events: bool = False,
) -> str:
    """Compile declarative overlays into an Advanced SubStation Alpha document."""
    if any(c in font for c in "\n\r,"):
        raise ValueError("ASS font must be a single font family")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{max(22, height // 25)},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,2,0,7,30,30,30,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    overlays = _get_prop(shot, "overlays", ()) or ()
    shot_start_frame = int(_get_prop(shot, "start_frame", 0))
    local_composition = str(_get_prop(shot, "local_composition", ""))

    schulte_grid = next(
        (
            overlay
            for overlay in overlays
            if _get_prop(overlay, "kind") == "data_grid" and _get_prop(overlay, "preset") == "schulte_6x6"
        ),
        None,
    )

    for overlay in overlays:
        ox = float(_get_prop(overlay, "x", 0.1))
        oy = float(_get_prop(overlay, "y", 0.1))
        ow = float(_get_prop(overlay, "width", 0.3))
        oh = float(_get_prop(overlay, "height", 0.15))
        kind = str(_get_prop(overlay, "kind", "label"))
        start_frame = int(_get_prop(overlay, "start_frame", 0))
        end_frame = int(_get_prop(overlay, "end_frame", 0))

        x, y = round(ox * width), round(oy * height)
        w, h = round(ow * width), round(oh * height)
        start = _ass_time(start_frame, fps)
        end = _ass_time(end_frame, fps)
        contents: list[str] = []

        raw_text = str(_get_prop(overlay, "text", ""))

        if kind in {"label", "timer"}:
            text = _safe_ass_text(raw_text)
            if kind == "timer":
                clock_start_frame = _get_prop(overlay, "clock_start_frame")
                if clock_start_frame is not None:
                    value_from = _get_prop(overlay, "value_from")
                    assert value_from is not None
                    for begin, finish, clock_text in timer_segments(
                        start_frame, end_frame, shot_start_frame,
                        int(clock_start_frame), int(value_from), fps,
                    ):
                        timer_name = (
                            f"{_TIMER_FRAME_EVENT_PREFIX}{begin}:{finish}"
                            if mark_timer_events else ""
                        )
                        events.append(
                            f"Dialogue: 0,{_timer_ass_time(begin, fps)},{_timer_ass_time(finish, fps)},Default,{timer_name},0,0,0,,"
                            f"{{\\an5\\b1\\fs{max(54, h // 2)}\\bord0\\1c&H66391E&"
                            f"\\pos({x + w // 2},{y + h // 2})}}{clock_text}"
                        )
                    continue
                contents.append(
                    f"{{\\an5\\b1\\fs{max(54, h // 2)}\\bord0\\1c&H66391E&\\pos({x + w // 2},{y + h // 2})}}{text}"
                )
            elif local_composition in {"kinetic_type", "focus_sweep"}:
                longest_line = max(len(line) for line in raw_text.splitlines()) if raw_text else 1
                primary = oy < 0.55
                font_size = max(64, min(174 if primary else 104, round(w / max(1, longest_line * 0.52))))
                contents.append(
                    f"{{\\an5\\b1\\fs{font_size}\\bord0\\1c&H66391E&\\fad(180,0)"
                    f"\\pos({x + w // 2},{y + h // 2})}}{text}"
                )
            else:
                contents.append(f"{{\\pos({x},{y})}}{text}")

        elif kind == "pictogram":
            icon = _get_prop(overlay, "icon")
            assert icon is not None
            motion_to = _get_prop(overlay, "motion_to")
            motion_end_frame = _get_prop(overlay, "motion_end_frame")
            if motion_to is None:
                contents.extend(pictogram_ass(icon, x, y, w, h))
            else:
                if motion_end_frame is None:
                    raise ValueError("Moving pictograms need an arrival frame")
                move_to_px = (
                    round(motion_to[0] * width),
                    round(motion_to[1] * height),
                )
                move_ms = round((int(motion_end_frame) - start_frame) * 1000 / fps)
                if move_ms <= 0:
                    raise ValueError("Moving pictograms need a positive serialized duration")
                contents.extend(
                    pictogram_ass(
                        icon, x, y, w, h, move_to=move_to_px, move_ms=move_ms
                    )
                )

        elif kind == "highlight":
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord3\\1a&HFF&\\3c&H00BFFF&}}m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}"
            )

        elif kind == "arrow":
            head = max(6, min(w, h) // 5)
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord3\\1a&HFF&\\3c&H00BFFF&}}m 0 0 l {w} {h} m {w - head} {h} l {w} {h} {w} {h - head}{{\\p0}}"
            )

        elif kind == "mask":
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord0\\1c&H111827&\\1a&H58&}}"
                f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}"
            )

        elif kind == "card":
            size = max(22, min(72, round(h * 0.5), round((w - 32) / max(1, len(raw_text) * 0.52))))
            contents.extend(
                [
                    f"{{\\pos({x},{y})\\p1\\bord2\\1c&H66391E&\\3c&H5AE0FF&\\fad(120,0)}}"
                    f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}",
                    f"{{\\an5\\b1\\fs{size}\\bord0\\1c&HFFFFFF&\\fad(120,0)"
                    f"\\pos({x + w // 2},{y + h // 2})}}"
                    f"{_safe_ass_text(raw_text)}",
                ]
            )

        elif kind == "progress_ring":
            cx, cy = w // 2, h // 2
            radius = max(4, min(w, h) // 2 - 4)
            progress_val = float(_get_prop(overlay, "progress") or 0.0)
            sweep = max(1, round(36 * progress_val))
            points = [
                (
                    cx + round(radius * math.cos(math.radians(-90 + index * 10))),
                    cy + round(radius * math.sin(math.radians(-90 + index * 10))),
                )
                for index in range(sweep + 1)
            ]
            ring_path = f"m {cx} {cy} l " + " ".join(f"{px} {py}" for px, py in points)
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord0\\1c&H5AE0FF&\\1a&H18&}}"
                f"{ring_path} {cx} {cy}{{\\p0}}"
            )

        elif kind == "tile_reveal":
            cells = list(_get_prop(overlay, "cells", []))
            reveal = _get_prop(overlay, "reveal_cells") or list(range(len(cells)))
            cols = int(_get_prop(overlay, "columns", 1) or 1)
            rows = int(_get_prop(overlay, "rows", 1) or 1)
            cell_w = w / cols
            cell_h = h / rows
            available = max(1, end_frame - start_frame)
            step = max(1, available // max(1, len(reveal)))
            for order, cell_index in enumerate(reveal):
                row, column = divmod(cell_index, cols)
                left, top = round(column * cell_w), round(row * cell_h)
                right, bottom = round((column + 1) * cell_w), round((row + 1) * cell_h)
                reveal_frame = min(end_frame - 1, start_frame + order * step)
                reveal_start = _ass_time(reveal_frame, fps)
                shape = (
                    f"{{\\pos({x},{y})\\p1\\bord2\\1c&H20283A&\\3c&H5AE0FF&\\fad(120,0)}}"
                    f"m {left} {top} l {right} {top} {right} {bottom} {left} {bottom} {left} {top}{{\\p0}}"
                )
                label = (
                    f"{{\\an5\\b1\\fs{max(18, round(min(cell_w, cell_h) * 0.32))}"
                    f"\\pos({x + round((column + 0.5) * cell_w)},{y + round((row + 0.5) * cell_h)})"
                    f"\\fad(120,0)}}{_safe_ass_text(cells[cell_index])}"
                )
                events.extend(
                    [
                        f"Dialogue: 0,{reveal_start},{end},Default,,0,0,0,,{shape}",
                        f"Dialogue: 1,{reveal_start},{end},Default,,0,0,0,,{label}",
                    ]
                )
            continue

        elif kind == "focus_sweep":
            bar = max(3, w // 35)
            contents.append(
                f"{{\\move({x},{y},{x + w - bar},{y})\\p1\\bord0\\1c&H5AE0FF&\\1a&H35&}}"
                f"m 0 0 l {bar} 0 {bar} {h} 0 {h} 0 0{{\\p0}}"
            )

        elif kind == "comparison":
            secondary_text = str(_get_prop(overlay, "secondary_text", ""))
            longest_len = max(len(raw_text), len(secondary_text))
            size = max(64, min(122, round((w / 2 - 64) / max(1, longest_len * 0.5))))
            contents.extend(
                [
                    f"{{\\pos({x},{y})\\p1\\bord0\\1c&H66391E&}}"
                    f"m 0 0 l {w // 2 - 12} 0 {w // 2 - 12} {h} 0 {h} 0 0{{\\p0}}",
                    f"{{\\pos({x},{y})\\p1\\bord0\\1c&HCEE7F2&}}"
                    f"m {w // 2 + 12} 0 l {w} 0 {w} {h} {w // 2 + 12} {h} {w // 2 + 12} 0{{\\p0}}",
                    f"{{\\an5\\b1\\fs{size}\\bord0\\1c&HFFFFFF&\\fad(180,0)\\pos({x + w // 4},{y + h // 2})}}{_safe_ass_text(raw_text)}",
                    f"{{\\an5\\b1\\fs{size}\\bord0\\1c&H66391E&\\fad(240,0)\\pos({x + 3 * w // 4},{y + h // 2})}}"
                    f"{_safe_ass_text(secondary_text)}",
                ]
            )

        elif kind == "trace_path":
            raw_pts = _get_prop(overlay, "points", []) or []
            pts = [(round(px * w), round(py * h)) for px, py in raw_pts]
            if pts:
                trace_path_str = f"m {pts[0][0]} {pts[0][1]} l " + " ".join(
                    f"{px} {py}" for px, py in pts[1:]
                )
                contents.append(
                    f"{{\\pos({x},{y})\\p1\\bord4\\1a&HFF&\\3c&H5AE0FF&}}{trace_path_str}{{\\p0}}"
                )

        elif kind == "counter":
            val_from = _get_prop(overlay, "value_from")
            val_to = _get_prop(overlay, "value_to")
            assert val_from is not None and val_to is not None
            values = list(range(int(val_from), int(val_to) + 1))
            available = end_frame - start_frame
            for index, value in enumerate(values):
                value_start = start_frame + round(index * available / len(values))
                value_end = start_frame + round((index + 1) * available / len(values))
                suffix = f" {_safe_ass_text(raw_text)}" if raw_text else ""
                content = (
                    f"{{\\an5\\b1\\fs{max(28, h // 2)}\\pos({x + w // 2},{y + h // 2})}}"
                    f"{value}{suffix}"
                )
                events.append(
                    f"Dialogue: 1,{_ass_time(value_start, fps)},{_ass_time(value_end, fps)},Default,,0,0,0,,{content}"
                )
            continue

        elif kind == "challenge_frame":
            contents.extend(
                [
                    f"{{\\pos({x},{y})\\p1\\bord3\\1a&HFF&\\3c&H5AE0FF&}}"
                    f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}",
                    f"{{\\an8\\b1\\fs{max(54, height // 16)}\\1c&H5AE0FF&"
                    f"\\pos({x + w // 2},{max(36, y - height // 30)})}}{_safe_ass_text(raw_text)}",
                ]
            )

        elif kind == "rule_reveal":
            contents.extend(
                [
                    f"{{\\pos({x},{y})\\p1\\bord0\\1c&H66391E&\\1a&H00&\\fad(180,0)}}"
                    f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}",
                    f"{{\\an5\\b1\\fs{max(48, height // 17)}\\bord0\\pos({x + w // 2},{y + h // 2})"
                    f"\\fad(180,0)}}{_safe_ass_text(raw_text)}",
                ]
            )

        elif kind == "fixation_cue":
            cx, cy = x + w // 2, y + h // 2
            radius = max(8, min(w, h) // 5)
            contents.extend(
                [
                    f"{{\\pos({cx},{cy})\\p1\\bord3\\1a&HFF&\\3c&H5AE0FF&}}"
                    f"m {-radius} 0 l {radius} 0 m 0 {-radius} l 0 {radius}{{\\p0}}",
                    f"{{\\an5\\b1\\fs{max(18, radius)}\\pos({cx},{cy})}}+",
                ]
            )

        elif kind == "target_indicator":
            target_cell = _get_prop(overlay, "target_cell")
            if schulte_grid is None or target_cell is None:
                raise ValueError("Schulte target indicator requires its deterministic grid")
            grid_ox = float(_get_prop(schulte_grid, "x", 0.15))
            grid_oy = float(_get_prop(schulte_grid, "y", 0.15))
            grid_ow = float(_get_prop(schulte_grid, "width", 0.7))
            grid_oh = float(_get_prop(schulte_grid, "height", 0.7))
            grid_x = round(grid_ox * width)
            grid_y = round(grid_oy * height)
            cell_w = round(grid_ow * width / 6)
            cell_h = round(grid_oh * height / 6)
            row, column = divmod(int(target_cell), 6)
            cx = grid_x + round((column + 0.5) * cell_w)
            cy = grid_y + round((row + 0.5) * cell_h)
            radius = max(8, round(min(cell_w, cell_h) * 0.38))
            duration_ms = max(1, round((end_frame - start_frame) * 1000 / fps))
            contents.append(
                f"{{\\pos({cx},{cy})\\p1\\bord4\\1a&HFF&\\3c&H5AE0FF&"
                f"\\t(0,{duration_ms},\\fscx112\\fscy112\\3c&H56D68B&)}}"
                f"m {-radius} {-radius} l {radius} {-radius} {radius} {radius} {-radius} {radius} {-radius} {-radius}{{\\p0}}"
            )

        elif kind == "start_transition":
            badge_y = round(height * 0.0525)
            if raw_text == "Start":
                continue  # Generic readiness chrome must not announce a premature start
            contents.extend(
                [
                    f"{{\\an5\\b1\\fs{max(32, min(round(height * 0.0625), round(h * 0.85)))}\\bord0\\1c&H66391E&\\pos({width // 2},{badge_y})}}"
                    f"{_safe_ass_text(raw_text)}",
                ]
            )

        elif kind == "data_grid":
            cols = int(_get_prop(overlay, "columns", 6) or 6)
            rows = int(_get_prop(overlay, "rows", 6) or 6)
            cell_w = w / cols
            cell_h = h / rows
            highlight_cells = list(_get_prop(overlay, "highlight_cells", []) or [])
            for cell_index in highlight_cells:
                row, column = divmod(cell_index, cols)
                left, top = round(column * cell_w), round(row * cell_h)
                right, bottom = round((column + 1) * cell_w), round((row + 1) * cell_h)
                contents.append(
                    f"{{\\pos({x},{y})\\p1\\bord0\\1c&H56D68B&\\1a&H30&}}"
                    f"m {left} {top} l {right} {top} {right} {bottom} {left} {bottom} {left} {top}{{\\p0}}"
                )
            grid_path = [f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0"]
            grid_path.extend(
                f"m {round(column * cell_w)} 0 l {round(column * cell_w)} {h}"
                for column in range(1, cols)
            )
            grid_path.extend(
                f"m 0 {round(row * cell_h)} l {w} {round(row * cell_h)}"
                for row in range(1, rows)
            )
            interior = []
            for column in range(1, cols):
                line_x = round(column * cell_w)
                interior.append(f"m {line_x} 0 l {line_x + 2} 0 {line_x + 2} {h} {line_x} {h}")
            for row in range(1, rows):
                line_y = round(row * cell_h)
                interior.append(f"m 0 {line_y} l {w} {line_y} {w} {line_y + 2} 0 {line_y + 2}")
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord0\\1a&H00&\\1c&H303030&}}"
                + " ".join(interior) + "{\\p0}"
            )
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord2\\1a&HFF&\\3c&H303030&}}"
                + " ".join(grid_path)
                + "{\\p0}"
            )
            preset = _get_prop(overlay, "preset")
            cells = list(_get_prop(overlay, "cells", []) or [])
            if preset == "schulte_6x6" and not cells:
                cells = SCHULTE_6X6
            font_size = max(18, round(min(cell_w, cell_h) * 0.48))
            for cell_index, cell in enumerate(cells):
                row, column = divmod(cell_index, cols)
                cell_x = x + round((column + 0.5) * cell_w)
                cell_y = y + round((row + 0.5) * cell_h)
                safe_cell = (
                    str(cell)
                    .replace("\\", "＼")
                    .replace("{", "(")
                    .replace("}", ")")
                    .replace("\r", " ")
                    .replace("\n", " ")
                )
                contents.append(
                    f"{{\\an5\\fs{font_size}\\b1\\bord1\\3c&HFFFFFF&\\1c&H202020&"
                    f"\\pos({cell_x},{cell_y})}}{safe_cell}"
                )

        events.extend(
            f"Dialogue: 0,{start},{end},Default,,0,0,0,,{content}" for content in contents
        )

    return header + "\n".join(events) + "\n"


def _overlay_recipe_from_ass(
    ass_text: str, fps: int, *, scale_timer_events: bool = True
) -> OverlayFilterRecipe:
    """Parse serialized ASS text into multi-pass recipe scaling timer PTS if required."""
    if not scale_timer_events:
        return OverlayFilterRecipe(fps, (OverlayAssPass(0, False, ass_text),))

    first_dialogue = ass_text.find("Dialogue: ")
    if first_dialogue < 0:
        return OverlayFilterRecipe(fps, (OverlayAssPass(0, False, ass_text),))
    header = ass_text[:first_dialogue]
    lines = [
        line for line in ass_text[first_dialogue:].split("\n")
        if line.startswith("Dialogue: ")
    ]
    layered: dict[int, list[tuple[bool, str]]] = {}
    has_running_timer = False
    for line in lines:
        fields = line[len("Dialogue: "):].split(",", 9)
        if len(fields) != 10:
            raise ValueError("Malformed ASS dialogue in overlay recipe")
        try:
            layer = int(fields[0])
        except ValueError as exc:
            raise ValueError("ASS dialogue layer must be an integer") from exc
        timer_pts_scaled = False
        if fields[4].startswith(_TIMER_FRAME_EVENT_PREFIX):
            frame_parts = fields[4][len(_TIMER_FRAME_EVENT_PREFIX):].split(":")
            if len(frame_parts) != 2:
                raise ValueError("Malformed timer frame marker in ASS dialogue")
            begin, finish = (int(part) for part in frame_parts)
            fields[1] = _scaled_timer_ass_time(begin, fps)
            fields[2] = _scaled_timer_ass_time(finish, fps)
            fields[4] = ""
            timer_pts_scaled = True
            has_running_timer = True
        layered.setdefault(layer, []).append(
            (timer_pts_scaled, "Dialogue: " + ",".join(fields))
        )

    if not has_running_timer:
        layer = min(layered, default=0)
        return OverlayFilterRecipe(fps, (OverlayAssPass(layer, False, ass_text),))

    passes: list[OverlayAssPass] = []
    for layer in sorted(layered):
        run_kind: bool | None = None
        run: list[str] = []
        for timer_pts_scaled, line in layered[layer]:
            if run and timer_pts_scaled != run_kind:
                passes.append(
                    OverlayAssPass(layer, bool(run_kind), header + "\n".join(run) + "\n")
                )
                run = []
            run_kind = timer_pts_scaled
            run.append(line)
        if run:
            passes.append(
                OverlayAssPass(layer, bool(run_kind), header + "\n".join(run) + "\n")
            )
    return OverlayFilterRecipe(fps, tuple(passes))


def overlay_filter_recipe(
    shot: Any, width: int, height: int, fps: int, font: str = "Arial"
) -> OverlayFilterRecipe:
    """Build shared ASS passes, scaling only running timer PTS above 100 FPS."""
    overlays = _get_prop(shot, "overlays", ()) or ()
    if not overlays:
        return OverlayFilterRecipe(fps, ())
    scale_timer_events = fps > 100 and any(
        _get_prop(o, "kind") == "timer" and _get_prop(o, "clock_start_frame") is not None
        for o in overlays
    )
    ass_text = overlay_ass(
        shot, width, height, fps, font, mark_timer_events=scale_timer_events
    )
    return _overlay_recipe_from_ass(
        ass_text, fps, scale_timer_events=scale_timer_events
    )


# ---------------------------------------------------------------------------
# Legacy Subtitle Utilities
# ---------------------------------------------------------------------------

def fix_arabic_srt(input_path: str, output_path: str) -> None:
    """Ensure Arabic SRT transcript is preserved in UTF-8."""
    with open(input_path, encoding="utf-8-sig") as f:
        content = f.read()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


def build_subtitle_style_string(config: Mapping[str, Any]) -> str:
    """Generate ASS style attribute string from configuration."""
    return (
        f"Fontname={config['SUB_FONT_NAME']},"
        f"Fontsize={config['SUB_FONT_SIZE']},"
        f"PrimaryColour={config['SUB_PRIMARY_COLOR']},"
        f"OutlineColour={config['SUB_OUTLINE_COLOR']},"
        f"BorderStyle={config['SUB_BORDER_STYLE']},"
        f"Outline={config['SUB_OUTLINE']},"
        f"Shadow={config['SUB_SHADOW']},"
        f"Alignment={config['SUB_ALIGNMENT']},"
        f"MarginV={config['SUB_MARGIN_V']},"
        f"Bold={config['SUB_BOLD']}"
    )


def build_dynamic_ass_subtitles(
    raw_transcript_path: str,
    output_ass_path: str,
    config: Mapping[str, Any],
    total_duration: float = 0.0,
    scene_graph: Any = None,
) -> str | None:
    """Generate Advanced SubStation Alpha subtitles with active word highlights."""
    if not os.path.exists(raw_transcript_path):
        return None

    font_name = config.get("SUB_FONT_NAME", "Cairo, Tajawal, Segoe UI, Arial")
    font_size = int(config.get("SUB_FONT_SIZE", 34))
    primary_color = "&H00FFFFFF"
    highlight_color = "&H003EB0FF"
    outline_color = "&H00000000"
    margin_v = int(config.get("SUB_MARGIN_V", 65))

    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.get("OUTPUT_WIDTH", 2560)}
PlayResY: {config.get("OUTPUT_HEIGHT", 1440)}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H80000000,1,0,0,0,100,100,0,0,1,3.8,2.0,2,60,60,{margin_v},1
Style: TopicTitle,Cairo,54,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4.0,2.0,8,60,60,100,1
Style: CalloutBadge,Tajawal,40,&H00E09F3E,&H000000FF,&H001E1E24,&H80000000,1,0,0,0,100,100,0,0,1,3.0,1.5,5,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def format_ass_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines = []
    with open(raw_transcript_path, encoding="utf-8") as f:
        for raw_line in f:
            line_str = raw_line.strip()
            if not line_str:
                continue
            match = re.match(r"^\[?(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\]?\s*(.*)", line_str)
            if match:
                h = int(match.group(1)) if match.group(1) else 0
                m = int(match.group(2))
                s = float(match.group(3))
                start_sec = h * 3600.0 + m * 60.0 + s
                text = match.group(4).strip()
                if text:
                    lines.append((start_sec, text))

    events = []
    for i, (start_sec, text) in enumerate(lines):
        end_sec = (
            lines[i + 1][0]
            if i < len(lines) - 1
            else (total_duration if total_duration > start_sec else start_sec + 3.5)
        )
        words = text.split()
        if not words:
            continue
        start_str = format_ass_time(start_sec)
        end_str = format_ass_time(end_sec)
        highlighted_body = "".join(
            [
                f"{{\\c{highlight_color}\\t(0,200,\\fscx105\\fscy105)}}{w}{{\\c{primary_color}\\fscx100\\fscy100}} "
                for w in words
            ]
        )
        events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{highlighted_body.strip()}")

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(events) + "\n")

    return output_ass_path


def format_dialogue_ass(
    dialogue_events: Sequence[Mapping[str, Any] | Any],
    width: int,
    height: int,
    fps: int,
    font: str = "Cairo, Tajawal, Arial",
) -> str:
    """Format dialogue lines as bottom-centered ASS events."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{max(28, height // 22)},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3.0,1.5,2,40,40,50,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for ev in dialogue_events:
        start_frame = int(_get_prop(ev, "start_frame", 0))
        end_frame = int(_get_prop(ev, "end_frame", 0))
        text = _safe_ass_text(str(_get_prop(ev, "text", "")))
        start_ts = _ass_time(start_frame, fps)
        end_ts = _ass_time(end_frame, fps)
        events.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}")

    return header + "\n".join(events) + "\n"
