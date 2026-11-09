"""Proportionate repository secret scanning gate.

Scans tracked files and documentation for high-fidelity secret and service
token signatures with reviewed exclusion support.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# High-fidelity token patterns
SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "telegram_bot_token": re.compile(r"(?:(?<=\b)|(?<=bot))[0-9]{8,10}:[a-zA-Z0-9_-]{34,36}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"),
    "aws_secret_key": re.compile(
        r"(?i)\b(?:aws_secret_access_key|aws_secret_key)\s*[:=]\s*['\"]?([a-zA-Z0-9/+=]{40})['\"]?"
    ),
    "github_token": re.compile(
        r"\b(?:ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82}|gho_[a-zA-Z0-9]{36}|ghu_[a-zA-Z0-9]{36}|ghs_[a-zA-Z0-9]{36}|ghr_[a-zA-Z0-9]{36})\b"
    ),
    "private_key_block": re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    ),
    "slack_token": re.compile(r"\bxox[baprs]-[0-9a-zA-Z]{10,48}\b"),
    "generic_api_key_assignment": re.compile(
        r"(?i)\b(?:api_key|api_token|secret_key|auth_token|client_secret|bearer_token)\s*[:=]\s*['\"]([a-zA-Z0-9_\-\.]{24,})['\"]"
    ),
}

INLINE_PRAGMAS = (
    "# pragma: allowlist secret",
    "# noqa: secret-check",
    "<!-- pragma: allowlist secret -->",
)


@dataclass(frozen=True)
class SecretFinding:
    """Represents a detected secret in a scanned file."""

    path: str
    line_number: int
    rule_name: str
    masked_value: str

    def format_diagnostic(self) -> str:
        """Format finding for terminal reporting without leaking secret contents."""
        return (
            f"{self.path}:{self.line_number}: [{self.rule_name}] "
            f"potential secret token detected: {self.masked_value}"
        )


def mask_secret(value: str) -> str:
    """Return a safely redacted representation of a secret string."""
    value = value.strip()
    if len(value) <= 8:
        return "[REDACTED]"
    prefix = value[:4]
    suffix = value[-4:]
    return f"{prefix}...[REDACTED]...{suffix}"


def load_allowlist(config_path: Path | None = None) -> dict[str, Any]:
    """Load the reviewed exclusions allowlist configuration."""
    default_config: dict[str, Any] = {
        "excluded_paths": [
            ".git",
            ".runtime",
            ".venv",
            ".mypy_cache",
            ".pytest_cache",
            "__pycache__",
            "build",
            "dist",
        ],
        "excluded_extensions": [
            ".png",
            ".jpg",
            ".jpeg",
            ".wav",
            ".mp3",
            ".mp4",
            ".ico",
            ".whl",
            ".tar.gz",
            ".pyc",
        ],
        "allowed_patterns": [
            "YOUR_TELEGRAM_BOT_TOKEN",
            "your_telegram_bot_token",
            "your-api-key",
            "your_api_key_here",
            r"\[redacted\]",
            r"0000000000:AA[a-zA-Z0-9_-]{33}",
            "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_1234567",
            "AKIAIOSFODNN7EXAMPLE",
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "ghp_000000000000000000000000000000000000",
            "xoxb-YOUR_SLACK_TOKEN",
        ],
        "path_specific_allowlists": {},
    }

    if config_path is None:
        candidate = Path(__file__).resolve().parent / "secrets_allowlist.json"
        if candidate.is_file():
            config_path = candidate

    if config_path and config_path.is_file():
        try:
            with open(config_path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    if k in default_config:
                        default_config[k] = v
        except Exception as e:
            print(f"Warning: Failed to load allowlist from {config_path}: {e}", file=sys.stderr)

    return default_config


def _is_allowed(
    line: str,
    matched_text: str,
    file_rel_path: str,
    allowlist: dict[str, Any],
) -> bool:
    """Check if a match is covered by reviewed exclusions or inline pragmas."""
    if any(pragma in line for pragma in INLINE_PRAGMAS):
        return True

    allowed_patterns: list[str] = allowlist.get("allowed_patterns", [])
    for pattern_str in allowed_patterns:
        try:
            if re.search(pattern_str, line) or re.search(pattern_str, matched_text):
                return True
        except re.error:
            if pattern_str in line or pattern_str in matched_text:
                return True

    path_specific = allowlist.get("path_specific_allowlists", {})
    if file_rel_path in path_specific:
        patterns = path_specific[file_rel_path]
        for pattern_str in patterns:
            try:
                if re.search(pattern_str, line) or re.search(pattern_str, matched_text):
                    return True
            except re.error:
                if pattern_str in line or pattern_str in matched_text:
                    return True

    return False


def scan_file(
    path: Path,
    allowlist: dict[str, Any],
    root: Path | None = None,
) -> list[SecretFinding]:
    """Scan a single file for secret patterns."""
    root = root or path.parent
    try:
        rel_path = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel_path = path.as_posix()

    excluded_extensions = tuple(allowlist.get("excluded_extensions", []))
    if any(rel_path.endswith(ext) for ext in excluded_extensions):
        return []

    excluded_paths = allowlist.get("excluded_paths", [])
    for exc in excluded_paths:
        exc_norm = exc.replace("\\", "/").strip("/")
        if rel_path == exc_norm or rel_path.startswith(f"{exc_norm}/"):
            return []

    try:
        content_bytes = path.read_bytes()
    except (OSError, PermissionError):
        return []

    # Skip binary files
    if b"\x00" in content_bytes[:4096]:
        return []

    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content_bytes.decode("latin-1")
        except Exception:
            return []

    findings: list[SecretFinding] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule_name, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(line):
                matched_str = match.group(0)
                # If group 1 exists, evaluate group 1 (the secret value itself)
                val_to_eval = match.group(1) if match.lastindex and match.lastindex >= 1 else matched_str
                if _is_allowed(line, val_to_eval, rel_path, allowlist):
                    continue
                findings.append(
                    SecretFinding(
                        path=rel_path,
                        line_number=line_number,
                        rule_name=rule_name,
                        masked_value=mask_secret(val_to_eval),
                    )
                )

    return findings


def scan_repository(
    root: Path,
    allowlist: dict[str, Any] | None = None,
    files: list[Path] | None = None,
) -> list[SecretFinding]:
    """Scan files in the repository for secrets."""
    allowlist = allowlist or load_allowlist(root / "tools" / "secrets_allowlist.json")

    target_paths: list[Path] = []
    if files is not None:
        target_paths = [p if p.is_absolute() else (root / p) for p in files]
    else:
        # Use git ls-files if available
        try:
            cmd = ["git", "-C", str(root), "ls-files"]
            output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            tracked = output.decode("utf-8", errors="ignore").splitlines()
            target_paths = [root / p.strip() for p in tracked if p.strip()]
        except Exception:
            # Fallback to filesystem walk
            for p in root.rglob("*"):
                if p.is_file():
                    target_paths.append(p)

    all_findings: list[SecretFinding] = []
    for path in target_paths:
        if not path.is_file():
            continue
        findings = scan_file(path, allowlist, root=root)
        all_findings.extend(findings)

    return all_findings


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for secret scanning gate."""
    parser = argparse.ArgumentParser(
        description="Proportionate repository secret scanning gate."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (defaults to current working directory)",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="Path to secrets allowlist JSON configuration",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Optional specific files to scan (e.g. from pre-commit)",
    )

    args = parser.parse_args(argv)
    root = args.root.resolve()
    allowlist = load_allowlist(args.allowlist or (root / "tools" / "secrets_allowlist.json"))

    target_files = args.files if args.files else None
    findings = scan_repository(root=root, allowlist=allowlist, files=target_files)

    if findings:
        print(f"Secret scanning gate failed: {len(findings)} potential secret(s) detected:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding.format_diagnostic()}", file=sys.stderr)
        print("\nIf any detection is a reviewed placeholder or test fixture,", file=sys.stderr)
        print("update tools/secrets_allowlist.json or annotate with '# pragma: allowlist secret'.", file=sys.stderr)
        return 1

    file_count = len(target_files) if target_files else "tracked"
    print(f"Secret scanning gate passed: 0 secrets detected across {file_count} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
