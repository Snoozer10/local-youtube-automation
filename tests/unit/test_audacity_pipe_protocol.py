"""Unit tests for Audacity named-pipe protocol semantics against a fake pipe pair."""

import pytest
from mocks.mock_named_pipe import NamedPipePair, consume_until_empty_line

import automate_audacity


@pytest.fixture
def pair() -> NamedPipePair:
    return NamedPipePair()


class TestCommandFraming:
    def test_command_is_framed_with_trailing_newline_and_flushed(self, pair):
        automate_audacity.send_audacity_command(pair.write_pipe, pair.read_pipe, "SelectAll:")
        assert pair.sent_text == "SelectAll:\n"
        assert pair.flushes >= 1

    def test_sequential_commands_preserve_order(self, pair):
        pair.enqueue_response("ok\n", "\n")
        automate_audacity.send_audacity_command(pair.write_pipe, pair.read_pipe, "SelectAll:")
        automate_audacity.send_audacity_command(pair.write_pipe, pair.read_pipe, "Export2:")
        assert pair.sent_commands == ["SelectAll:", "Export2:"]

    def test_function_returns_raw_accumulated_response(self, pair):
        pair.enqueue_response("BatchCommand finished.\n", "\n")
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "SelectAll:"
        )
        assert response == "BatchCommand finished.\n\n"


class TestEmptyLineTerminator:
    def test_consumer_stops_at_first_empty_line(self, pair):
        pair.enqueue_response("line one\n", "line two\n", "\n", "post-terminator\n")
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "SelectAll:"
        )
        assert response == "line one\nline two\n\n"
        assert pair.read_pipe.has_pending()
        assert pair.read_pipe.readline() == "post-terminator\n"

    def test_multi_line_response_fully_drained(self, pair):
        pair.enqueue_response("a\n", "b\n", "c\n", "\n")
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "GetInfo"
        )
        assert response == "a\nb\nc\n\n"
        assert not pair.read_pipe.has_pending()

    def test_blank_only_response_terminates_immediately(self, pair):
        pair.enqueue_response("\n")
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "SelectAll:"
        )
        assert response == "\n"


class TestEofHandling:
    def test_eof_before_any_output_returns_without_hanging(self, pair):
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "SelectAll:"
        )
        assert response == ""

    def test_eof_after_partial_unterminated_line_returns_partial(self, pair):
        pair.enqueue_response("crashed mid-outpu")
        response = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "SelectAll:"
        )
        assert response == "crashed mid-outpu"

    def test_helper_mirrors_send_audacity_command_consumption(self, pair):
        pair.enqueue_response("x\n", "y\n", "\n")
        via_helper = consume_until_empty_line(pair.read_pipe)
        pair.response_lines.clear()
        pair.enqueue_response("x\n", "y\n", "\n")
        via_command = automate_audacity.send_audacity_command(
            pair.write_pipe, pair.read_pipe, "same-command"
        )
        assert via_helper == via_command
