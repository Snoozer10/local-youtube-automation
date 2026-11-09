"""Unit tests for the proportionate repository secret scanning gate."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

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
    load_allowlist,
    main,
    mask_secret,
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
        self.assertIn("[REDACTED]", findings[0].masked_value)
        self.assertNotIn("AAFl1234567890abcdefghijklmnopqrstuv", findings[0].masked_value)

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
        self.assertIn("AKIA", findings[0].masked_value)
        self.assertIn("[REDACTED]", findings[0].masked_value)

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
        self.assertIn("[REDACTED]", findings[0].masked_value)

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
        special_file.write_text("Key: AKIA1234567890ABCDEF\n", encoding="utf-8")  # pragma: allowlist secret

        other_file = self.root / "docs" / "other.md"
        other_file.write_text("Key: AKIA1234567890ABCDEF\n", encoding="utf-8")  # pragma: allowlist secret

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


if __name__ == "__main__":
    unittest.main()
