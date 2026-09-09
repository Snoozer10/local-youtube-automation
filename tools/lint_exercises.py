#!/usr/bin/env python3
"""Exercise Linter for Formulative Pedagogy Scaffold.

Enforces structural invariants across all exercise sections and drills:
1. Dash-cased section names: exercises/XX-section-name/
2. Dash-cased exercise names: XX.YY-exercise-name/
3. Presence of at least one variant folder: explainer/, problem/, solution/
4. Non-empty readme.md with zero broken internal links
5. Presence and integrity of required code files (exercise.py, test_exercise.py)
6. Clean exit code: 0 on pass, 1 on validation error with actionable diagnostics
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path
from typing import NamedTuple

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SECTION_PATTERN = re.compile(r"^\d{2}-[a-z0-9]+(-[a-z0-9]+)*$")
EXERCISE_PATTERN = re.compile(r"^(\d{2})\.(\d{2})-[a-z0-9]+(-[a-z0-9]+)*$")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
ALLOWED_VARIANTS = {"explainer", "problem", "solution"}


class LintIssue(NamedTuple):
    path: Path
    message: str
    severity: str = "ERROR"  # "ERROR" or "WARNING"


class ExerciseLintReport:
    def __init__(self) -> None:
        self.sections_checked: int = 0
        self.exercises_checked: int = 0
        self.files_checked: int = 0
        self.links_checked: int = 0
        self.issues: list[LintIssue] = []

    def error(self, path: Path, message: str) -> None:
        self.issues.append(LintIssue(path=path, message=message, severity="ERROR"))

    def warning(self, path: Path, message: str) -> None:
        self.issues.append(LintIssue(path=path, message=message, severity="WARNING"))

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "ERROR" for issue in self.issues)


def validate_markdown_links(markdown_file: Path, report: ExerciseLintReport) -> None:
    """Validates that all local relative links in a markdown file resolve to existing files."""
    try:
        content = markdown_file.read_text(encoding="utf-8")
    except Exception as exc:
        report.error(markdown_file, f"Cannot read file: {exc}")
        return

    base_dir = markdown_file.parent
    for match in MARKDOWN_LINK_PATTERN.finditer(content):
        link_text = match.group(1).strip()
        link_target = match.group(2).strip()

        # Skip web urls, mailto, javascript, or pure page anchors
        if any(link_target.startswith(prefix) for prefix in ("http://", "https://", "mailto:", "ftp://", "#")):
            continue

        if link_target.startswith("file:///"):
            report.links_checked += 1
            raw_path = link_target[len("file:///") :]
            clean_path = urllib.parse.unquote(raw_path)
            target_path = Path(clean_path).resolve()
            if not target_path.exists():
                report.error(
                    markdown_file,
                    f"Broken file link '{link_target}' (text: '{link_text}') -> path '{target_path}' does not exist",
                )
            continue

        # Strip internal page anchors, e.g. path/to/file.md#heading
        target_file_part = link_target.split("#", 1)[0].strip()
        if not target_file_part:
            continue

        report.links_checked += 1
        # Resolve target relative to the markdown file's directory
        resolved_path = (base_dir / target_file_part).resolve()

        if not resolved_path.exists():
            report.error(
                markdown_file,
                f"Broken link '{link_target}' (text: '{link_text}') -> path '{resolved_path}' does not exist",
            )


def lint_exercise(
    exercise_dir: Path,
    expected_section_prefix: str,
    report: ExerciseLintReport,
) -> None:
    """Lints an individual exercise directory."""
    report.exercises_checked += 1
    dir_name = exercise_dir.name

    match = EXERCISE_PATTERN.match(dir_name)
    if not match:
        report.error(
            exercise_dir,
            f"Exercise directory '{dir_name}' does not conform to pattern 'XX.YY-exercise-name' "
            f"(lowercase dash-cased alphanumeric words with 2-digit numbers)",
        )
        return

    section_prefix = match.group(1)
    if section_prefix != expected_section_prefix:
        report.error(
            exercise_dir,
            f"Exercise prefix '{section_prefix}' does not match enclosing section prefix '{expected_section_prefix}'",
        )

    # Check for presence of variant folders
    child_dirs = {d.name: d for d in exercise_dir.iterdir() if d.is_dir() and not d.name.startswith(".")}
    variants_present = set(child_dirs.keys()) & ALLOWED_VARIANTS

    if not variants_present:
        report.error(
            exercise_dir,
            f"Missing required variant folder in '{dir_name}'. Must contain at least one of: "
            f"{', '.join(sorted(ALLOWED_VARIANTS))}",
        )

    # Check for non-empty readme.md
    readme_path = exercise_dir / "readme.md"
    readme_alt = exercise_dir / "README.md"
    target_readme = readme_path if readme_path.exists() else (readme_alt if readme_alt.exists() else None)

    if not target_readme:
        report.error(exercise_dir, "Missing required 'readme.md' documentation file")
    else:
        report.files_checked += 1
        if target_readme.stat().st_size == 0:
            report.error(target_readme, "'readme.md' file is empty (0 bytes)")
        else:
            validate_markdown_links(target_readme, report)

    # Check problem/ variant if present
    if "problem" in variants_present:
        problem_dir = child_dirs["problem"]
        code_file = problem_dir / "exercise.py"
        if not code_file.exists():
            report.error(problem_dir, "Missing 'exercise.py' workspace file in problem/ variant")
        else:
            report.files_checked += 1
            if code_file.stat().st_size == 0:
                report.error(code_file, "Problem 'exercise.py' is empty")
            else:
                content = code_file.read_text(encoding="utf-8")
                if "# TODO" not in content:
                    report.error(
                        code_file,
                        "Problem 'exercise.py' must contain at least one '# TODO' instruction block",
                    )

    # Check solution/ variant if present
    if "solution" in variants_present:
        solution_dir = child_dirs["solution"]
        sol_code = solution_dir / "exercise.py"
        sol_test = solution_dir / "test_exercise.py"

        if not sol_code.exists():
            report.error(solution_dir, "Missing reference 'exercise.py' in solution/ variant")
        else:
            report.files_checked += 1
            if sol_code.stat().st_size == 0:
                report.error(sol_code, "Solution 'exercise.py' is empty")

        if not sol_test.exists():
            report.error(solution_dir, "Missing test suite 'test_exercise.py' in solution/ variant")
        else:
            report.files_checked += 1
            if sol_test.stat().st_size == 0:
                report.error(sol_test, "Solution 'test_exercise.py' is empty")

    # Check explainer/ variant if present
    if "explainer" in variants_present:
        explainer_dir = child_dirs["explainer"]
        # Explainer can have readme.md, explainer.md, or code
        explainer_files = [f for f in explainer_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
        if not explainer_files:
            report.error(explainer_dir, "Explainer folder is empty; expected documentation or walkthrough file")
        else:
            for f in explainer_files:
                report.files_checked += 1
                if f.suffix.lower() == ".md":
                    validate_markdown_links(f, report)


def lint_section(section_dir: Path, report: ExerciseLintReport) -> None:
    """Lints a curriculum section directory."""
    report.sections_checked += 1
    dir_name = section_dir.name

    if not SECTION_PATTERN.match(dir_name):
        report.error(
            section_dir,
            f"Section directory '{dir_name}' does not conform to pattern 'XX-section-name' "
            f"(2-digit prefix followed by dash-cased alphanumeric words)",
        )
        return

    expected_prefix = dir_name.split("-", 1)[0]

    exercise_dirs = [d for d in section_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not exercise_dirs:
        report.error(section_dir, f"Section '{dir_name}' contains no exercise subdirectories")
        return

    for ex_dir in sorted(exercise_dirs):
        lint_exercise(ex_dir, expected_prefix, report)


def lint_all_exercises(exercises_root: Path) -> ExerciseLintReport:
    """Validates the entire exercises hierarchy."""
    report = ExerciseLintReport()

    if not exercises_root.exists() or not exercises_root.is_dir():
        report.error(exercises_root, f"Exercises directory not found at '{exercises_root}'")
        return report

    section_dirs = [d for d in exercises_root.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not section_dirs:
        report.error(exercises_root, f"No curriculum sections found in '{exercises_root}'")
        return report

    for sec_dir in sorted(section_dirs):
        lint_section(sec_dir, report)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint and validate curriculum exercise scaffold.")
    parser.add_argument(
        "--exercises-dir",
        type=Path,
        default=None,
        help="Path to the exercises directory (defaults to exercises/ in repository root).",
    )
    args = parser.parse_args()

    if args.exercises_dir:
        exercises_dir = args.exercises_dir.resolve()
    else:
        # Default relative to this tool's location or cwd
        base_path = Path(__file__).resolve().parent.parent
        exercises_dir = base_path / "exercises"

    print("=" * 70)
    print("Formulative Pedagogy Scaffold & Drill Linter")
    print(f"Target Directory: {exercises_dir}")
    print("=" * 70)

    report = lint_all_exercises(exercises_dir)

    print(f"Sections Checked : {report.sections_checked}")
    print(f"Exercises Checked: {report.exercises_checked}")
    print(f"Files Validated  : {report.files_checked}")
    print(f"Links Verified   : {report.links_checked}")
    print("-" * 70)

    if report.issues:
        error_count = sum(1 for i in report.issues if i.severity == "ERROR")
        warning_count = sum(1 for i in report.issues if i.severity == "WARNING")
        print(f"FAILED: Found {error_count} error(s) and {warning_count} warning(s):\n")

        for issue in report.issues:
            badge = "[ERROR]" if issue.severity == "ERROR" else "[WARN]"
            try:
                rel_path = issue.path.relative_to(exercises_dir.parent)
            except ValueError:
                rel_path = issue.path
            print(f"  {badge} {rel_path}")
            print(f"     -> {issue.message}\n")

        return 1 if report.has_errors else 0

    print("[SUCCESS] ALL EXERCISE SECTIONS & DRILLS PASSED STRUCTURAL VALIDATION")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
