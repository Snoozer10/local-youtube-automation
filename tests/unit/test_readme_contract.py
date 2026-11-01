"""Regression tests for the offline public README contract checker."""

import tempfile
import unittest
from pathlib import Path

from tools.check_readme import _heading_anchors, validate_repository

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "Snoozer10/local-youtube-automation"


class ReadmeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_public_readme_docs_pass_repository_contract(self):
        self.assertEqual(validate_repository(ROOT), [])

    def test_heading_anchors_preserve_unicode_and_number_duplicates(self):
        lines = [
            (1, "## A heading"),
            (2, "## A heading"),
            (3, "## العَرَبِيَّة"),
            (4, "## A + B"),
        ]

        self.assertEqual(
            _heading_anchors(lines),
            {"a-heading", "a-heading-1", "العَرَبِيَّة", "a--b"},
        )

    def test_generated_duplicate_anchor_skips_existing_suffix_heading(self):
        lines = [(1, "## A"), (2, "## A-1"), (3, "## A")]

        self.assertEqual(_heading_anchors(lines), {"a", "a-1", "a-2"})

    def test_missing_cross_document_anchor_is_reported(self):
        self.make_repository()
        (self.root / "README.md").write_text(
            self.readme("[Quick start](docs/getting-started.md#missing)"),
            encoding="utf-8",
        )

        errors = validate_repository(self.root)

        self.assertTrue(
            any("missing anchor" in error and "'missing'" in error for error in errors)
        )

    def test_links_in_code_fences_are_ignored_and_duplicate_anchor_resolves(self):
        self.make_repository()
        fence = chr(96) * 3
        (self.root / "docs/getting-started.md").write_text(
        f"""# Install

## Repeat

## Repeat

{fence}markdown
[fake](does-not-exist.md#fake)
{fence}
        """,
            encoding="utf-8",
        )
        (self.root / "README.md").write_text(
            self.readme("[Repeated section](docs/getting-started.md#repeat-1)"),
            encoding="utf-8",
        )

        self.assertEqual(validate_repository(self.root), [])

    def test_placeholder_clone_url_is_rejected(self):
        self.make_repository()
        readme = self.readme().replace(
            f"https://github.com/{REPOSITORY}",
            "https://github.com/YOUR-USERNAME/local-youtube-automation",
        )
        (self.root / "README.md").write_text(readme, encoding="utf-8")

        errors = validate_repository(self.root)

        self.assertTrue(any("placeholder clone URL" in error for error in errors))

    def test_python_badge_must_match_package_metadata(self):
        self.make_repository()
        readme = self.readme().replace("Python-3.10%2B", "Python-3.11%2B")
        (self.root / "README.md").write_text(readme, encoding="utf-8")

        errors = validate_repository(self.root)

        self.assertTrue(any("Python support" in error for error in errors))

    def test_local_links_cannot_escape_repository_root(self):
        self.make_repository()
        (self.root / "docs/getting-started.md").write_text(
            "# Install\n\n[Outside](../../../outside.md)\n", encoding="utf-8"
        )

        errors = validate_repository(self.root)

        self.assertTrue(any("escapes the repository" in error for error in errors))

    def make_repository(self):
        (self.root / "docs/agents").mkdir(parents=True)
        (self.root / "docs/getting-started.md").write_text(
            "# Getting started\n", encoding="utf-8"
        )
        (self.root / "docs/agents/setup.md").write_text(
            "# Setup agent\n", encoding="utf-8"
        )
        (self.root / "docs/agents/readme-maintenance.md").write_text(
            "# README maintenance\n", encoding="utf-8"
        )
        (self.root / ".github/workflows").mkdir(parents=True)
        (self.root / ".github/workflows/ci.yml").write_text(
            "name: ci\n", encoding="utf-8"
        )
        (self.root / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.10"\n', encoding="utf-8"
        )
        (self.root / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        (self.root / "README.md").write_text(self.readme(), encoding="utf-8")

    def readme(self, extra=""):
        return f"""# Project

Clone https://github.com/{REPOSITORY}.git

{extra}

[Setup guide](https://github.com/{REPOSITORY}/blob/master/docs/agents/setup.md)

[Same page]()

![CI](https://github.com/{REPOSITORY}/actions/workflows/ci.yml/badge.svg)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)

[![MIT license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
"""


if __name__ == "__main__":
    unittest.main()
