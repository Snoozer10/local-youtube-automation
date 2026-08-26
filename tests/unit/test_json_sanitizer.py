import pytest

from json_sanitizer import clean_and_repair_json


def test_tier1_direct_parse_of_fenced_array():
    raw = '```json\n[{"index":1,"visual_prompt":{"subject_details":"x"}}]\n```'
    assert clean_and_repair_json(raw) == [{"index": 1, "visual_prompt": {"subject_details": "x"}}]


def test_tier2_repairs_unescaped_inner_quotes():
    raw = (
        '[{"index": 1, "visual_prompt": '
        '{"subject_details": "Ahmed holding a "plastic cup" of tea"}}]'
    )
    result = clean_and_repair_json(raw)
    assert result[0]["visual_prompt"]["subject_details"] == 'Ahmed holding a "plastic cup" of tea'


def test_tier3_closes_truncated_array_with_trailing_comma():
    raw = '[{"index": 1},{"index": 2},'
    assert clean_and_repair_json(raw) == [{"index": 1}, {"index": 2}]


def test_tier4_salvages_objects_from_destroyed_array():
    raw = 'Junk {"index": 1, "visual_prompt": {}} mid {"index": 2, "visual_prompt": {}} end'
    assert clean_and_repair_json(raw) == [
        {"index": 1, "visual_prompt": {}},
        {"index": 2, "visual_prompt": {}},
    ]


def test_nested_braces_inside_strings_do_not_corrupt_scanner():
    raw = 'noise {"index": 1, "text": "use {curly} braces"} tail {"index": 2}'
    assert clean_and_repair_json(raw) == [
        {"index": 1, "text": "use {curly} braces"},
        {"index": 2},
    ]


def test_tier4_drops_objects_without_index_key():
    raw = 'junk {"label": "a"} mid {"index": 2} end'
    assert clean_and_repair_json(raw) == [{"index": 2}]


def test_total_garbage_raises_value_error():
    with pytest.raises(ValueError, match="Failed to extract valid JSON structures"):
        clean_and_repair_json("hello world no json")


def test_newline_delimited_bare_objects_are_salvaged():
    raw = '{"index": 1}\n{"index": 2}'
    assert clean_and_repair_json(raw) == [{"index": 1}, {"index": 2}]


def test_bare_list_without_fences_parses_directly():
    assert clean_and_repair_json('[{"index": 1}]') == [{"index": 1}]


def test_prose_wrapped_array_parses_after_preclean():
    raw = 'Here is the JSON: [{"index": 1, "note": "done"}] hope it helps'
    assert clean_and_repair_json(raw) == [{"index": 1, "note": "done"}]
