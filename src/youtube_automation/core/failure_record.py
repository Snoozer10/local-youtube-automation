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


_CANARY_OR_PROSE_RE = re.compile(
    r"(?i)\b(?:canary|system prompt|user prompt|prompt:|script:|def |class |import |return |select\b.*from\b)\b"
)
_CREDENTIAL_RAW_RE = re.compile(
    r"(?i)\b(?:password|passwd|secret|api[_-]?key|bearer|token)\b\s*[:=]\s*(?!\[redacted\])\S+"
)
_BOUNDED_OPERATIONAL_PATTERNS = [
    re.compile(r"(?i)^BrowserType\.connect_over_cdp:\s*Timeout\s+\d+ms\s+exceeded$"),
    re.compile(r"(?i)^Page\.goto:\s*Timeout\s+\d+ms\s+exceeded$"),
    re.compile(r"(?i)^locator\.[a-z]+\s*:\s*Timeout\s+\d+ms\s+exceeded$"),
    re.compile(r"(?i)^Resource\s+lease\s+renewal\s+failed$"),
    re.compile(r"(?i)^Lost\s+production\s+lease$"),
    re.compile(r"(?i)^Cannot\s+acquire\s+a\s+production\s+lease$"),
    re.compile(r"(?i)^Nested\s+production\s+leases\s+must\s+share\s+one\s+ledger$"),
    re.compile(r"(?i)^Stage\s+circuit(?:\s+is)?\s+open(?:\s+after\s+\d+\s+failed\s+attempts)?(?::\s*[a-zA-Z0-9_\-:]+)?$"),
    re.compile(r"(?i)^Stage\s+is\s+already\s+running$"),
    re.compile(r"(?i)^Resource\s+is\s+busy$"),
    re.compile(r"(?i)^Invalid\s+terminal\s+state$"),
    re.compile(r"(?i)^Stale\s+worker(?:\s+cannot\s+finish\s+this\s+job)?$"),
    re.compile(r"(?i)^(?:TTS\s+)?attempt\s+ceiling\s+reached$"),
    re.compile(r"(?i)^(?:Existing\s+voice\s+chapters\s+have\s+)?no\s+matching\s+adaptive\s+recipe$"),
    re.compile(r"(?i)^(?:AI\s+Studio\s+banner\s+)?Http\s+response\s+at\s+400\s+or\s+500\s+level,\s*http\s+status\s+code:\s*\d+$"),
    re.compile(r"(?i)^http\s+status\s+code:?\s*\d+$"),
    re.compile(r"(?i)^Connection\s+(?:refused|reset(?:\s+by\s+peer)?)$"),
    re.compile(r"(?i)^Operation\s+timed\s+out$"),
    re.compile(r"(?i)^Quota\s+exhausted$"),
    re.compile(r"(?i)^Usage\s+limit\s+reached$"),
    re.compile(r"(?i)^Validation\s+failed$"),
    re.compile(r"(?i)^Invalid\s+syntax$"),
    re.compile(r"(?i)^\[email\]$"),
]
_AUTH_HEADER_PREFIX_RE = re.compile(
    r"(?i)^['\"]?(?:Authorization|Proxy-Authorization|Cookie|Set-Cookie)['\"]?\s*[:=]"
)


def is_safe_operational_message(text: str) -> bool:
    """Validate whether an error message is an authorized bounded operational summary.

    Rejects non-ASCII canaries, unvalidated prompt prose, private scripts, raw request
    bodies, unredacted credentials, arbitrary ASCII sentences, and messages containing
    unauthorized trailing prose.
    """
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if not stripped or not all(32 <= ord(c) <= 126 for c in stripped):
        return False
    if any(c in stripped for c in ("\n", "\r", "\t", "{", "}", "<", ">")):
        return False
    if _CANARY_OR_PROSE_RE.search(stripped) or _CREDENTIAL_RAW_RE.search(stripped):
        return False
    if len(stripped) > 200:
        return False
    for pat in _BOUNDED_OPERATIONAL_PATTERNS:
        if pat.fullmatch(stripped):
            return True
    return False


def project_safe_message(
    message: str,
    *,
    exc_name: str = "",
    layer: str = "unknown",
    kind: str = "unknown",
    known_issue: dict[str, Any] | None = None,
) -> str:
    """Project a message into an authorized safe summary.

    If the cleaned message is a verified operational message, it is returned.
    Otherwise, projects to a known-issue signature or a bounded category diagnostic identity.
    """
    cleaned = _clean(message, limit=300)
    if is_safe_operational_message(cleaned):
        return cleaned
    if known_issue and isinstance(known_issue, dict) and known_issue.get("id"):
        sig = known_issue.get("observed_signature")
        return f"[{known_issue['id']}] {sig}" if sig else f"[{known_issue['id']}] Known issue matched"
    base_name = exc_name.strip() or "Failure"
    return f"[{layer}/{kind}] {base_name}"


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
    kind = error_kind(exc, layer)
    exc_name = _clean(type(exc).__name__, 80)
    raw_message = _clean(str(exc))
    known_issue = match_known_issue(
        {
            "exception": exc_name,
            "message": raw_message,
            "layer": layer,
            "frame": safe_frame,
        }
    )
    safe_message = project_safe_message(
        raw_message,
        exc_name=exc_name,
        layer=layer,
        kind=kind,
        known_issue=known_issue,
    )
    record: dict[str, Any] = {
        "version": 1,
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage": _clean(str(stage), 80),
        "run_dir": _safe_repo_path(run_dir) if run_dir else None,
        "layer": layer,
        "kind": kind,
        "exception": exc_name,
        "message": safe_message,
        "frame": safe_frame,
        "sends_spent": sends_spent if isinstance(sends_spent, int) and sends_spent >= 0 else None,
        "evidence": safe_evidence,
        "extra": {
            _clean(str(key), 40): _clean(str(value), 80)
            for key, value in list(sanitize_record(extra or {}).items())[:10]
        },
    }
    record["known_issue"] = known_issue
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
            raw_rec = json.loads(line)
            if isinstance(raw_rec, dict):
                records.append(sanitize_record(raw_rec))
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
    return sanitize_record(record) if isinstance(record, dict) else None


def sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Copy diagnostic JSON with redaction, safe message projection, and bounded depth."""
    if not isinstance(record, dict):
        raise ValueError("Failure record must be a JSON object")
    remaining = 512
    sensitive = {
        "authorization", "proxyauthorization", "bearer", "cookie", "setcookie",
        "token", "accesstoken", "refreshtoken", "idtoken", "apikey", "xapikey",
        "password", "passwd", "secret", "prompt", "script", "context", "prose",
        "text", "body", "payload", "query", "input", "detail", "canary",
    }
    rec_exc = str(record.get("exception", ""))
    rec_layer = str(record.get("layer", "unknown"))
    rec_kind = str(record.get("kind", "unknown"))
    rec_known = record.get("known_issue")

    def visit(
        value: Any,
        depth: int,
        header_values: bool = False,
        key_name: str = "",
        parent_sensitive: bool = False,
    ) -> Any:
        nonlocal remaining
        if remaining <= 0:
            return "[truncated]"
        remaining -= 1
        if depth > 8:
            return "[truncated]"
        if (header_values or parent_sensitive) and not isinstance(value, (dict, list)):
            return "[redacted]"
        if isinstance(value, str):
            if key_name == "message":
                return project_safe_message(
                    value,
                    exc_name=rec_exc,
                    layer=rec_layer,
                    kind=rec_kind,
                    known_issue=rec_known,
                )
            if key_name in {"rundir", "run_dir", "run"}:
                return _safe_repo_path(value)
            if header_values or parent_sensitive or key_name in sensitive:
                return "[redacted]"
            cleaned = _clean(value[:4096], limit=300)
            if any(ord(c) > 126 for c in cleaned) or re.search(r"(?i)\bcanary\b", cleaned):
                return "[redacted]"
            if (
                cleaned in {"<external-path>", "<missing>", "<unknown>"}
                or is_safe_operational_message(cleaned)
            ):
                return cleaned
            if key_name in {
                "stage", "state", "recipe", "job_id", "jobid", "channel_id", "channelid", "fence",
                "attempts", "category", "severity", "exception", "layer", "kind",
                "utc", "safe_id", "safeid", "id", "status"
            }:
                if re.fullmatch(r"^[a-zA-Z0-9_\-.:/]{1,80}$", cleaned):
                    return cleaned
            return "[redacted]"
        if isinstance(value, dict):
            result = {}
            for index, (key, item) in enumerate(value.items()):
                if index >= 64 or remaining <= 0:
                    break
                raw_key = str(key)[:1024]
                clean_key = _clean(raw_key, limit=80)
                normalized = re.sub(r"[^a-z0-9]", "", raw_key.lower())
                is_sensitive_key = normalized in sensitive
                if header_values or (is_sensitive_key and not isinstance(item, (dict, list))):
                    result[clean_key] = "[redacted]"
                    remaining -= 1
                else:
                    result[clean_key] = visit(
                        item,
                        depth + 1,
                        header_values or normalized in {"headers", "requestheaders", "responseheaders"},
                        key_name=normalized,
                        parent_sensitive=parent_sensitive or is_sensitive_key,
                    )
            return result
        if isinstance(value, list):
            items = []
            for item in value[:64]:
                if remaining <= 0:
                    break
                items.append(
                    visit(
                        item,
                        depth + 1,
                        header_values,
                        key_name=key_name,
                        parent_sensitive=parent_sensitive,
                    )
                )
            return items
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if parent_sensitive:
            return "[redacted]"
        str_val = _clean(str(value)[:4096], limit=300)
        if any(ord(c) > 126 for c in str_val) or re.search(r"(?i)\bcanary\b", str_val):
            return "[redacted]"
        return str_val

    sanitized = visit(record, 0)
    if not isinstance(sanitized, dict):
        raise ValueError("Failure record must sanitize to a JSON object")
    return sanitized


def digest(record: dict[str, Any]) -> str:
    """Human/agent summary, at most 60 lines."""
    record = sanitize_record(record)
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
