import pytest
import os
import sys

# Ensure the root directory is in the sys.path to import refine_script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from refine_script import sanitize_solo_narrator_text, validate_refinement_quality

def test_sanitize_solo_narrator_text():
    # Strips prefixes
    assert sanitize_solo_narrator_text("الراوي: أهلاً بكم") == "أهلاً بكم"
    assert sanitize_solo_narrator_text("أبو حميد: بص يا سيدي") == "بص يا سيدي"
    assert sanitize_solo_narrator_text("المتحدث: كلام مهم") == "كلام مهم"
    assert sanitize_solo_narrator_text("Host: Welcome back") == "Welcome back"
    assert sanitize_solo_narrator_text("Speaker 1: Hello") == "Hello"
    assert sanitize_solo_narrator_text("Narrator:   Test") == "Test"
    
    # Preserves rhetorical internal use
    assert sanitize_solo_narrator_text("طب ليه أبو حميد قال كدا؟") == "طب ليه أبو حميد قال كدا؟"
    assert sanitize_solo_narrator_text("أنا كأبو حميد بحب الشاي") == "أنا كأبو حميد بحب الشاي"
    assert sanitize_solo_narrator_text("الراوي بيقول كلام مش منطقي") == "الراوي بيقول كلام مش منطقي"

def test_validate_refinement_quality():
    # Rejects text with unstripped speaker prefixes
    is_valid, reason = validate_refinement_quality("الراوي: بص يا سيدي الفكرة كلها في الدماغ.")
    assert not is_valid
    assert "speaker prefix" in reason.lower() or "multi-character dialogue" in reason.lower()

    # Rejects text with banned fusha connectors
    is_valid, reason = validate_refinement_quality("علاوة على ذلك، الفكرة كلها في الدماغ اللي بتفكر كتير جدا يا عزيزي.")
    assert not is_valid
    assert "banned formal fusha connector" in reason.lower()

    # Rejects raw digits
    is_valid, reason = validate_refinement_quality("الفكرة كلها إننا عندنا 15 منطقة في الدماغ بتفكر كتير جدا يا عزيزي.")
    assert not is_valid
    assert "un-transliterated digits" in reason.lower()

    # Accepts valid Al-Daheeh refined paragraphs with Gary Provost cadence variance
    valid_text = "بص يا عزيزي. الموضوع مش سهل خالص زي ما أنت متخيل. الخلايا العصبية في دماغك عمالة تبعت إشارات كهربائية بسرعة تلاتمية كيلو في الساعة عشان تاخد قرار تافه زي دا. لبسنا في الحيط!"
    is_valid, reason = validate_refinement_quality(valid_text)
    assert is_valid
