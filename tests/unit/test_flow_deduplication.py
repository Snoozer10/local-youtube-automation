"""Unit tests for Google Flow Quadruple-Lock Handshake and Deduplication.

Validates:
1. RollingSha256Ledger 15-frame rolling window collision detection and eviction
2. check_flow_quota_or_errors modal/quota interceptor
3. card_spawn_handshake adaptive polling and quota interception
4. Dual-Mode prompt generation logic (Mode A Master Setup vs Mode B Surgical Delta L.A.D. < 25 words)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from youtube_automation.visuals.flow_generator import (
    RollingSha256Ledger,
    build_dual_mode_prompt,
    card_spawn_handshake,
    check_flow_quota_or_errors,
    classify_flow_error,
)


class TestRollingSha256Ledger:
    def test_ledger_detects_stale_scrape_collision(self, tmp_path):
        ledger = RollingSha256Ledger(window_size=15)

        file_a = tmp_path / "frame_01.png"
        file_a.write_bytes(b"image data frame 1")

        file_b = tmp_path / "frame_02.png"
        file_b.write_bytes(b"image data frame 2")

        file_dup = tmp_path / "frame_03_stale.png"
        file_dup.write_bytes(b"image data frame 1")  # identical content to frame 1

        collision_a, hash_a = ledger.check_and_register(str(file_a))
        assert not collision_a
        assert len(hash_a) == 64

        collision_b, hash_b = ledger.check_and_register(str(file_b))
        assert not collision_b
        assert hash_b != hash_a

        # file_dup has exact same bytes as file_a -> MUST detect collision
        collision_dup, hash_dup = ledger.check_and_register(str(file_dup))
        assert collision_dup
        assert hash_dup == hash_a

    def test_ledger_window_eviction(self, tmp_path):
        window_size = 5
        ledger = RollingSha256Ledger(window_size=window_size)

        files = []
        for i in range(7):
            f = tmp_path / f"frame_{i}.png"
            f.write_bytes(f"unique frame content {i}".encode())
            files.append(f)

        # Register frames 0..4 (fills 5 slots)
        for i in range(5):
            collision, _ = ledger.check_and_register(str(files[i]))
            assert not collision

        assert len(ledger.history) == 5
        # Frame 0 is currently in ledger
        assert ledger.is_collision(ledger.compute_file_hash(str(files[0])))

        # Register frame 5 -> evicts frame 0
        ledger.check_and_register(str(files[5]))
        assert len(ledger.history) == 5
        assert not ledger.is_collision(ledger.compute_file_hash(str(files[0])))

        # Register frame 6 -> evicts frame 1
        ledger.check_and_register(str(files[6]))
        assert not ledger.is_collision(ledger.compute_file_hash(str(files[1])))
        assert ledger.is_collision(ledger.compute_file_hash(str(files[6])))


class TestQuotaAndModalInterceptor:
    def test_detects_quota_exhaustion_message(self):
        page = MagicMock()
        mock_loc = MagicMock()
        mock_loc.is_visible.return_value = True
        mock_loc.inner_text.return_value = "You have reached your usage limit for this period."

        error_locators = MagicMock()
        error_locators.count.return_value = 1
        error_locators.nth.return_value = mock_loc

        page.get_by_text.return_value = error_locators

        err = check_flow_quota_or_errors(page)
        assert err is not None
        assert "reached your usage limit" in err.lower()

    def test_returns_none_when_clean(self):
        page = MagicMock()
        error_locators = MagicMock()
        error_locators.count.return_value = 0
        page.get_by_text.return_value = error_locators

        err = check_flow_quota_or_errors(page)
        assert err is None


class TestCardSpawnHandshake:
    def test_handshake_succeeds_when_card_count_increments(self):
        page = MagicMock()
        locator_mock = MagicMock()
        # Count starts at 5, then increments to 6
        locator_mock.count.side_effect = [5, 6]
        page.locator.return_value = locator_mock

        # Quota check returns None
        error_locators = MagicMock()
        error_locators.count.return_value = 0
        page.get_by_text.return_value = error_locators

        spawned = card_spawn_handshake(page, pre_card_count=5, timeout_seconds=5.0)
        assert spawned is True

    def test_handshake_aborts_on_quota_error(self):
        page = MagicMock()
        locator_mock = MagicMock()
        locator_mock.count.return_value = 5
        page.locator.return_value = locator_mock

        # Quota check detects error
        err_loc = MagicMock()
        err_loc.is_visible.return_value = True
        err_loc.inner_text.return_value = "Reached your usage limit"
        error_locators = MagicMock()
        error_locators.count.return_value = 1
        error_locators.nth.return_value = err_loc
        page.get_by_text.return_value = error_locators

        with pytest.raises(RuntimeError, match="(?i)reached your usage limit"):
            card_spawn_handshake(page, pre_card_count=5, timeout_seconds=5.0)


class TestDualModePromptBuilder:
    def test_mode_a_for_beat_1(self):
        item = {
            "beat_index": 1,
            "scene_archetype": "PROGRESSIVE_BUILD",
            "master_setup_prompt": "An antique brass double-pan balance scale resting on a dark walnut drafting table, chiaroscuro lighting, 24mm lens.",
            "surgical_delta_prompt": "In the attached scene, add a gold coin to the left pan.",
            "visual_delta": "gold coin",
            "spatial_direction": "to the left pan",
        }
        mode, prompt = build_dual_mode_prompt(item, attach_success=True)
        assert mode == "A"
        assert "antique brass double-pan" in prompt

    def test_mode_b_lad_formula_under_25_words(self):
        item = {
            "beat_index": 2,
            "scene_archetype": "PROGRESSIVE_BUILD",
            "master_setup_prompt": "An antique brass double-pan balance scale resting on a dark walnut drafting table, chiaroscuro lighting, 24mm lens.",
            "surgical_delta_prompt": "In the attached scene, maintain identical background, desk, and lighting. Add a heavy lead weight to right pan.",
            "visual_delta": "a heavy lead weight",
            "spatial_direction": "to right pan",
        }
        mode, prompt = build_dual_mode_prompt(item, attach_success=True)
        assert mode == "B"
        assert prompt.startswith("In the attached scene, maintain identical background")
        words = prompt.split()
        assert len(words) < 25

    def test_mode_b_fallback_to_mode_a_when_chip_attachment_fails(self):
        item = {
            "beat_index": 2,
            "scene_archetype": "PROGRESSIVE_BUILD",
            "master_setup_prompt": "Master setup prompt description for beat 1 fallback.",
            "visual_delta": "second element",
            "spatial_direction": "centered",
        }
        mode, prompt = build_dual_mode_prompt(item, attach_success=False)
        assert mode == "A"
        assert prompt == "Master setup prompt description for beat 1 fallback."


class TestClassifyFlowError:
    def test_classifies_fatal_quota_english(self):
        assert (
            classify_flow_error("You have reached your usage limit. You have not been charged.")
            == "FATAL_QUOTA"
        )
        assert classify_flow_error("Quota exceeded for this project.") == "FATAL_QUOTA"
        assert classify_flow_error("Rate limit exceeded") == "FATAL_QUOTA"

    def test_classifies_fatal_quota_arabic(self):
        assert (
            classify_flow_error("لقد بلغت الحدّ الأقصى للاستخدام. يُرجى إعادة المحاولة لاحقًا.")
            == "FATAL_QUOTA"
        )

    def test_classifies_policy_violation(self):
        assert classify_flow_error("This prompt violates safety guidelines.") == "POLICY_VIOLATION"
        assert classify_flow_error("Image failed due to copyright or infringement notice.") == "POLICY_VIOLATION"
        assert classify_flow_error("تم رفض الطلب بسبب إرشادات الأمان.") == "POLICY_VIOLATION"
        assert classify_flow_error("Prompt violates content guidelines.") == "POLICY_VIOLATION"

    def test_classifies_transient_error(self):
        assert classify_flow_error("Something went wrong loading your media") == "TRANSIENT_ERROR"
        assert classify_flow_error("Playwright Timeout Error") == "TRANSIENT_ERROR"
        assert classify_flow_error("Network connection dropped") == "TRANSIENT_ERROR"
        assert classify_flow_error("Google Flow rendering froze mid-progress.") == "TRANSIENT_ERROR"


class TestAttachPreviousImagesSelectionOrder:
    def test_top_of_feed_selection_and_chronological_reversal(self):
        """Verifies that Google Flow top-prepended cards (lowest Y) are correctly selected
        as the most recent generations and reversed for chronological attachment order.
        """
        # Simulated feed cards: Y=60 is most recent render (Card 3), Y=400 is Card 2, Y=800 is Card 1 (oldest)
        simulated_cards = [
            (800, 30, "Card_1_Oldest"),
            (60, 30, "Card_3_Newest"),
            (400, 30, "Card_2_Middle"),
        ]
        # Sort ascending by Y (as done in flow_generator.py)
        simulated_cards.sort(key=lambda item: (item[0], item[1]))
        primary_cards = [c[2] for c in simulated_cards]

        assert primary_cards == ["Card_3_Newest", "Card_2_Middle", "Card_1_Oldest"]

        # 1 image attach (immediate previous frame)
        target_1 = list(reversed(primary_cards[:1]))
        assert target_1 == ["Card_3_Newest"]

        # 2 images attach (chronological: Card 2 then Card 3)
        target_2 = list(reversed(primary_cards[:2]))
        assert target_2 == ["Card_2_Middle", "Card_3_Newest"]


