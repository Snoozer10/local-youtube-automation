import pytest
from unit.test_production_shots import shot

from youtube_automation.production.graphic_cues import bind_schulte_overlays, schulte_word_cues
from youtube_automation.production.shots import Overlay, ShotPlan, _validate_interactive_graphics


def cue_timeline():
    tokens = [(0, "Schulte"), (4, "focus"), (4.5, "center"), (8, "40"), (8.4, "seconds"),
              (12, "ready"), (13, "1"), (14, "2"), (15, "3"), (16, "start")]
    return {"fps": 30, "total_frames": 600,
            "words": [{"text": text, "start": start, "end": start + .2} for start, text in tokens],
            "spans": [{"index": 0, "start_frame": 0, "end_frame": 600,
                       "text": "Schulte table: focus on the center; 40 seconds; ready 1 2 3 start"}]}


def timeline_with_words(tokens):
    timeline = cue_timeline()
    timeline["words"] = [
        {"text": text, "start": start, "end": start + 0.2}
        for start, text in tokens
    ]
    timeline["spans"][0]["text"] = "Schulte table: focus on the center; exercise timing"
    return timeline


def grid_shot(start=0, end=600, grid_layout="full"):
    duration = end - start
    return shot(start_frame=start, end_frame=end, overlays=[
        Overlay(kind="data_grid", preset="schulte_6x6", grid_layout=grid_layout,
                start_frame=0, end_frame=duration),
        Overlay(kind="rule_reveal", text="Find the numbers", start_frame=0, end_frame=duration),
        Overlay(kind="timer", text="00:00", start_frame=0, end_frame=duration),
        Overlay(kind="target_indicator", target_cell=10, start_frame=0, end_frame=duration),
        Overlay(kind="fixation_cue", start_frame=0, end_frame=duration),
    ])


def test_canonical_words_replace_eager_timer_fixation_and_answer_highlight():
    overlays = bind_schulte_overlays(grid_shot(), cue_timeline())
    assert not any(o.kind == "target_indicator" for o in overlays)
    assert next(o for o in overlays if o.kind == "timer").start_frame == 240
    assert next(o for o in overlays if o.kind == "timer").text == "00:40"
    assert next(o for o in overlays if o.kind == "fixation_cue").start_frame == 120
    assert next(o for o in overlays if o.kind == "rule_reveal").end_frame == 360
    assert [(o.text, o.start_frame, o.end_frame) for o in overlays if o.kind == "start_transition"] == [
        ("Ready?", 360, 390), ("1", 390, 420), ("2", 420, 450), ("3", 450, 480), ("Start!", 480, 510)]


def test_cues_survive_shot_boundaries_without_restarting_countdown_or_grid():
    first = bind_schulte_overlays(grid_shot(0, 420), cue_timeline())
    second = bind_schulte_overlays(grid_shot(420, 600), cue_timeline())
    assert next(o for o in first if o.kind == "data_grid").cells == next(o for o in second if o.kind == "data_grid").cells
    assert [(o.text, o.start_frame) for o in second if o.kind == "start_transition"] == [("2", 0), ("3", 30), ("Start!", 60)]
    assert next(o for o in second if o.kind == "fixation_cue").start_frame == 0
    assert not any(o.kind == "rule_reveal" for o in second)


def test_cue_binding_is_idempotent_and_non_grid_shots_are_unchanged():
    original = grid_shot()
    rebound = original.model_copy(update={"overlays": bind_schulte_overlays(original, cue_timeline())})
    assert bind_schulte_overlays(rebound, cue_timeline()) == rebound.overlays
    plain = shot()
    assert bind_schulte_overlays(plain, cue_timeline()) == plain.overlays


def test_time_limit_and_numeric_words_without_ready_sequence_do_not_start_task():
    timeline = cue_timeline()
    timeline["words"] = timeline["words"][:5]
    cues = schulte_word_cues(timeline)
    assert not any(kind == "start_transition" for kind, _, _ in cues)
    assert [cue for cue in cues if cue[0] == "timer"] == [("timer", 240, "00:40")]


@pytest.mark.parametrize(
    ("tokens", "limit_frame"),
    [
        (
            [
                (0, "Schulte"), (1, "focus"), (1.2, "center"),
                (3, "40"), (3.2, "seconds"), (4, "and"),
                (4.2, "rest"), (4.5, "10"), (4.7, "seconds"),
                (8, "ready"), (8.3, "1"), (8.6, "2"), (8.9, "3"), (9.2, "start"),
            ],
            90,
        ),
        (
            [
                (0, "Schulte"), (1, "focus"), (1.2, "center"),
                (3, "40"), (3.2, "seconds"), (4, "then"),
                (4.2, "rest"), (4.5, "10"), (4.7, "seconds"),
                (8, "ready"), (8.3, "1"), (8.6, "2"), (8.9, "3"), (9.2, "start"),
            ],
            90,
        ),
        (
            [
                (0, "Schulte"), (1, "focus"), (1.2, "center"),
                (3, "rest"), (3.2, "10"), (3.4, "seconds"), (3.8, "then"),
                (4.5, "40"), (4.7, "seconds"),
                (8, "ready"), (8.3, "1"), (8.6, "2"), (8.9, "3"), (9.2, "start"),
            ],
            135,
        ),
        (
            [
                (0, "Schulte"), (1, "focus"), (1.2, "center"),
                (3, "10"), (3.2, "seconds"), (3.4, "of"), (3.6, "rest"),
                (4, "then"), (5, "40"), (5.2, "seconds"),
                (8, "ready"), (8.3, "1"), (8.6, "2"), (8.9, "3"), (9.2, "start"),
            ],
            150,
        ),
    ],
    ids=["exercise-and-rest", "exercise-then-rest", "rest-before-exercise", "seconds-of-rest"],
)
def test_local_rest_phrase_does_not_mask_an_adjacent_exercise_limit(tokens, limit_frame):
    cues = schulte_word_cues(timeline_with_words(tokens))

    assert [cue for cue in cues if cue[0] == "timer"] == [
        ("timer", limit_frame, "00:40")
    ]


def test_preview_fixation_is_centered_inside_the_preview_grid():
    overlays = bind_schulte_overlays(
        grid_shot(grid_layout="preview"), cue_timeline()
    )
    board = next(o for o in overlays if o.kind == "data_grid")
    fixation = next(o for o in overlays if o.kind == "fixation_cue")

    assert fixation.grid_layout == "preview"
    assert board.x <= fixation.x
    assert board.y <= fixation.y
    assert fixation.x + fixation.width <= board.x + board.width
    assert fixation.y + fixation.height <= board.y + board.height


def test_each_timer_binds_to_its_own_start_and_rest_is_not_a_timer():
    tokens = [
        (0, "Schulte"), (2, "focus"), (2.5, "center"),
        (4, "40"), (4.4, "seconds"),
        (8, "ready"), (9, "1"), (10, "2"), (11, "3"), (12, "start"),
        (14, "rest"), (14.2, "10"), (14.4, "seconds"),
        (20, "then"), (20.2, "20"), (20.6, "seconds"),
        (25, "ready"), (26, "1"), (27, "2"), (28, "3"), (29, "start"),
    ]
    timeline = {
        "fps": 30,
        "total_frames": 1800,
        "words": [
            {"text": text, "start": start, "end": start + 0.2}
            for start, text in tokens
        ],
        "spans": [{
            "index": 0,
            "start_frame": 0,
            "end_frame": 1800,
            "text": (
                "Schulte: focus on the center; 40 seconds; ready 1 2 3 start; "
                "rest 10 seconds; then 20 seconds; ready 1 2 3 start"
            ),
        }],
    }

    timers = [
        overlay for overlay in bind_schulte_overlays(grid_shot(0, 1800), timeline)
        if overlay.kind == "timer"
    ]

    assert [timer.text for timer in timers] == ["00:40", "00:20"]
    assert [(timer.start_frame, timer.end_frame) for timer in timers] == [
        (120, 870), (870, 1470)
    ]
    assert [timer.clock_start_frame for timer in timers] == [360, 870]
    assert [timer.value_from for timer in timers] == [40, 20]



@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        (("forty", "seconds"), "00:40"),
        (("forty", "two", "seconds"), "00:42"),
        (("one", "minute"), "01:00"),
        (("أربعون", "ثانية"), "00:40"),
        (("ارْبعين", "ثواني"), "00:40"),
        (("اثنين", "دقيقة"), "02:00"),
        (("ثلاثون", "دقيقة"), "30:00"),
        (("sixty", "minutes"), "60:00"),
        (("٤٠", "ثانية"), "00:40"),
    ],
)
def test_spoken_number_words_and_minutes_compile_exact_timer_values(phrase, expected):
    tokens = [(0, "Schulte")]
    tokens.extend((3 + index * 0.2, text) for index, text in enumerate(phrase))
    timers = [
        cue for cue in schulte_word_cues(timeline_with_words(tokens))
        if cue[0] == "timer"
    ]

    assert timers == [("timer", 90, expected)]


@pytest.mark.parametrize(
    "duration",
    [
        [(2, "rest"), (2.2, "one"), (2.4, "minute")],
        [(2, "one"), (2.2, "minute"), (2.4, "pause")],
        [(2, "one"), (2.2, "minute"), (2.4, "of"), (2.6, "rest")],
        [(2, "استراحة"), (2.2, "عدة"), (2.4, "دقائق")],
    ],
)
def test_minute_rest_phrases_never_create_exercise_countdowns(duration):
    timeline = timeline_with_words([(0, "Schulte"), *duration])

    assert not any(
        kind == "timer" for kind, _, _ in schulte_word_cues(timeline)
    )


def test_spoken_word_limits_bind_to_distinct_actual_start_intervals():
    tokens = [
        (0, "Schulte"), (2, "focus"), (2.5, "center"),
        (4, "forty"), (4.4, "seconds"),
        (8, "ready"), (9, "1"), (10, "2"), (11, "3"), (12, "start"),
        (14, "rest"), (14.2, "ten"), (14.4, "minutes"),
        (20, "then"), (20.2, "twenty"), (20.6, "seconds"),
        (25, "ready"), (26, "1"), (27, "2"), (28, "3"), (29, "start"),
    ]
    timeline = timeline_with_words(tokens)
    timeline["total_frames"] = 1800
    timers = [
        overlay for overlay in bind_schulte_overlays(
            grid_shot(0, 1800), timeline
        )
        if overlay.kind == "timer"
    ]

    assert [timer.text for timer in timers] == ["00:40", "00:20"]
    assert [(timer.start_frame, timer.end_frame) for timer in timers] == [
        (120, 870), (870, 1470)
    ]
    assert [timer.clock_start_frame for timer in timers] == [360, 870]
    assert [timer.value_from for timer in timers] == [40, 20]


@pytest.mark.parametrize(
    "phrase",
    [
        ("one", "hundred", "seconds"),
        ("about", "forty", "seconds"),
        ("1.5", "minutes"),
        ("10-20", "seconds"),
        ("١٫٥", "دقائق"),
        ("١٠–٢٠", "ثانية"),
        ("-30", "seconds"),
        ("+30", "seconds"),
        ("−30", "seconds"),
        ("20", "-", "30", "seconds"),
        ("20", "to", "30", "seconds"),
        (".5", "minutes"),
        ("-", "30", "seconds"),
        ("+", "30", "seconds"),
        (".", "5", "minutes"),
    ],
)
def test_unsupported_or_ambiguous_spoken_limits_fail_when_bound_to_start(phrase):
    tokens = [(0, "Schulte")]
    tokens.extend((4 + index * 0.2, text) for index, text in enumerate(phrase))
    tokens.extend([
        (12, "ready"), (13, "1"), (14, "2"), (15, "3"), (16, "start")
    ])

    with pytest.raises(ValueError, match="Unsupported or ambiguous spoken exercise time limit"):
        schulte_word_cues(timeline_with_words(tokens))


def test_word_minute_limit_over_supported_bound_fails_when_bound_to_start():
    tokens = [
        (0, "Schulte"), (4, "sixty"), (4.2, "one"), (4.4, "minutes"),
        (12, "ready"), (13, "1"), (14, "2"), (15, "3"), (16, "start"),
    ]

    with pytest.raises(ValueError, match="outside supported bounds"):
        schulte_word_cues(timeline_with_words(tokens))


def test_multiple_limits_for_one_start_are_rejected_as_ambiguous():
    timeline = cue_timeline()
    timeline["words"] = [
        {"text": text, "start": start, "end": start + 0.2}
        for start, text in [
            (0, "Schulte"), (8, "20"), (8.3, "seconds"),
            (9, "30"), (9.3, "seconds"),
            (12, "ready"), (13, "1"), (14, "2"), (15, "3"), (16, "start"),
        ]
    ]

    with pytest.raises(ValueError, match="Multiple Schulte time limits"):
        schulte_word_cues(timeline)


@pytest.mark.parametrize("seconds", ["0", "3601"])
def test_out_of_range_limit_is_rejected_when_bound_to_a_spoken_start(seconds):
    timeline = cue_timeline()
    timeline["words"][3]["text"] = seconds

    with pytest.raises(ValueError, match="outside supported bounds"):
        schulte_word_cues(timeline)


def test_out_of_range_unbound_number_does_not_create_a_timer():
    timeline = cue_timeline()
    timeline["words"] = [
        {"text": text, "start": start, "end": start + 0.2}
        for start, text in [(0, "Schulte"), (8, "3601"), (8.4, "seconds")]
    ]

    assert not any(kind == "timer" for kind, _, _ in schulte_word_cues(timeline))


def test_out_of_range_limit_after_last_start_is_unbound_and_ignored():
    timeline = cue_timeline()
    timeline["words"].extend(
        [
            {"text": "3601", "start": 18, "end": 18.2},
            {"text": "seconds", "start": 18.2, "end": 18.4},
        ]
    )

    timers = [cue for cue in schulte_word_cues(timeline) if cue[0] == "timer"]
    assert timers == [("timer", 240, "00:40")]


def test_legacy_span_only_timing_keeps_a_single_instruction_without_invented_words():
    timeline = cue_timeline()
    timeline.pop("words")
    timeline["spans"][0]["text"] = "Schulte table: focus on the center; ready 1 2 3 start"
    cues = schulte_word_cues(timeline)
    assert [kind for kind, _, _ in cues] == ["fixation_cue", "start_transition"]
    assert all(frame == 0 for _, frame, _ in cues)
    assert cues[-1][2] == timeline["spans"][0]["text"]


def test_version_three_preflight_refuses_eager_cues_until_rebound():
    timeline = cue_timeline()
    plan = ShotPlan(version=3, brief_sha256="a"*64, timeline_sha256="b"*64,
                    fps=30, total_frames=600, shots=[grid_shot()],
                    editorial_policy={"cadence": "balanced", "target_shot_seconds": 20,
                                      "max_shot_seconds": 20, "max_consecutive_framing": 6,
                                      "max_motion_fraction": 1})
    with pytest.raises(ValueError, match="canonical word timestamps"):
        _validate_interactive_graphics(plan, timeline, complete=True)
    current = plan.shots[0].model_copy(update={"overlays": bind_schulte_overlays(plan.shots[0], timeline)})
    _validate_interactive_graphics(plan.model_copy(update={"shots": [current]}), timeline, complete=True)
    # A transcript span may contain later instructions beyond the compiled prefix.
    prefix = grid_shot(0, 90)
    prefix = prefix.model_copy(update={"overlays": bind_schulte_overlays(prefix, timeline)})
    _validate_interactive_graphics(plan.model_copy(update={"shots": [prefix]}), timeline, complete=False)



def test_article_minute_limit_is_bound_to_actual_spoken_start():
    timeline = cue_timeline()
    timeline["words"][3]["text"] = "a"
    timeline["words"][4]["text"] = "minute"

    limit_frame = round(timeline["words"][3]["start"] * timeline["fps"])
    assert ("timer", limit_frame, "01:00") in schulte_word_cues(timeline)


def test_unsupported_article_hour_bound_to_start_fails_addressably():
    timeline = cue_timeline()
    timeline["words"][3]["text"] = "an"
    timeline["words"][4]["text"] = "hour"

    with pytest.raises(ValueError, match="Unsupported or ambiguous spoken exercise time limit"):
        schulte_word_cues(timeline)
