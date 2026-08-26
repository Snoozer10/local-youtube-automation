"""Four-tier repair ladder for LLM responses containing storyboard JSON arrays."""

import json
import re
from typing import Any

_FENCE_LINE = re.compile(r"^[ \t]*```(?:json)?[ \t]*$", re.MULTILINE | re.IGNORECASE)
_INNER_QUOTE = re.compile(r'(?<=:\s")([^"\\]*?)"([^"\\]*?)"(?=[\s,}])')
_TRAILING_COMMA = re.compile(r",\s*([\]}])")

_ERROR_MESSAGE = "Failed to extract valid JSON structures from model response."


def _strip_markdown_fences(text: str) -> str:
    first = _FENCE_LINE.search(text)
    if first is None:
        return text
    body = text[first.end() :]
    last: re.Match[str] | None = None
    for match in _FENCE_LINE.finditer(body):
        last = match
    if last is not None:
        body = body[: last.start()]
    return body


def _trim_surrounding_prose(text: str) -> str:
    open_positions = [position for position in (text.find("["), text.find("{")) if position >= 0]
    if not open_positions:
        return text
    start = min(open_positions)
    close_positions = [
        position for position in (text.rfind("]"), text.rfind("}")) if position >= start
    ]
    end = max(close_positions) if close_positions else len(text) - 1
    return text[start : end + 1]


def _pre_clean(raw_text: str) -> str:
    return _trim_surrounding_prose(_strip_markdown_fences(raw_text))


def _replace_inner_quotes(match: re.Match[str]) -> str:
    return f'{match.group(1)}\\"{match.group(2)}\\"'


def _fix_inner_quotes(text: str) -> str:
    return _INNER_QUOTE.sub(_replace_inner_quotes, text)


def _strip_trailing_commas(text: str) -> str:
    return _TRAILING_COMMA.sub(r"\1", text)


def _close_unclosed_array(text: str) -> str:
    if text.startswith("[") and not text.rstrip().endswith("]"):
        return text.rstrip() + "]"
    return text


def _try_parse(text: str) -> list[dict[str, Any]] | None:
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    if not isinstance(parsed, list):
        return None
    dict_entries = [entry for entry in parsed if isinstance(entry, dict)]
    return dict_entries or None


def _balance_brackets(text: str) -> str:
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if escaped:
            escaped = False
            continue
        if in_string:
            if char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            stack.append(char)
        elif char in "]}" and stack:
            stack.pop()
    closers = '"' if in_string else ""
    closers += "".join("]" if opener == "[" else "}" for opener in reversed(stack))
    return text + closers


def _extract_top_level_objects(text: str) -> list[str]:
    chunks: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "{":
            index += 1
            continue
        depth = 0
        in_string = False
        escaped = False
        cursor = index
        end = -1
        while cursor < length:
            char = text[cursor]
            if escaped:
                escaped = False
            elif in_string:
                if char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = cursor
                    break
            cursor += 1
        if end == -1:
            index += 1
            continue
        chunks.append(text[index : end + 1])
        index = end + 1
    return chunks


def _salvage_indexed_objects(text: str) -> list[dict[str, Any]]:
    salvaged: list[dict[str, Any]] = []
    for chunk in _extract_top_level_objects(text):
        try:
            parsed = json.loads(_fix_inner_quotes(chunk))
        except ValueError:
            continue
        if isinstance(parsed, dict) and "index" in parsed:
            salvaged.append(parsed)
    return salvaged


def clean_and_repair_json(raw_text: str) -> list[dict[str, Any]]:
    cleaned = _pre_clean(raw_text)

    direct = _try_parse(cleaned)
    if direct is not None:
        return direct

    quote_fixed = _fix_inner_quotes(cleaned)
    tier_two = _try_parse(_strip_trailing_commas(_close_unclosed_array(quote_fixed)))
    if tier_two is not None:
        return tier_two

    tier_three = _try_parse(_strip_trailing_commas(_balance_brackets(quote_fixed)))
    if tier_three is not None:
        return tier_three

    salvaged = _salvage_indexed_objects(cleaned)
    if salvaged:
        return salvaged

    raise ValueError(_ERROR_MESSAGE)
