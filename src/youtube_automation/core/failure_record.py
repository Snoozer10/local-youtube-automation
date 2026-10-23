"""Compact, machine-readable failure records plus a known-issue matcher (offline, stdlib only)."""

from __future__ import annotations

import json
import os
import re
import traceback
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FAILURES_PATH_ENV = "FAILURE_RECORDS_PATH"
KNOWN_ISSUES_PATH = Path(__file__).with_name("known_issues.json")
_UNSET: Any = object()


_CAPTURE_ACTIVE: ContextVar[bool] = ContextVar("failure_record_capture_active", default=False)

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_path() -> Path:
    override = os.environ.get(FAILURES_PATH_ENV)
    return Path(override) if override else _repo_root() / ".runtime" / "failures.jsonl"


def _rel_frame_path(filename: str) -> str | None:
    """Repo-relative posix path when the file is under src/ or .runtime/, else None."""
    try:
        root = _repo_root().resolve()
        path = Path(filename)
        candidate = (path if path.is_absolute() else root / path).resolve()
        relative = candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    rel = relative.as_posix()
    return rel if rel.startswith(("src/", ".runtime/")) else None


def innermost_project_frame(exc: BaseException) -> dict[str, Any] | None:
    """LAST traceback frame under repo src/ or .runtime/ (never the full traceback)."""
    found = None
    for fs in traceback.extract_tb(exc.__traceback__):
        rel = _rel_frame_path(fs.filename)
        if rel:
            found = {"file": rel, "line": fs.lineno, "function": fs.name}
    return found


_REDACTIONS = (
    (re.compile(r"\?[^\s\"')>]+"), "?[redacted]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
    (
        re.compile(
            r"(?i)\b(cookie|set-cookie|token|authorization|bearer|api[_-]?key)\b[\"']?(\s*[:=]\s*|\s+)\S+"
        ),
        r"\1=[redacted]",
    ),
    (
        re.compile(
            r"""(?i)(["']?\b(?:password|passwd|secret)["']?\s*[:=]\s*)("(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|[^\s,;]+)"""
        ),
        r"\1[redacted]",
    ),
)
_CONTRACT_FILES = ("production/contracts", "production/writing", "production/narration")


def _clean(text: str, limit: int = 300) -> str:
    header_redactions = (
        (
            re.compile(
                r"(?i)([\"']?(?:proxy-)?authorization[\"']?\s*:\s*)\"(?:\\.|[^\"\\])*\""
            ),
            r'\1"[redacted]"',
        ),
        (
            re.compile(
                r"(?i)([\"']?(?:set-cookie|cookie)[\"']?\s*:\s*)\"(?:\\.|[^\"\\])*\""
            ),
            r'\1"[redacted]"',
        ),
        (
            re.compile(
                r"(?i)\b(proxy-authorization|authorization)\b[\"']?\s*[:=]\s*(?:\"(?:\\.|[^\"\\])*\"?|'(?:\\.|[^'\\])*'?|[A-Za-z][A-Za-z0-9_-]*\s+[^\s,;]+|[^\s,;]+)"
            ),
            r"\1: [redacted]",
        ),
        (
            re.compile(
                r"(?i)\b(set-cookie|cookie)\b[\"']?\s*:\s*(?:\"(?:\\.|[^\"\\])*\"?|'(?:\\.|[^'\\])*'?|[^\r\n]*)"
            ),
            r"\1: [redacted]",
        ),
    )
    for rx, repl in header_redactions:
        text = rx.sub(repl, text)
    for rx, repl in _REDACTIONS:
        text = rx.sub(repl, text)
    return " ".join(text.split())[:limit]


def classify_layer(exc: BaseException, stage: str = "", frame: Any = _UNSET) -> str:
    """Layer rules, first match wins (matched by class name, no heavy imports).

    budget: message has "ceiling reached"; browser.cdp: connect_over_cdp/CDP in message;
    provider: TTSProviderError/GeminiUsageLimitError/"http status code" banners;
    network: NetworkDegradedError/URLError/socket timeouts/Page.goto timeout;
    browser.ui: TTSWorkspaceUnavailableError or playwright errors (locator timeouts);
    contract: ValidationError, or ValueError raised in production contracts|writing|narration;
    code: any other exception with a frame in src/; else unknown.
    """
    name, msg = type(exc).__name__, str(exc)
    low = msg.lower()
    if frame is _UNSET:
        frame = innermost_project_frame(exc)
    if "ceiling reached" in low:
        return "budget"
    if re.search(r"connect_over_cdp|\bcdp\b", msg, re.I):
        return "browser.cdp"
    if name in ("TTSProviderError", "GeminiUsageLimitError") or "http status code" in low:
        return "provider"
    is_pw = type(exc).__module__.startswith("playwright")
    if name in ("NetworkDegradedError", "URLError", "timeout") or "page.goto" in low:
        return "network"
    if name == "TimeoutError" and not is_pw:
        return "network"
    if name == "TTSWorkspaceUnavailableError" or is_pw:
        return "browser.ui"
    if name == "ValidationError":
        return "contract"
    fpath = (frame or {}).get("file", "")
    if name == "ValueError" and any(part in fpath for part in _CONTRACT_FILES):
        return "contract"
    return "code" if fpath.startswith("src/") else "unknown"


def error_kind(exc: BaseException, layer: str) -> str:
    """transient/quota/account/contract/budget/code/unknown (provider wording via ui_guard)."""
    if layer in ("budget", "contract", "code", "unknown"):
        return layer
    try:
        from youtube_automation.browser.ui_guard import classify_provider_error

        kind = str(classify_provider_error(str(exc)))
    except Exception:
        low = str(exc).lower()
        kind = "quota" if "quota" in low or "usage limit" in low else "unknown"
    if kind == "unknown" and layer in ("network", "browser.cdp"):
        return "transient"
    return kind


def _load_issues() -> list[dict[str, Any]]:
    try:
        data = json.loads(KNOWN_ISSUES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def match_known_issue(
    record: dict[str, Any], issues: list[dict[str, Any]] | None = None
) -> dict[str, Any] | None:
    exc_name, message = str(record.get("exception", "")), str(record.get("message", ""))
    frame = record.get("frame") or {}
    frame_file = str(frame.get("file", "")) if isinstance(frame, dict) else ""
    for issue in _load_issues() if issues is None else issues:
        if issue.get("layer") and issue["layer"] != record.get("layer"):
            continue
        try:
            rx = re.compile(issue["pattern"], re.I)
            if issue.get("frame_pattern") and not re.search(
                issue["frame_pattern"], frame_file, re.I
            ):
                continue
        except (re.error, KeyError, TypeError):
            continue
        if rx.search(message) or rx.search(exc_name) or rx.search(f"{exc_name}: {message}"):
            return {
                key: issue.get(key)
                for key in (
                    "id",
                    "observed_signature",
                    "cause",
                    "cause_status",
                    "confidence",
                    "fix",
                    "evidence",
                    "false_positive_boundaries",
                )
            }
    return None


def _safe_repo_path(value: str | os.PathLike[str]) -> str:
    """Return a bounded repo-relative path; never persist machine-specific roots."""
    try:
        root = _repo_root().resolve()
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = root / candidate
        return _clean(candidate.resolve(strict=False).relative_to(root).as_posix(), 300)
    except (OSError, RuntimeError, TypeError, ValueError):
        return "<external-path>"


def build_record(
    exc: BaseException,
    *,
    stage: str,
    run_dir: str | os.PathLike[str] | None = None,
    sends_spent: int | None = None,
    evidence: Sequence[str | os.PathLike[str]] = (),
    extra: dict[str, Any] | None = None,
    frame: Any = _UNSET,
) -> dict[str, Any]:
    if frame is _UNSET:
        frame = innermost_project_frame(exc)
    if isinstance(frame, dict):
        raw_frame_path = str(frame.get("file", ""))
        frame_path = (
            raw_frame_path
            if raw_frame_path.startswith(("src/", ".runtime/"))
            else _rel_frame_path(raw_frame_path)
        )
        safe_frame = (
            {
                "file": _clean(frame_path, 300),
                "line": max(0, int(frame.get("line", 0))),
                "function": _clean(str(frame.get("function", "")), 120),
            }
            if frame_path
            else None
        )
    else:
        safe_frame = None
    layer = classify_layer(exc, stage, safe_frame)
    safe_evidence: list[str] = []
    for path in evidence:
        if len(safe_evidence) == 10:
            break
        safe_path = _safe_repo_path(path)
        if safe_path not in safe_evidence:
            safe_evidence.append(safe_path)
    record: dict[str, Any] = {
        "version": 1,
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage": _clean(str(stage), 80),
        "run_dir": _safe_repo_path(run_dir) if run_dir else None,
        "layer": layer,
        "kind": error_kind(exc, layer),
        "exception": _clean(type(exc).__name__, 80),
        "message": _clean(str(exc)),
        "frame": safe_frame,
        "sends_spent": sends_spent if isinstance(sends_spent, int) and sends_spent >= 0 else None,
        "evidence": safe_evidence,
        "extra": {
            _clean(str(key), 40): _clean(str(value), 80)
            for key, value in list(sanitize_record(extra or {}).items())[:10]
        },
    }
    record["known_issue"] = match_known_issue(record)
    return record


def append_record(record: dict[str, Any], path: str | os.PathLike[str] | None = None) -> Path:
    target = Path(path) if path else default_path()
    line = json.dumps(record, ensure_ascii=False)
    if len(line.encode("utf-8")) > 16_384:
        raise ValueError("failure record exceeds the 16 KiB limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return target


@contextmanager
def capture(
    stage: str,
    *,
    run_dir: str | os.PathLike[str] | None = None,
    sends_spent: int | None = None,
    evidence: Sequence[str | os.PathLike[str]] = (),
) -> Iterator[None]:
    """Record one bounded failure per nested operation and re-raise it untouched."""
    if _CAPTURE_ACTIVE.get():
        yield
        return
    token = _CAPTURE_ACTIVE.set(True)
    try:
        try:
            yield
        except BaseException as exc:
            try:
                append_record(
                    build_record(
                        exc, stage=stage, run_dir=run_dir, sends_spent=sends_spent, evidence=evidence
                    )
                )
            except BaseException:
                # Diagnostics must never replace the product exception.
                pass
            raise
    finally:
        _CAPTURE_ACTIVE.reset(token)


def load_records(
    path: str | os.PathLike[str] | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    target = Path(path) if path else default_path()
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records[-limit:] if limit else records


def load_last_record(
    path: str | os.PathLike[str] | None = None, *, max_bytes: int = 65_536
) -> dict[str, Any] | None:
    """Read only a bounded tail and return its newest complete JSON object."""
    target = Path(path) if path else default_path()
    budget = min(max(1, int(max_bytes)), 65_536)
    try:
        with target.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            if not end:
                return None
            start = max(0, end - budget)
            handle.seek(start)
            tail = handle.read(budget)
    except OSError:
        return None
    if start:
        boundary = tail.find(b"\n")
        if boundary < 0:
            return None
        tail = tail[boundary + 1 :]
    lines = [line for line in tail.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        record = json.loads(lines[-1])
    except (UnicodeDecodeError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Copy diagnostic JSON with redaction and bounded depth, fields and strings."""
    if not isinstance(record, dict):
        raise ValueError("Failure record must be a JSON object")
    remaining = 512
    sensitive = {
        "authorization", "proxyauthorization", "bearer", "cookie", "setcookie",
        "token", "accesstoken", "refreshtoken", "idtoken", "apikey", "xapikey",
        "password", "passwd", "secret",
    }

    def visit(value: Any, depth: int, header_values: bool = False) -> Any:
        nonlocal remaining
        if remaining <= 0:
            return "[truncated]"
        remaining -= 1
        if depth > 8:
            return "[truncated]"
        if header_values and not isinstance(value, (dict, list)):
            return "[redacted]"
        if isinstance(value, str):
            return _clean(value[:4096], limit=300)
        if isinstance(value, dict):
            result = {}
            for index, (key, item) in enumerate(value.items()):
                if index >= 64 or remaining <= 0:
                    break
                raw_key = str(key)[:1024]
                clean_key = _clean(raw_key, limit=80)
                normalized = re.sub(r"[^a-z0-9]", "", raw_key.lower())
                if header_values or normalized in sensitive:
                    result[clean_key] = "[redacted]"
                    remaining -= 1
                else:
                    result[clean_key] = visit(
                        item, depth + 1, normalized in {"headers", "requestheaders", "responseheaders"}
                    )
            return result
        if isinstance(value, list):
            items = []
            for item in value[:64]:
                if remaining <= 0:
                    break
                items.append(visit(item, depth + 1, header_values))
            return items
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return _clean(str(value)[:4096], limit=300)

    sanitized = visit(record, 0)
    if not isinstance(sanitized, dict):
        raise ValueError("Failure record must sanitize to a JSON object")
    return sanitized


def digest(record: dict[str, Any]) -> str:
    """Human/agent summary, at most 60 lines."""
    frame = record.get("frame")
    out = [
        f"stage: {record.get('stage')}   utc: {record.get('utc')}",
        f"layer/kind: {record.get('layer')}/{record.get('kind')}",
        f"exception: {record.get('exception')}: {record.get('message')}",
        "frame: " + (f"{frame['file']}:{frame['line']} {frame['function']}" if frame else "none"),
        f"sends spent: {record.get('sends_spent')}",
    ]
    if record.get("run_dir"):
        out.append(f"run_dir: {record['run_dir']}")
    issue = record.get("known_issue")
    if issue:
        confidence = issue.get("confidence") or "unrated"
        status = issue.get("cause_status") or "hypothesis"
        out += [
            f"known issue: {issue['id']}",
            f"  observed: {issue.get('observed_signature') or 'signature match'}",
            f"  cause ({status}; {confidence}): {issue['cause']}",
            f"  fix: {issue['fix']}",
        ]
        out += [f"  false-positive boundary: {p}" for p in (issue.get("false_positive_boundaries") or [])]
        out += [f"  evidence: {p}" for p in (issue.get("evidence") or [])]
    else:
        out.append("known issue: none")
    out += [f"evidence: {p}" for p in record.get("evidence") or []]
    return "\n".join(_clean(line[:4096], limit=300) for line in out[:60])
