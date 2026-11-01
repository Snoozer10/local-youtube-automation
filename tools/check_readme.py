"""Check the README's small, public, local documentation contract."""

from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPOSITORY = "Snoozer10/local-youtube-automation"
PUBLIC_DOCS = (
    "README.md",
    "docs/getting-started.md",
    "docs/agents/setup.md",
    "docs/agents/readme-maintenance.md",
)
INLINE_LINK = re.compile(r"!?\[([^\]]*)\]\(([^)]+)\)")
ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile("^ {0,3}([" + chr(96) + "~]{3,})")


def slugify_heading(heading: str) -> str:
    """Return the GitHub-style fragment used by ordinary ATX headings."""
    heading = html.unescape(heading)
    heading = re.sub(r"\[([^]]*)\]\([^)]*\)", r"\1", heading)
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = heading.lower()
    slug = "".join(
        char
        for char in heading
        if char.isalnum()
        or char in "-_ "
        or unicodedata.category(char).startswith("M")
    )
    return slug.replace(" ", "-")


def _without_fenced_code(text: str) -> list[tuple[int, str]]:
    """Return (line number, Markdown line) pairs outside fenced code blocks."""
    result: list[tuple[int, str]] = []
    fence_char: str | None = None
    fence_length = 0
    for number, line in enumerate(text.splitlines(), start=1):
        match = FENCE.match(line)
        if fence_char is None:
            if match:
                marker = match.group(1)
                fence_char, fence_length = marker[0], len(marker)
            else:
                result.append((number, line))
        elif match:
            marker = match.group(1)
            if marker[0] == fence_char and len(marker) >= fence_length:
                fence_char = None
                fence_length = 0
    return result


def _heading_anchors(lines: list[tuple[int, str]]) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for _, line in lines:
        heading = ATX_HEADING.match(line)
        if not heading:
            continue
        base = slugify_heading(heading.group(2))
        if not base:
            continue
        candidate = base
        while candidate in anchors:
            count = counts.get(base, 0) + 1
            counts[base] = count
            candidate = f"{base}-{count}"
        counts.setdefault(base, 0)
        anchors.add(candidate)
    return anchors


def _markdown_targets(lines: list[tuple[int, str]]):
    for line_number, line in lines:
        index = 0
        while index < len(line):
            opening = line.find("[", index)
            if opening < 0:
                break
            depth = 0
            closing = opening
            while closing < len(line):
                if line[closing] == "[":
                    depth += 1
                elif line[closing] == "]":
                    depth -= 1
                    if depth == 0:
                        break
                closing += 1
            if depth or closing + 1 >= len(line) or line[closing + 1] != "(":
                index = opening + 1
                continue

            label = line[opening + 1 : closing]
            target_start = closing + 2
            target_end = target_start
            paren_depth = 0
            while target_end < len(line):
                if line[target_end] == "(":
                    paren_depth += 1
                elif line[target_end] == ")":
                    if paren_depth == 0:
                        break
                    paren_depth -= 1
                target_end += 1
            if target_end == len(line):
                index = closing + 1
                continue

            raw_target = line[target_start:target_end].strip()
            if raw_target.startswith("<") and ">" in raw_target:
                target = raw_target[1 : raw_target.index(">")]
            else:
                target = raw_target.split(maxsplit=1)[0] if raw_target else ""
            yield line_number, label, target
            if "[" in label:
                yield from _markdown_targets([(line_number, label)])
            index = target_end + 1


def _check_document(root: Path, relative: str) -> list[str]:
    source = root / relative
    if not source.is_file():
        return [f"{relative}:1: required document is missing"]
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{relative}:1: cannot read UTF-8 Markdown: {exc}"]

    lines = _without_fenced_code(text)
    errors: list[str] = []
    for line_number, _, target in _markdown_targets(lines):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue

        decoded_path = unquote(parsed.path)
        if decoded_path:
            destination = (source.parent / decoded_path).resolve()
            try:
                destination.relative_to(root.resolve())
            except ValueError:
                errors.append(
                    f"{relative}:{line_number}: local target escapes the repository: {target}"
                )
                continue
            if not destination.is_file() and not destination.is_dir():
                errors.append(f"{relative}:{line_number}: missing local target: {target}")
                continue
        else:
            destination = source

        if parsed.fragment:
            try:
                target_text = destination.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                errors.append(
                    f"{relative}:{line_number}: cannot read fragment target: {target}"
                )
                continue
            target_pairs = (
                lines if destination == source else _without_fenced_code(target_text)
            )
            fragment = unquote(parsed.fragment)
            if fragment not in _heading_anchors(target_pairs):
                errors.append(
                    f"{relative}:{line_number}: missing anchor "
                    f"'{fragment}' in {destination.relative_to(root.resolve())}"
                )
    return errors


def _python_minimum(root: Path) -> tuple[int, int] | None:
    metadata = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"""(?m)^\s*requires-python\s*=\s*['"]([^'"]+)""", metadata)
    if not match:
        return None
    minimum = re.search(r">=\s*(\d+)\.(\d+)", match.group(1))
    return (int(minimum.group(1)), int(minimum.group(2))) if minimum else None


def _check_readme_metadata(root: Path) -> list[str]:
    relative = "README.md"
    path = root / relative
    if not path.is_file():
        return [f"{relative}:1: required document is missing"]
    text = path.read_text(encoding="utf-8")
    lines = _without_fenced_code(text)
    errors: list[str] = []
    plain_text = text
    if f"https://github.com/{REPOSITORY}" not in plain_text:
        errors.append(f"{relative}:1: include the canonical clone URL")
    if "YOUR-USERNAME" in plain_text:
        errors.append(f"{relative}:1: remove the placeholder clone URL")
    if f"https://github.com/{REPOSITORY}/blob/master/docs/agents/setup.md" not in plain_text:
        errors.append(f"{relative}:1: copy/paste setup prompt must link to the full agent guide")

    ci_badge = f"https://github.com/{REPOSITORY}/actions/workflows/ci.yml/badge.svg"
    if not any(target.startswith(ci_badge) for _, _, target in _markdown_targets(lines)):
        errors.append(f"{relative}:1: include an image badge for the current CI workflow")
    if not (root / ".github/workflows/ci.yml").is_file():
        errors.append(".github/workflows/ci.yml:1: CI badge target does not exist")

    python_badges = [
        target
        for _, label, target in _markdown_targets(lines)
        if label.lower().startswith("python")
        and "img.shields.io/badge/python-" in target.lower()
    ]
    minimum = _python_minimum(root)
    if minimum is None:
        errors.append("pyproject.toml:1: cannot parse a >= Python support minimum")
    else:
        supported = False
        for target in python_badges:
            decoded = unquote(target)
            version = re.search(r"/badge/Python-(\d+)\.(\d+)\+[-/]", decoded, re.I)
            if version and tuple(map(int, version.groups())) == minimum:
                supported = True
        if not supported:
            errors.append(
                f"{relative}:1: Python support badge must match pyproject.toml >= "
                f"{minimum[0]}.{minimum[1]}"
            )

    license_links = [
        target
        for _, label, target in _markdown_targets(lines)
        if "license" in label.lower()
    ]
    if not any(
        target == "LICENSE" and (root / target).is_file() for target in license_links
    ):
        errors.append(f"{relative}:1: include a working local license link")
    elif "MIT License" not in (root / "LICENSE").read_text(encoding="utf-8"):
        errors.append("LICENSE:1: expected MIT license text")
    return errors


def validate_repository(root: Path) -> list[str]:
    """Return line-addressed local-link and README-contract failures."""
    root = root.resolve()
    errors = [
        error
        for relative in PUBLIC_DOCS
        for error in _check_document(root, relative)
    ]
    errors.extend(_check_readme_metadata(root))
    return sorted(errors)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate_repository(root)
    if errors:
        print("README documentation check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"README documentation check passed ({len(PUBLIC_DOCS)} documents checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
