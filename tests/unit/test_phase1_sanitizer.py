"""Unit tests for automate_all Arabic language gate and Gemini chatter sanitization."""

import automate_all


class TestPhase1Sanitizer:
    def test_is_valid_arabic_transcreation_detects_english_chat(self):
        english_chat = (
            "That is a fantastic hook. It immediately pulls the audience in by tapping into a universal curiosity "
            "we've all experienced, while quickly pivoting from the cliche 'do they love me?' to a much deeper question. "
            "Since this is just the first of 19 paragraphs, how would you like to proceed?"
        )
        assert not automate_all.is_valid_arabic_transcreation(english_chat)

    def test_is_valid_arabic_transcreation_rejects_empty_or_short(self):
        assert not automate_all.is_valid_arabic_transcreation("")
        assert not automate_all.is_valid_arabic_transcreation("Short text")
        assert not automate_all.is_valid_arabic_transcreation("   ")

    def test_is_valid_arabic_transcreation_accepts_clean_arabic(self):
        arabic_text = (
            "شوف يا سيدي، إحنا شايفين نفسنا بني آدمين، لينا أسامي، ووظايف، ومسحولين في أقساط شقق وتجديد باقة نت، "
            "وحياتنا معقدة كِدَه. بس الفكرة فين؟ الحيوانات ولا تعرف أي حاجة عن السَحْلَة دِي."
        )
        assert automate_all.is_valid_arabic_transcreation(arabic_text)

    def test_sanitize_gemini_chatter_strips_preamble_and_outro(self):
        raw_output = (
            "Here is the translation of the final paragraph, adapted into the conversational, "
            "dramatic Cairene Amiya cadence for the script's conclusion:\n\n"
            '"كل عادة بنعملها، كل صوت بيطلع مننا، وكل قرار بناخده.. بيديوم درس. إحنا طول الوقت بنعرّف الحيوانات دي إحنا مين بالظبط."'
            "\n\nDo you want to add a classic sign-off to officially wrap up the episode?"
        )
        sanitized = automate_all.sanitize_gemini_chatter(raw_output)
        assert not sanitized.startswith("Here is the translation")
        assert not sanitized.endswith("wrap up the episode?")
        assert "كل عادة بنعملها" in sanitized
        assert automate_all.is_valid_arabic_transcreation(sanitized)

    def test_sanitize_gemini_chatter_preserves_uncontaminated_arabic(self):
        pure_arabic = "خُد عندك مثلاً الكلاب... دِي يمكن أكتر حيوانات بتفهمنا. بيعرفوا يقروا تعبيرات الوش."
        assert automate_all.sanitize_gemini_chatter(pure_arabic) == pure_arabic
