"""Unit tests for the proportionate repository secret scanning gate."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import tools

    if hasattr(tools, "__path__") and str(ROOT / "tools") not in tools.__path__:
        tools.__path__.insert(0, str(ROOT / "tools"))
except ImportError:
    pass

from tools.check_secrets import (  # noqa: E402
    ScanError,
    load_allowlist,
    main,
    mask_secret,
    sanitize_path,
    scan_file,
    scan_repository,
)


class SecretScanningGateTests(unittest.TestCase):
    """Test suite for tools/check_secrets.py."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.allowlist = load_allowlist(ROOT / "tools" / "secrets_allowlist.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _remove_git_dir(self, path: Path) -> None:
        """Helper to safely remove Git repository directory on Windows."""

        def _on_error(func: Any, p: str, _exc_info: Any) -> None:
            os.chmod(p, stat.S_IWRITE)
            func(p)

        if path.exists():
            shutil.rmtree(path, onerror=_on_error)

    def test_clean_repository_passes_secret_scanning_gate(self) -> None:
        """Verify the tracked repository baseline has 0 secret findings."""
        findings = scan_repository(ROOT, allowlist=self.allowlist)
        self.assertEqual(
            findings,
            [],
            f"Expected 0 secret findings in repository, got {len(findings)}: {findings}",
        )

    def test_detects_telegram_bot_token(self) -> None:
        """Verify synthetic Telegram bot tokens are detected and masked."""
        test_file = self.root / "sample.py"
        test_file.write_text(
            'token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "telegram_bot_token")
        self.assertEqual(findings[0].line_number, 1)
        diag = findings[0].format_diagnostic()
        self.assertEqual(diag, "sample.py:1: [telegram_bot_token] potential secret token detected")
        self.assertNotIn("AAFl1234567890abcdefghijklmnopqrstuv", diag)

    def test_detects_aws_access_key(self) -> None:
        """Verify synthetic AWS access key identifiers are detected."""
        test_file = self.root / "config.env"
        test_file.write_text(
            "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF\n",  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "aws_access_key")
        diag = findings[0].format_diagnostic()
        self.assertEqual(diag, "config.env:1: [aws_access_key] potential secret token detected")
        self.assertNotIn("AKIA1234567890ABCDEF", diag)  # pragma: allowlist secret

    def test_detects_aws_secret_key(self) -> None:
        """Verify synthetic AWS secret access key assignments are detected."""
        test_file = self.root / "aws_creds.py"
        test_file.write_text(
            'aws_secret_access_key = "1234567890abcdef1234567890abcdef12345678"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "aws_secret_key")

    def test_detects_github_personal_access_token(self) -> None:
        """Verify synthetic GitHub personal access tokens are detected."""
        test_file = self.root / "auth.json"
        test_file.write_text(
            '{"token": "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"}\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "github_token")

    def test_detects_private_key_block(self) -> None:
        """Verify synthetic private key blocks are detected."""
        test_file = self.root / "id_rsa"
        test_file.write_text(
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----\n",  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "private_key_block")

    def test_detects_slack_token(self) -> None:
        """Verify synthetic Slack bot/user tokens are detected."""
        test_file = self.root / "slack.py"
        slack_prefix = "xoxb"
        test_file.write_text(
            f'SLACK_TOKEN = "{slack_prefix}-123456789012-3456789012345-abcdefghijklmnopqrstuvwx"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "slack_token")

    def test_detects_generic_api_key_assignment(self) -> None:
        """Verify generic API key assignments with long tokens are detected."""
        test_file = self.root / "service.py"
        test_file.write_text(
            'client_secret = "secret_value_1234567890_abcdefghijklmnopqrstuvwxyz"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "generic_api_key_assignment")

    def test_detects_secrets_in_markdown_documentation(self) -> None:
        """Verify synthetic secrets in markdown documentation are caught."""
        doc_file = self.root / "guide.md"
        doc_file.write_text(
            "# Setup Guide\n\n"
            "Run this command with your live bot token:\n"
            "curl -s https://api.telegram.org/bot9876543210:AAFl1234567890abcdefghijklmnopqrstuv/getMe\n",  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(doc_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "telegram_bot_token")
        self.assertEqual(findings[0].line_number, 4)
        self.assertEqual(findings[0].path, "guide.md")
        diag = findings[0].format_diagnostic()
        self.assertEqual(diag, "guide.md:4: [telegram_bot_token] potential secret token detected")
        self.assertNotIn("AAFl", diag)

    def test_detects_aws_credentials_in_documentation(self) -> None:
        """Verify synthetic AWS credentials in documentation are caught."""
        doc_file = self.root / "deploy.md"
        doc_file.write_text(
            "# Deployment Guide\n\n"
            "Set your production credentials:\n"
            "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF\n",  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(doc_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "aws_access_key")
        self.assertEqual(findings[0].line_number, 4)

    def test_respects_reviewed_allowed_patterns(self) -> None:
        """Verify documented placeholder patterns in allowlist pass cleanly."""
        test_file = self.root / "doc.md"
        test_file.write_text(
            "Example: export TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN\n"
            "AWS sample key: AKIAIOSFODNN7EXAMPLE\n"
            "Placeholder: 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_1234567\n"
            "Redacted marker: [redacted]\n",
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(findings, [])

    def test_respects_inline_pragma_annotations(self) -> None:
        """Verify inline pragma annotations suppress detection on specific lines."""
        test_file = self.root / "test_inline.py"
        test_file.write_text(
            'token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"  # pragma: allowlist secret\n'  # pragma: allowlist secret
            'key = "AKIA1234567890ABCDEF"  # noqa: secret-check\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(findings, [])

    def test_respects_html_comment_pragma_in_markdown(self) -> None:
        """Verify HTML comment pragma suppresses secret detection in markdown."""
        doc_file = self.root / "docs_with_secret.md"
        doc_file.write_text(
            "# Documentation with documented fixture\n\n"
            "token = 9876543210:AAFl1234567890abcdefghijklmnopqrstuv <!-- pragma: allowlist secret -->\n",  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(doc_file, self.allowlist, root=self.root)
        self.assertEqual(findings, [])

    def test_respects_path_specific_allowlists(self) -> None:
        """Verify targeted path-specific exclusions apply only to the specified file."""
        config = {
            "excluded_paths": [],
            "excluded_extensions": [],
            "allowed_patterns": [],
            "path_specific_allowlists": {
                "docs/special.md": ["AKIA1234567890ABCDEF"],  # pragma: allowlist secret
            },
        }

        special_file = self.root / "docs" / "special.md"
        special_file.parent.mkdir(parents=True, exist_ok=True)
        special_file.write_text(
            "Key: AKIA1234567890ABCDEF\n",  # pragma: allowlist secret
            encoding="utf-8",
        )

        other_file = self.root / "docs" / "other.md"
        other_file.write_text(
            "Key: AKIA1234567890ABCDEF\n",  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings_special = scan_file(special_file, config, root=self.root)
        self.assertEqual(findings_special, [])

        findings_other = scan_file(other_file, config, root=self.root)
        self.assertEqual(len(findings_other), 1)
        self.assertEqual(findings_other[0].rule_name, "aws_access_key")

    def test_respects_excluded_paths(self) -> None:
        """Verify files in excluded paths are skipped."""
        runtime_dir = self.root / ".runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        ignored_file = runtime_dir / "temp_leak.txt"
        ignored_file.write_text(
            "AKIA1234567890ABCDEF\n",  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(ignored_file, self.allowlist, root=self.root)
        self.assertEqual(findings, [])

    def test_respects_excluded_binary_extensions(self) -> None:
        """Verify binary extensions are skipped without scanning."""
        img_file = self.root / "image.png"
        img_file.write_bytes(b"AKIA1234567890ABCDEF")  # pragma: allowlist secret

        findings = scan_file(img_file, self.allowlist, root=self.root)
        self.assertEqual(findings, [])

    def test_mask_secret_helper(self) -> None:
        """Verify mask_secret helper redacts middle bytes."""
        short_val = "1234"
        self.assertEqual(mask_secret(short_val), "[REDACTED]")

        long_val = "1234567890abcdef"
        masked = mask_secret(long_val)
        self.assertEqual(masked, "1234...[REDACTED]...cdef")
        self.assertNotIn("567890ab", masked)

    def test_cli_exit_codes(self) -> None:
        """Verify CLI returns exit code 0 on clean scan and 1 on secret finding."""
        clean_file = self.root / "clean.py"
        clean_file.write_text("print('clean')\n", encoding="utf-8")

        # Clean scan returns 0
        ret_clean = main(["--root", str(self.root), str(clean_file)])
        self.assertEqual(ret_clean, 0)

        # Dirty scan returns 1
        dirty_file = self.root / "dirty.py"
        dirty_file.write_text(
            'token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )
        ret_dirty = main(["--root", str(self.root), str(dirty_file)])
        self.assertEqual(ret_dirty, 1)

    # ------------------------------------------------------------------
    # Codex Audit Item 1: NUL-delimited Git paths & Arabic/non-ASCII preservation
    # ------------------------------------------------------------------
    def test_detects_secrets_in_arabic_and_non_ascii_git_paths(self) -> None:
        """Verify tracked files with Arabic names are preserved verbatim without quoting and scanned."""
        repo_dir = self.root / "arabic_repo"
        repo_dir.mkdir()
        try:
            subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
            arabic_filename = "ملف_بيانات_سري.py"
            secret_file = repo_dir / arabic_filename
            secret_file.write_text(
                'token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"\n',  # pragma: allowlist secret
                encoding="utf-8",
            )
            subprocess.run(["git", "add", arabic_filename], cwd=repo_dir, check=True)

            findings = scan_repository(repo_dir, allowlist=self.allowlist)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].rule_name, "telegram_bot_token")
            self.assertEqual(findings[0].path, arabic_filename)

            # Also verify clean Arabic file passes
            secret_file.write_text("print('مرحبا بالعالم')\n", encoding="utf-8")
            subprocess.run(["git", "add", arabic_filename], cwd=repo_dir, check=True)
            clean_findings = scan_repository(repo_dir, allowlist=self.allowlist)
            self.assertEqual(clean_findings, [])
        finally:
            self._remove_git_dir(repo_dir)

    # ------------------------------------------------------------------
    # Codex Audit Item 2: Individual match allowlists & pragma scoping
    # ------------------------------------------------------------------
    def test_line_level_placeholder_does_not_suppress_adjacent_secret(self) -> None:
        """Verify a placeholder like [redacted] on a line does not suppress a real secret on that line."""
        test_file = self.root / "adjacent.py"
        test_file.write_text(
            'api_key = "secret_value_1234567890_abcdefghijklmnopqrstuvwxyz"  # previous was [redacted]\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "generic_api_key_assignment")

    def test_placeholder_as_secret_value_is_allowed(self) -> None:
        """Verify placeholder tokens themselves pass when used as the matched value."""
        test_file = self.root / "placeholder_val.py"
        test_file.write_text(
            'api_key = "your-api-key"\nsecret_key = "[redacted]"\n',
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(findings, [])

    def test_rule_scoped_pragma_exemption(self) -> None:
        """Verify pragma scoped to a matching rule suppresses detection."""
        test_file = self.root / "scoped_pragma.py"
        test_file.write_text(
            'api_key = "secret_value_1234567890_abcdefghijklmnopqrstuvwxyz"  # pragma: allowlist secret: generic_api_key_assignment\n'  # pragma: allowlist secret
            'token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"  # noqa: secret-check(telegram_bot_token)\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(findings, [])

    def test_unmatched_rule_scoped_pragma_does_not_exempt(self) -> None:
        """Verify pragma scoped to a different rule does not suppress an unmatched secret."""
        test_file = self.root / "mismatched_pragma.py"
        test_file.write_text(
            'api_key = "secret_value_1234567890_abcdefghijklmnopqrstuvwxyz"  # pragma: allowlist secret: aws_access_key\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "generic_api_key_assignment")

    # ------------------------------------------------------------------
    # Codex Audit Item 3: Bound to declared inputs, ScanError on failure
    # ------------------------------------------------------------------
    def test_git_enumeration_failure_raises_scan_error_and_does_not_scan_untracked(self) -> None:
        """Verify Git enumeration failure raises ScanError and does not fall back to scanning untracked files."""
        # Non-git folder with untracked .env containing secret
        env_file = self.root / ".env"
        env_file.write_text(
            'API_TOKEN="secret_value_1234567890_abcdefghijklmnopqrstuvwxyz"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        with self.assertRaises(ScanError) as ctx:
            scan_repository(self.root, allowlist=self.allowlist)
        self.assertIn("Git enumeration failed", str(ctx.exception))

    def test_target_path_outside_repository_raises_scan_error(self) -> None:
        """Verify specifying a target path outside the repository root raises ScanError."""
        outside_file = self.root.parent / "outside_leak.py"
        outside_file.write_text("print('outside')\n", encoding="utf-8")
        try:
            with self.assertRaises(ScanError) as ctx:
                scan_repository(self.root, allowlist=self.allowlist, files=[outside_file])
            self.assertIn("outside repository root", str(ctx.exception))
        finally:
            if outside_file.exists():
                outside_file.unlink()

    def test_nonexistent_target_path_raises_scan_error(self) -> None:
        """Verify specifying a non-existent target path raises ScanError."""
        missing = self.root / "does_not_exist.py"
        with self.assertRaises(ScanError) as ctx:
            scan_repository(self.root, allowlist=self.allowlist, files=[missing])
        self.assertIn("does not exist", str(ctx.exception))

    def test_missing_tracked_input_raises_scan_error(self) -> None:
        """Verify missing tracked file on disk raises ScanError rather than reporting clean."""
        repo_dir = self.root / "missing_tracked_repo"
        repo_dir.mkdir()
        try:
            subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
            file_path = repo_dir / "tracked.py"
            file_path.write_text("print('tracked')\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.py"], cwd=repo_dir, check=True)
            # Remove file from disk without git rm
            file_path.unlink()

            with self.assertRaises(ScanError) as ctx:
                scan_repository(repo_dir, allowlist=self.allowlist)
            self.assertIn("Tracked input missing on disk", str(ctx.exception))
        finally:
            self._remove_git_dir(repo_dir)

    def test_cli_exit_code_2_on_scan_error(self) -> None:
        """Verify CLI returns exit code 2 when a ScanError occurs."""
        missing = self.root / "missing_cli.py"
        ret = main(["--root", str(self.root), str(missing)])
        self.assertEqual(ret, 2)

    # ------------------------------------------------------------------
    # Codex Audit Item 4: UTF-16, unquoted assignments, quoted JSON keys
    # ------------------------------------------------------------------
    def test_detects_secrets_in_utf16_text(self) -> None:
        """Verify secrets in UTF-16 with BOM and UTF-16 LE without BOM are detected."""
        # UTF-16 with BOM
        utf16_bom_file = self.root / "secret_bom.txt"
        content = 'api_key = "secret_value_1234567890_abcdefghijklmnopqrstuvwxyz"\n'  # pragma: allowlist secret
        utf16_bom_file.write_bytes(content.encode("utf-16"))

        findings_bom = scan_file(utf16_bom_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings_bom), 1)
        self.assertEqual(findings_bom[0].rule_name, "generic_api_key_assignment")

        # UTF-16 LE without BOM
        utf16_nobom_file = self.root / "secret_nobom.txt"
        utf16_nobom_file.write_bytes(content.encode("utf-16-le"))

        findings_nobom = scan_file(utf16_nobom_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings_nobom), 1)
        self.assertEqual(findings_nobom[0].rule_name, "generic_api_key_assignment")

    def test_detects_unquoted_api_token_assignment(self) -> None:
        """Verify unquoted API_TOKEN=value assignments are detected."""
        test_file = self.root / "unquoted.env"
        test_file.write_text(
            "API_TOKEN=secret_value_1234567890_abcdefghijklmnopqrstuvwxyz\n",  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "generic_api_key_assignment")

    def test_detects_quoted_json_credential_keys(self) -> None:
        """Verify quoted JSON credential keys are detected."""
        test_file = self.root / "creds.json"
        test_file.write_text(
            "{\n"
            '  "aws_secret_access_key": "1234567890abcdef1234567890abcdef12345678",\n'  # pragma: allowlist secret
            '  "api_key": "secret_value_1234567890_abcdefghijklmnopqrstuvwxyz"\n'  # pragma: allowlist secret
            "}\n",
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        rules = {f.rule_name for f in findings}
        self.assertIn("aws_secret_key", rules)
        self.assertIn("generic_api_key_assignment", rules)

    # ------------------------------------------------------------------
    # Codex Audit Item 5: Safe diagnostic format without credential fragments
    # ------------------------------------------------------------------
    def test_diagnostic_format_emits_no_secret_fragments(self) -> None:
        """Verify format_diagnostic emits strictly safe path:line and rule name."""
        test_file = self.root / "token.py"
        test_file.write_text(
            'token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        diag = findings[0].format_diagnostic()
        self.assertEqual(
            diag,
            "token.py:1: [telegram_bot_token] potential secret token detected",
        )
        self.assertNotIn("AAFl", diag)
        self.assertNotIn("9876543210", diag)

    # ------------------------------------------------------------------
    # Codex Follow-up 1: Containment validation on both scan modes
    # ------------------------------------------------------------------
    def test_git_scan_rejects_tracked_path_through_junction_outside_repo(self) -> None:
        """Verify default Git scan rejects tracked path through junction pointing outside repo."""
        repo_dir = self.root / "junction_repo"
        repo_dir.mkdir()
        outside_dir = self.root / "outside_target"
        outside_dir.mkdir()
        outside_file = outside_dir / "secret.py"
        outside_file.write_text("print('outside')\n", encoding="utf-8")

        junction_dir = repo_dir / "linked_ext"
        if sys.platform == "win32":
            res = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction_dir), str(outside_dir)],
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                self.skipTest("Windows mklink junction creation not available")
        else:
            os.symlink(outside_dir, junction_dir)

        try:
            subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
            tracked_rel = "linked_ext/secret.py"
            subprocess.run(["git", "add", tracked_rel], cwd=repo_dir, check=True)

            with self.assertRaises(ScanError) as ctx_git:
                scan_repository(repo_dir, allowlist=self.allowlist)
            self.assertIn("outside repository root", str(ctx_git.exception))

            with self.assertRaises(ScanError) as ctx_explicit:
                scan_repository(repo_dir, allowlist=self.allowlist, files=[repo_dir / tracked_rel])
            self.assertIn("outside repository root", str(ctx_explicit.exception))
        finally:
            if junction_dir.exists():
                if sys.platform == "win32":
                    subprocess.run(["cmd", "/c", "rmdir", str(junction_dir)], capture_output=True)
                else:
                    junction_dir.unlink()
            self._remove_git_dir(repo_dir)

    # ------------------------------------------------------------------
    # Codex Follow-up 2: Failed file read treated as ScanError (exit code 2)
    # ------------------------------------------------------------------
    def test_failed_file_read_raises_scan_error_and_cli_exits_2(self) -> None:
        """Verify an in-scope file that fails read_bytes raises ScanError and produces exit code 2."""
        unreadable_file = self.root / "unreadable.py"
        unreadable_file.write_text("print('test')\n", encoding="utf-8")

        from unittest.mock import patch

        with patch.object(Path, "read_bytes", side_effect=PermissionError("Permission denied")):
            with self.assertRaises(ScanError) as ctx:
                scan_file(unreadable_file, self.allowlist, root=self.root)
            self.assertIn("Failed to read file", str(ctx.exception))

            ret = main(["--root", str(self.root), str(unreadable_file)])
            self.assertEqual(ret, 2)

    # ------------------------------------------------------------------
    # Codex Follow-up 3: Scoped exclusions, whole-match allowlists, quoted marker isolation
    # ------------------------------------------------------------------
    def test_quoted_bare_and_rule_scoped_pragma_does_not_suppress_credential(self) -> None:
        """Verify pragma text inside quoted string or backticks does not suppress credentials."""
        # Bare pragma inside quotes
        test_file = self.root / "quoted_pragma.py"
        test_file.write_text(
            'msg = "# pragma: allowlist secret"\n'
            'token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )
        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "telegram_bot_token")

        # Rule-scoped pragma inside quotes
        test_file_scoped = self.root / "quoted_scoped.py"
        test_file_scoped.write_text(
            'msg = "# pragma: allowlist secret: telegram_bot_token"\n'
            'token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )
        findings_scoped = scan_file(test_file_scoped, self.allowlist, root=self.root)
        self.assertEqual(len(findings_scoped), 1)
        self.assertEqual(findings_scoped[0].rule_name, "telegram_bot_token")

        # HTML pragma inside quotes
        test_file_html = self.root / "quoted_html.py"
        test_file_html.write_text(
            'doc = "<!-- pragma: allowlist secret -->"\n'
            'token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )
        findings_html = scan_file(test_file_html, self.allowlist, root=self.root)
        self.assertEqual(len(findings_html), 1)
        self.assertEqual(findings_html[0].rule_name, "telegram_bot_token")

        # Backticks in markdown
        doc_file = self.root / "backtick_doc.md"
        doc_file.write_text(
            "# Guide\n"
            "Use `# pragma: allowlist secret` to suppress.\n"
            "token = 9876543210:AAFl1234567890abcdefghijklmnopqrstuv\n",  # pragma: allowlist secret
            encoding="utf-8",
        )
        findings_doc = scan_file(doc_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings_doc), 1)
        self.assertEqual(findings_doc[0].rule_name, "telegram_bot_token")

    def test_whole_match_allowlist_catches_longer_token_containing_placeholder(self) -> None:
        """Verify credential containing allowlisted pattern as substring is not suppressed."""
        test_file = self.root / "substring_token.py"
        test_file.write_text(
            'api_key = "your-api-key-really-secret-live-1234567890"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )
        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "generic_api_key_assignment")

    def test_exemption_for_one_match_does_not_hide_another_credential(self) -> None:
        """Verify an exemption for one match cannot hide another credential on the same line."""
        # Allowlisted placeholder + un-allowlisted secret on same line
        test_file = self.root / "multi_credential.py"
        test_file.write_text(
            'api_key = "your-api-key" ; token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )
        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_name, "telegram_bot_token")

        # Two secrets, only one pragma: only one is exempted, second remains detected
        test_file_two = self.root / "two_secrets_one_pragma.py"
        test_file_two.write_text(
            'token1 = "9876543210:AAFl1111111111abcdefghijklmnopqrstuv" ; '  # pragma: allowlist secret
            'token2 = "9876543210:AAFl2222222222abcdefghijklmnopqrstuv"  # pragma: allowlist secret\n',  # pragma: allowlist secret
            encoding="utf-8",
        )
        findings_two = scan_file(test_file_two, self.allowlist, root=self.root)
        self.assertEqual(len(findings_two), 1)
        self.assertEqual(findings_two[0].rule_name, "telegram_bot_token")

    # ------------------------------------------------------------------
    # Codex Follow-up 4: Sanitize tokens in finding and error diagnostic paths
    # ------------------------------------------------------------------
    def test_sanitize_path_helper(self) -> None:
        """Verify sanitize_path helper redacts secret tokens from paths."""
        self.assertEqual(
            sanitize_path("path/to/AKIA1234567890ABCDEF.py"),  # pragma: allowlist secret
            "path/to/[REDACTED].py",
        )
        self.assertEqual(
            sanitize_path("prefix_AKIA1234567890ABCDEF_suffix.txt"),  # pragma: allowlist secret
            "prefix_[REDACTED]_suffix.txt",
        )
        self.assertEqual(
            sanitize_path("clean/path/file.py"),
            "clean/path/file.py",
        )

    def test_finding_diagnostic_sanitizes_token_in_filename(self) -> None:
        """Verify finding diagnostics replace secret tokens in filenames with [REDACTED]."""
        token_filename = "AKIA1234567890ABCDEF.py"  # pragma: allowlist secret
        test_file = self.root / token_filename
        test_file.write_text(
            'key = "AKIA1234567890ABCDEF"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )

        findings = scan_file(test_file, self.allowlist, root=self.root)
        self.assertEqual(len(findings), 1)
        diag = findings[0].format_diagnostic()
        self.assertIn("[REDACTED].py", diag)
        self.assertNotIn("AKIA1234567890ABCDEF", diag)  # pragma: allowlist secret

    def test_error_diagnostic_sanitizes_token_in_path(self) -> None:
        """Verify error messages on stderr replace tokens in paths with [REDACTED]."""
        missing_name = "outside_AKIA1234567890ABCDEF.py"  # pragma: allowlist secret
        import io
        from contextlib import redirect_stderr

        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            ret = main(["--root", str(self.root), missing_name])

        self.assertEqual(ret, 2)
        err_output = stderr_buf.getvalue()
        self.assertIn("[REDACTED].py", err_output)
        self.assertNotIn("AKIA1234567890ABCDEF", err_output)  # pragma: allowlist secret

    def test_pragma_inside_multiline_triple_quoted_string_does_not_suppress_finding(self) -> None:
        """Verify pragma text inside multiline triple-quoted strings does not suppress secrets."""
        # Double-quote triple quotes """..."""
        test_file_dq = self.root / "multiline_dq.py"
        test_file_dq.write_text(
            'doc = """\n'
            "# pragma: allowlist secret\n"
            'token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"\n'  # pragma: allowlist secret
            '"""\n',
            encoding="utf-8",
        )
        findings_dq = scan_file(test_file_dq, self.allowlist, root=self.root)
        self.assertEqual(len(findings_dq), 1)
        self.assertEqual(findings_dq[0].rule_name, "telegram_bot_token")
        self.assertEqual(findings_dq[0].line_number, 3)

        # Single-quote triple quotes '''...'''
        test_file_sq = self.root / "multiline_sq.py"
        test_file_sq.write_text(
            "fixture = '''\n"
            "# pragma: allowlist secret: aws_access_key\n"
            "AWS_KEY = 'AKIA1234567890ABCDEF'\n"  # pragma: allowlist secret
            "'''\n",
            encoding="utf-8",
        )
        findings_sq = scan_file(test_file_sq, self.allowlist, root=self.root)
        self.assertEqual(len(findings_sq), 1)
        self.assertEqual(findings_sq[0].rule_name, "aws_access_key")
        self.assertEqual(findings_sq[0].line_number, 3)

    def test_forwarded_flags_after_double_dash_scanned_as_files(self) -> None:
        """Verify filenames matching flag syntax (e.g. --root=docs) after -- are scanned as files."""
        flag_file = self.root / "--root=docs"
        flag_file.write_text(
            'token = "9876543210:AAFl1234567890abcdefghijklmnopqrstuv"\n',  # pragma: allowlist secret
            encoding="utf-8",
        )
        try:
            ret_dirty = main(["--root", str(self.root), "--", str(flag_file)])
            self.assertEqual(ret_dirty, 1)

            flag_file.write_text("print('clean')\n", encoding="utf-8")
            ret_clean = main(["--root", str(self.root), "--", str(flag_file)])
            self.assertEqual(ret_clean, 0)
        finally:
            if flag_file.exists():
                flag_file.unlink()


if __name__ == "__main__":
    unittest.main()
