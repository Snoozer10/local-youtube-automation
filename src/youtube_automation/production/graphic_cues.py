"""Compile interactive cues from canonical words; never reveal a task answer by default."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .shots import Overlay, Shot, ShotPlan

CueKind = Literal["fixation_cue", "timer", "start_transition"]
_NUMERIC_SEPARATORS = frozenset("+-−‐‑‒–—.,٫/")
_START_TERMS = frozenset({"ابدا", "ابدأ", "start", "begin"})


def _token(text: str) -> str:
    normalized = re.sub(r"[\u064b-\u065f\u0670]", "", text.casefold())
    # Keep numeric punctuation so unsupported quantities cannot become integers.
    if normalized in _NUMERIC_SEPARATORS or re.search(
        r"\d[^\w]+\d|[+\-\u2010-\u2015\u2212]\s*\d|(?<!\w)[.,\u066b]\d",
        normalized,
    ):
        return normalized
    return re.sub(r"[^\w]", "", normalized)



_ENGLISH_SMALL = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(),
    range(20),
    strict=True,
))
_ENGLISH_TENS = dict(zip(
    "twenty thirty forty fifty sixty seventy eighty ninety".split(),
    range(20, 100, 10),
    strict=True,
))
_ENGLISH_ONES = {word: value for word, value in _ENGLISH_SMALL.items() if 1 <= value <= 9}
_ARABIC_SMALL = {
    "صفر": 0, "واحد": 1, "واحدة": 1, "اثنان": 2, "اثنين": 2,
    "اثنتان": 2, "اثنتين": 2, "ثلاث": 3, "ثلاثة": 3,
    "أربع": 4, "اربع": 4, "أربعة": 4, "اربعة": 4,
    "خمس": 5, "خمسة": 5, "ست": 6, "ستة": 6, "سبع": 7, "سبعة": 7,
    "ثمان": 8, "ثماني": 8, "ثمانية": 8, "تسع": 9, "تسعة": 9,
    "عشر": 10, "عشرة": 10,
}
_ARABIC_TENS = {
    "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30,
    "أربعون": 40, "أربعين": 40, "اربعون": 40, "اربعين": 40,
    "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60,
    "سبعون": 70, "سبعين": 70, "ثمانون": 80, "ثمانين": 80,
    "تسعون": 90, "تسعين": 90,
}
_SPOKEN_NUMBERS = {**_ENGLISH_SMALL, **_ENGLISH_TENS, **_ARABIC_SMALL, **_ARABIC_TENS}
_UNSUPPORTED_QUANTITIES = {
    "hundred", "thousand", "million", "dozen", "couple", "few", "several",
    "some", "many", "multiple", "half", "handful", "numerous", "countless",
    "مئة", "مائة", "مئه", "ألف", "الف", "آلاف", "مليون", "عدة", "بعض",
    "قليل", "كثير", "نصف",
}
_AMBIGUOUS_TIME_WORDS = {
    "about", "around", "roughly", "approximately", "approx", "nearly",
    "almost", "over", "under", "more", "less", "حوالي", "تقريبا", "نحو",
}
_REST_TERMS = {
    "rest", "break", "pause", "relax",
    "راحة", "استراحة", "استرح", "استريح", "استرخي",
}
_SECOND_TERMS = {"ثانيه", "ثانية", "ثواني", "second", "seconds", "sec", "secs"}
_MINUTE_TERMS = {"minute", "minutes", "min", "mins", "دقيقة", "دقيقه", "دقائق"}
_TIME_UNITS = _SECOND_TERMS | _MINUTE_TERMS
_CLAUSE_BOUNDARIES = {
    "then", "and", "but", "or", "after", "before",
    "ثم", "بعد", "بعدها", "لكن", "او", "و",
}


def _spoken_number(tokens: list[str], index: int) -> tuple[int, int] | None:
    token = tokens[index]
    if token.isdecimal():
        return int(token), 1
    for tens_word, tens in _ENGLISH_TENS.items():
        if token.startswith(tens_word) and token[len(tens_word):] in _ENGLISH_ONES:
            return tens + _ENGLISH_ONES[token[len(tens_word):]], 1
    value = _SPOKEN_NUMBERS.get(token)
    if value is None:
        return None
    if token in _ENGLISH_TENS and index + 1 < len(tokens):
        if tokens[index + 1] in _ENGLISH_ONES:
            return value + _ENGLISH_ONES[tokens[index + 1]], 2
        if (
            index + 2 < len(tokens) and tokens[index + 1] == "and"
            and tokens[index + 2] in _ENGLISH_ONES
        ):
            return value + _ENGLISH_ONES[tokens[index + 2]], 3
    if 1 <= value <= 9 and index + 1 < len(tokens):
        following = tokens[index + 1]
        arabic_tens = _ARABIC_TENS.get(following[1:] if following.startswith("و") else following)
        if arabic_tens is not None:
            return value + arabic_tens, 2
        if (
            following == "و" and index + 2 < len(tokens)
            and tokens[index + 2] in _ARABIC_TENS
        ):
            return value + _ARABIC_TENS[tokens[index + 2]], 3
    return value, 1


def _is_number_marker(token: str) -> bool:
    return (
        bool(re.search(r"\d", token))
        or token in _NUMERIC_SEPARATORS
        or token in _SPOKEN_NUMBERS
        or token in _UNSUPPORTED_QUANTITIES
        or any(
            token.startswith(word) and token[len(word):] in {"hundred", "thousand", "million"}
            for word in _SPOKEN_NUMBERS
        )
    )


def _has_ambiguous_time_word(tokens: list[str]) -> bool:
    return any(
        token in _AMBIGUOUS_TIME_WORDS
        or (
            token == "at" and index + 1 < len(tokens)
            and tokens[index + 1] in {"least", "most"}
        )
        for index, token in enumerate(tokens)
    )


def _is_rest_duration(tokens: list[str], number_index: int, unit_index: int) -> bool:
    prefix = tokens[max(0, number_index - 5):number_index]
    boundary = max(
        (index for index, token in enumerate(prefix) if token in _CLAUSE_BOUNDARIES),
        default=-1,
    )
    suffix = tokens[unit_index + 1:min(len(tokens), unit_index + 3)]
    return (
        any(token in _REST_TERMS for token in prefix[boundary + 1:])
        or bool(suffix) and (
            suffix[0] in _REST_TERMS
            or (
                len(suffix) > 1
                and suffix[0] == "of"
                and suffix[1] in _REST_TERMS
            )
        )
    )


def _spoken_time_limits(
    words: list[dict[str, Any]], tokens: list[str], fps: int
) -> list[tuple[int, int | None]]:
    limits: list[tuple[int, int | None]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        number = _spoken_number(tokens, index)
        article_unit = (
            tokens[index + 1]
            if index + 1 < len(tokens)
            else None
        )
        if token == "an" and article_unit == "hour":
            article_hour_unit_index = index + 1
            if not _is_rest_duration(tokens, index, article_hour_unit_index):
                frame = round(float(words[index]["start"]) * fps)
                limits.append((frame, None))
            index = article_hour_unit_index + 1
            continue
        if number is None and token == "a" and article_unit in {"second", "minute"}:
            number = (1, 1)
        if number is None and not _is_number_marker(token):
            index += 1
            continue

        value, consumed = number if number is not None else (None, 1)
        end = index + consumed
        if token.isdecimal():
            unit_index = next(
                (j for j in range(index + 1, min(len(tokens), index + 4))
                 if tokens[j] in _TIME_UNITS),
                None,
            )
        else:
            unit_index = end if end < len(tokens) and tokens[end] in _TIME_UNITS else None
            if unit_index is None:
                possible_unit = next(
                    (j for j in range(end, min(len(tokens), end + 4))
                     if tokens[j] in _TIME_UNITS),
                    None,
                )
                if possible_unit is None:
                    index += consumed if number is not None else 1
                    continue
                between = tokens[end:possible_unit]
                if not any(_is_number_marker(item) for item in between):
                    index += consumed if number is not None else 1
                    continue
                unit_index, value = possible_unit, None

        if unit_index is None or any(
            item in _START_TERMS for item in tokens[end:unit_index]
        ):
            index += consumed if number is not None else 1
            continue
        if _is_rest_duration(tokens, index, unit_index):
            index = unit_index + 1
            continue
        if any(_is_number_marker(item) for item in tokens[end:unit_index]):
            value = None
        prefix = tokens[max(0, index - 2):index]
        suffix = tokens[unit_index + 1:min(len(tokens), unit_index + 4)]
        if _has_ambiguous_time_word(prefix + tokens[end:unit_index]):
            value = None
        if (
            value is not None and suffix and suffix[0] in {"and", "or"}
            and any(_is_number_marker(item) for item in suffix[1:])
            and not any(item in _TIME_UNITS for item in suffix[1:])
            and not any(item in _REST_TERMS for item in suffix[1:])
        ):
            value = None
        if value is not None:
            value *= 60 if tokens[unit_index] in _MINUTE_TERMS else 1
        frame = round(float(words[index]["start"]) * fps)
        limits.append((frame, value))
        index = unit_index + 1
    return limits


def schulte_word_cues(timeline: dict[str, Any]) -> list[tuple[CueKind, int, str]]:
    from .shots import narration_bound_visual_events

    intros = [
        event.introduction_frame
        for event in narration_bound_visual_events(timeline)
        if event.preset == "schulte_6x6"
    ]
    if not intros:
        return []
    fps, first = int(timeline["fps"]), min(intros)
    if not timeline.get("words"):
        # Legacy span-only timelines cannot prove individual countdown timing.
        # Keep instructions at their canonical span boundary; never interpolate words.
        legacy: list[tuple[CueKind, int, str]] = []
        for span in timeline.get("spans", []):
            frame = int(span["start_frame"])
            if int(span["end_frame"]) <= first:
                continue
            text = str(span.get("text", ""))
            span_tokens = {_token(token) for token in text.split()}
            if span_tokens & {"المركز", "center", "centre"} and span_tokens & {
                "تركز", "ركز", "focus", "look", "ثبت"
            }:
                legacy.append(("fixation_cue", max(frame, first), ""))
            if span_tokens & {"جاهز", "مستعد", "ready"} and span_tokens & {
                "ابدا", "ابدأ", "start", "begin"
            }:
                legacy.append(("start_transition", max(frame, first), text))
        return legacy

    words = [
        word for word in timeline.get("words", [])
        if round(float(word["start"]) * fps) >= first
    ]
    tokens = [_token(str(word["text"])) for word in words]
    cues: list[tuple[CueKind, int, str]] = []
    time_limits = _spoken_time_limits(words, tokens, fps)

    for i, token in enumerate(tokens):
        frame = round(float(words[i]["start"]) * fps)
        if token in {"المركز", "center", "centre"} and not any(
            cue[0] == "fixation_cue" for cue in cues
        ):
            anchors = [
                j for j in range(max(0, i - 4), i + 1)
                if tokens[j] in {"تركز", "ركز", "focus", "look", "ثبت"}
            ]
            if anchors:
                cue_frame = round(float(words[anchors[0]]["start"]) * fps)
                cues.append(("fixation_cue", cue_frame, ""))

        if token in {"جاهز", "مستعد", "ready"}:
            sequence = tokens[i + 1:i + 5]
            if len(sequence) == 4 and sequence[:3] in (
                ["1", "2", "3"],
                ["١", "٢", "٣"],
                ["one", "two", "three"],
                ["واحد", "اثنان", "ثلاثة"],
            ) and sequence[3] in _START_TERMS:
                labels = (
                    ["جاهز؟", "1", "2", "3", "ابدأ"]
                    if token != "ready"
                    else ["Ready?", "1", "2", "3", "Start!"]
                )
                cues.extend(
                    (
                        "start_transition",
                        round(float(words[i + j]["start"]) * fps),
                        label,
                    )
                    for j, label in enumerate(labels)
                )

    start_frames = [
        frame
        for kind, frame, text in cues
        if kind == "start_transition" and text in {"ابدأ", "Start!"}
    ]
    assigned_starts: set[int] = set()
    for frame, seconds in time_limits:
        start_frame = next(
            (candidate for candidate in start_frames if candidate >= frame),
            None,
        )
        if start_frame is None:
            if seconds is None:
                continue
            if not 1 <= seconds <= 3600:
                # Unbound numbers are not exercise limits; ignore them even if
                # an earlier exercise already had a spoken start.
                continue
            if start_frames:
                raise ValueError(
                    "Schulte time limit has no following spoken start cue"
                )
            valid_unbound_limits = sum(
                1 for _, value in time_limits
                if value is not None and 1 <= value <= 3600
            )
            if valid_unbound_limits > 1:
                raise ValueError(
                    "Repeated Schulte time limits require distinct spoken start cues"
                )
            # A lone announced value without a recognized start remains static.
            cues.append(
                ("timer", frame, f"{seconds // 60:02d}:{seconds % 60:02d}")
            )
            continue
        if seconds is None:
            raise ValueError("Unsupported or ambiguous spoken exercise time limit")
        if not 1 <= seconds <= 3600:
            raise ValueError("Spoken exercise time limit is outside supported bounds")
        if start_frame in assigned_starts:
            raise ValueError(
                "Multiple Schulte time limits resolve to one spoken start cue"
            )
        assigned_starts.add(start_frame)
        cues.append(
            ("timer", frame, f"{seconds // 60:02d}:{seconds % 60:02d}")
        )

    return sorted(cues, key=lambda cue: cue[1])


def bind_schulte_overlays(shot: Shot, timeline: dict[str, Any]) -> list[Overlay]:
    from .shots import Overlay

    if not any(o.kind == "data_grid" and o.preset == "schulte_6x6" for o in shot.overlays):
        return list(shot.overlays)
    cues = schulte_word_cues(timeline)
    countdown = [cue for cue in cues if cue[0] == "start_transition"]
    start_frames = [
        frame for _, frame, text in countdown if text in {"ابدأ", "Start!"}
    ]
    ready_frame = countdown[0][1] if countdown else int(timeline["total_frames"])
    total = int(timeline["total_frames"])
    fps = int(timeline["fps"])
    grid_layout: Literal["full", "preview"] = next(
        (
            overlay.grid_layout
            for overlay in shot.overlays
            if overlay.kind == "data_grid" and overlay.preset == "schulte_6x6"
        ),
        "full",
    )
    overlays: list[Overlay] = []
    for overlay in shot.overlays:
        if overlay.kind in {"fixation_cue", "timer", "target_indicator", "start_transition"}:
            continue
        # Setup copy clears before the spoken countdown; the grid stays fixed.
        if overlay.kind in {"rule_reveal", "label"}:
            end = min(overlay.end_frame, ready_frame - shot.start_frame)
            if end <= overlay.start_frame:
                continue
            overlay = overlay.model_copy(update={"end_frame": end})
        overlays.append(overlay)

    timer_specs: list[tuple[int, int | None, int, int]] = []
    for kind, announced_frame, text in cues:
        if kind != "timer":
            continue
        minutes, seconds = map(int, text.split(":"))
        limit_seconds = minutes * 60 + seconds
        start_frame = next(
            (candidate for candidate in start_frames if candidate >= announced_frame),
            None,
        )
        if start_frame is None:
            timer_specs.append((announced_frame, None, limit_seconds, total))
            continue
        next_start = next(
            (candidate for candidate in start_frames if candidate > start_frame),
            total,
        )
        timer_end = min(total, start_frame + limit_seconds * fps, next_start)
        timer_specs.append((announced_frame, start_frame, limit_seconds, timer_end))

    previous_timer_end: int | None = None
    for announced_frame, clock_start, limit_seconds, timer_end in timer_specs:
        display_start = announced_frame
        if previous_timer_end is not None:
            display_start = max(display_start, previous_timer_end)
        previous_timer_end = timer_end
        begin, finish = max(display_start, shot.start_frame), min(timer_end, shot.end_frame)
        if begin >= finish:
            continue
        minutes, seconds = divmod(limit_seconds, 60)
        overlays.append(
            Overlay(
                kind="timer",
                start_frame=begin - shot.start_frame,
                end_frame=finish - shot.start_frame,
                text=f"{minutes:02d}:{seconds:02d}",
                clock_start_frame=clock_start,
                value_from=limit_seconds if clock_start is not None else None,
                x=0.82,
                y=0.025,
                width=0.15,
                height=0.08,
            )
        )

    for kind, start, text in cues:
        if kind == "timer":
            continue
        end = total
        if kind == "start_transition":
            end = next((cue[1] for cue in countdown if cue[1] > start), total)
            if text in {"ابدأ", "Start!"}:
                end = min(end, start + fps)
        begin, finish = max(start, shot.start_frame), min(end, shot.end_frame)
        if begin >= finish:
            continue
        if kind == "start_transition":
            overlays.append(
                Overlay(
                    kind=kind,
                    start_frame=begin - shot.start_frame,
                    end_frame=finish - shot.start_frame,
                    text=text,
                    x=0.3,
                    y=0.01,
                    width=0.4,
                    height=0.075,
                )
            )
        else:
            overlays.append(
                Overlay(
                    kind=kind,
                    start_frame=begin - shot.start_frame,
                    end_frame=finish - shot.start_frame,
                    text=text,
                    grid_layout=grid_layout if kind == "fixation_cue" else "full",
                )
            )
    return overlays


def bind_schulte_plan_cues(plan: ShotPlan, timeline: dict[str, Any]) -> ShotPlan:
    """Rebind compiled cue timing without changing any generated scene or its recipe."""
    return plan.model_copy(update={"shots": [
        shot.model_copy(update={"overlays": bind_schulte_overlays(shot, timeline)})
        for shot in plan.shots
    ]})


def timer_segments(start_frame: int, end_frame: int, shot_start_frame: int,
                   clock_start_frame: int, seconds: int, fps: int) -> list[tuple[int, int, str]]:
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
