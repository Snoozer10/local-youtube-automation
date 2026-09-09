"""Unit & Diagnostic Drill Tests for 03.02 Turn Completion Detector."""

import pytest

from .exercise import (
    clean_response_prefix,
    evaluate_stability_step,
    is_stop_button_or_spinner_active,
)


@pytest.mark.drill
def test_detect_stop_button_english_and_arabic() -> None:
    # English stop buttons
    assert is_stop_button_or_spinner_active(["Stop generating"], False) is True
    assert is_stop_button_or_spinner_active(["Cancel response"], False) is True

    # Arabic stop buttons
    assert is_stop_button_or_spinner_active(["إيقاف التوليد"], False) is True
    assert is_stop_button_or_spinner_active(["توقف"], False) is True

    # Spinner active with no stop button
    assert is_stop_button_or_spinner_active(["Send"], True) is True

    # Clean idle state
    assert is_stop_button_or_spinner_active(["Send", "Microphone"], False) is False


@pytest.mark.drill
def test_clean_response_prefix_multi_lingual() -> None:
    assert clean_response_prefix("Gemini said: Here is your script.") == "Here is your script."
    assert clean_response_prefix("قال Gemini: هذا هو النص المطلوب.") == "هذا هو النص المطلوب."
    assert clean_response_prefix("Gemini a dit: Voici le texte.") == "Voici le texte."
    assert clean_response_prefix("Pure text without prefix") == "Pure text without prefix"


@pytest.mark.drill
def test_evaluate_stability_filters_transient_placeholders() -> None:
    # "Thinking..." placeholder must reset stable count
    count, text, complete = evaluate_stability_step(
        current_text="Thinking...",
        last_text="Thinking...",
        stable_count=3,
        still_generating=False,
    )
    assert count == 0
    assert complete is False


@pytest.mark.drill
def test_evaluate_stability_resets_during_active_generation() -> None:
    # Even if text is unchanged, active generation must keep stable_count at 0
    count, text, complete = evaluate_stability_step(
        current_text="النص الكامل للمقطع الأول",
        last_text="النص الكامل للمقطع الأول",
        stable_count=3,
        still_generating=True,
    )
    assert count == 0
    assert complete is False


@pytest.mark.drill
def test_full_streaming_lifecycle_3_factor_handshake() -> None:
    # Simulate a sequence of observation ticks during LLM streaming:
    # Tick 1: Thinking phase (spinner active)
    # Tick 2: First token burst (streaming active, stop button visible)
    # Tick 3: Second token burst (streaming active)
    # Tick 4: Generation finished, text first observed
    # Ticks 5-8: Generation idle, text stable across 4 checks
    # Tick 9: 5th stable check -> completes!

    stream_events = [
        {"text": "Thinking...", "generating": True},
        {"text": "Gemini said: مرحبا بكم", "generating": True},
        {"text": "Gemini said: مرحبا بكم في هذا الشرح الشامل لليوتيوب.", "generating": True},
        {"text": "Gemini said: مرحبا بكم في هذا الشرح الشامل لليوتيوب.", "generating": False},
        {"text": "Gemini said: مرحبا بكم في هذا الشرح الشامل لليوتيوب.", "generating": False},
        {"text": "Gemini said: مرحبا بكم في هذا الشرح الشامل لليوتيوب.", "generating": False},
        {"text": "Gemini said: مرحبا بكم في هذا الشرح الشامل لليوتيوب.", "generating": False},
        {"text": "Gemini said: مرحبا بكم في هذا الشرح الشامل لليوتيوب.", "generating": False},
    ]

    stable_count = 0
    last_text = ""
    completed = False
    final_text = ""

    for event in stream_events:
        stable_count, last_text, completed = evaluate_stability_step(
            current_text=event["text"],
            last_text=last_text,
            stable_count=stable_count,
            still_generating=event["generating"],
            min_length=15,
            target_stable=5,
        )
        if completed:
            final_text = last_text
            break

    assert completed is True
    assert final_text == "مرحبا بكم في هذا الشرح الشامل لليوتيوب."
    assert stable_count == 5
