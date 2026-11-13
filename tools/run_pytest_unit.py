"""Run pre-commit unit tests with Python 3.10 qualification filtering.

This helper wraps pytest for the pre-commit pytest-unit hook, preserving the
command arguments while conditionally filtering the Python 3.11+ qualification
test on Python 3.10 to mirror CI's test selection.
"""

from __future__ import annotations

import sys

import pytest


def main(argv: list[str] | None = None) -> int:
    """Execute pytest with arguments, adding Python 3.10 qualification filter if needed."""
    args = list(sys.argv[1:] if argv is None else argv)
    if sys.version_info < (3, 11) and not any(
        arg == "-k" or arg.startswith("-k=") for arg in args
    ):
        args.extend(["-k", "not test_observation_environment_records_exact_runtime"])
    return int(pytest.main(args))


if __name__ == "__main__":
    raise SystemExit(main())
