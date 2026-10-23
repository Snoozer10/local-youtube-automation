"""Small, deterministic object illustrations for narration-bound local graphics."""
from __future__ import annotations

from typing import Literal

PictogramName = Literal["phone", "eye", "study_card", "cursor", "sequence"]

BLUE = "66391E"
WHITE = "FFFFFF"
GOLD = "5AE0FF"

_PATHS: dict[str, list[tuple[str, str]]] = {
    "phone": [
        (BLUE, "m .26 .04 l .74 .04 .80 .10 .80 .90 .74 .96 .26 .96 .20 .90 .20 .10 .26 .04"),
        (WHITE, "m .26 .18 l .74 .18 .74 .80 .26 .80 .26 .18"),
        (GOLD, "m .43 .85 l .57 .85 .57 .89 .43 .89 .43 .85"),
        (BLUE, "m .40 .34 l .64 .49 .40 .64 .40 .34"),
    ],
    "eye": [
        (BLUE, "m .03 .50 b .28 .05 .72 .05 .97 .50 b .72 .95 .28 .95 .03 .50"),
        (WHITE, "m .12 .50 b .32 .17 .68 .17 .88 .50 b .68 .83 .32 .83 .12 .50"),
        (BLUE, "m .50 .23 b .86 .23 .86 .77 .50 .77 b .14 .77 .14 .23 .50 .23"),
        (GOLD, "m .50 .37 b .67 .37 .67 .63 .50 .63 b .33 .63 .33 .37 .50 .37"),
    ],
    "study_card": [
        (BLUE, "m .13 .07 l .70 .07 .87 .24 .87 .93 .13 .93 .13 .07"),
        (WHITE, "m .20 .15 l .65 .15 .65 .31 .80 .31 .80 .86 .20 .86 .20 .15"),
        (GOLD, "m .70 .13 l .81 .25 .70 .25 .70 .13"),
        (BLUE, "m .29 .43 l .71 .43 .71 .48 .29 .48 .29 .43"),
        (BLUE, "m .29 .57 l .71 .57 .71 .62 .29 .62 .29 .57"),
        (BLUE, "m .29 .71 l .57 .71 .57 .76 .29 .76 .29 .71"),
    ],
    "cursor": [
        (BLUE, "m .18 .08 l .85 .55 .57 .61 .72 .89 .57 .97 .41 .67 .18 .84 .18 .08"),
        (GOLD, "m .27 .25 l .66 .52 .47 .56 .27 .69 .27 .25"),
    ],
    "sequence": [
        (GOLD, "m .13 .17 l .25 .17 .25 .29 .13 .29 .13 .17"),
        (BLUE, "m .34 .19 l .86 .19 .86 .27 .34 .27 .34 .19"),
        (GOLD, "m .13 .44 l .25 .44 .25 .56 .13 .56 .13 .44"),
        (BLUE, "m .34 .46 l .74 .46 .74 .54 .34 .54 .34 .46"),
        (GOLD, "m .13 .71 l .25 .71 .25 .83 .13 .83 .13 .71"),
        (BLUE, "m .34 .73 l .62 .73 .62 .81 .34 .81 .34 .73"),
    ],
}


def pictogram_ass(
    name: PictogramName,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    move_to: tuple[int, int] | None = None,
    move_ms: int | None = None,
) -> list[str]:
    """Render allowlisted shapes with an optional shared move, then hold at its endpoint."""
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
        result.append(f"{{{position_tag}\\p1\\bord0\\1c&H{color}&\\fad(150,0)}}"
                      + " ".join(scaled) + "{\\p0}")
    return result
