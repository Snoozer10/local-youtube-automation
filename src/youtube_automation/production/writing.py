"""Channel-aware writing with resumable, content-bound paragraph artifacts."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import Field

from youtube_automation.core.utils import atomic_write_json

from .briefs import Response, request_json, writing_prompt
from .contracts import Brief, Contract, Text, fingerprint, load_brief, narration_fingerprint
from .ledger import publication_guard


class Paragraphs(Contract):
    paragraphs: list[Text] = Field(min_length=1, max_length=100)


class WrittenParagraph(Contract):
    text: Text


_FINAL_SCRIPT_TOKEN = re.compile(r"<\s*/?\s*final_script\b", re.IGNORECASE)
_FINAL_SCRIPT_TAG = re.compile(r"<\s*/?\s*final_script\b[^>]*>", re.IGNORECASE)
_FINAL_SCRIPT_OPEN = re.compile(r"<final_script\s*>", re.IGNORECASE)
_FINAL_SCRIPT_CLOSE = re.compile(r"</final_script\s*>", re.IGNORECASE)
ACCEPTED_ORIGINAL_MODE = "accepted_original"
SCRIPT_ACCEPTANCE_FILE = "script_acceptance.json"


def _final_script_text(text: str) -> str:
    """Extract one complete final_script wrapper while preserving cached replies."""
    tokens = list(_FINAL_SCRIPT_TOKEN.finditer(text))
    if not tokens:
        result = text.strip()
        if not result:
            raise ValueError("Refined paragraph is empty")
        return result

    tags = list(_FINAL_SCRIPT_TAG.finditer(text))
    opening = [tag for tag in tags if _FINAL_SCRIPT_OPEN.fullmatch(tag.group())]
    closing = [tag for tag in tags if _FINAL_SCRIPT_CLOSE.fullmatch(tag.group())]
    if (
        len(tokens) != 2
        or len(tags) != 2
        or len(opening) != 1
        or len(closing) != 1
        or tokens[0].start() != tags[0].start()
        or tokens[1].start() != tags[1].start()
    ):
        raise ValueError("Refined paragraph has multiple, nested, or malformed <final_script> tags")

    start, end = opening[0], closing[0]
    if (
        start.start() > end.start()
        or text[: start.start()].strip()
        or text[end.end() :].strip()
    ):
        raise ValueError("Refined paragraph has malformed <final_script> markup")
    result = text[start.end() : end.start()].strip()
    if not result:
        raise ValueError("Refined paragraph has an empty <final_script> block")
    return result


def _accepted_original_text(root: Path, brief: Brief) -> tuple[str, dict[str, Any]]:
    raw = (root / "raw_transcript.txt").read_text(encoding="utf-8-sig")
    acceptance = json.loads((root / SCRIPT_ACCEPTANCE_FILE).read_text(encoding="utf-8-sig"))
    if not (
        isinstance(acceptance, dict)
        and acceptance.get("version") == 1
        and acceptance.get("kind") == "accepted_original_script"
        and acceptance.get("channel_id") == brief.channel.channel_id
        and acceptance.get("script_sha256") == fingerprint(raw)
        and brief.source_sha256 == fingerprint(raw)
        and all(
            isinstance(acceptance.get(key), str) and acceptance[key].strip()
            for key in ("accepted_by", "statement")
        )
    ):
        raise ValueError("Script acceptance does not bind this run's source and channel")
    text = raw.strip()
    if not text:
        raise ValueError("Accepted original script is empty")
    if _FINAL_SCRIPT_TOKEN.search(text):
        raise ValueError("Accepted original script contains <final_script> markup")
    return text + "\n", acceptance


def _journal_path(root: Path) -> Path:
    return root / ".publication_journal" / "writing.json"


def _remove_journal(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temp_name = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def _recover_pending_writing(root: Path, brief: Brief) -> dict[str, Any] | None:
    journal = _journal_path(root)
    try:
        pending: dict[str, Any] = json.loads(journal.read_text(encoding="utf-8"))
        outputs: dict[str, str] = pending["outputs"]
        receipt: dict[str, Any] = pending["receipt"]
        expected = {"breaked_paragraphs.txt", "final_output.txt", "refined_script.txt"}
        if (
            pending.get("version") != 1
            or pending.get("kind") != "writing"
            or set(outputs) != expected
            or receipt.get("brief_sha256") != narration_fingerprint(brief)
            or receipt.get("outputs")
            != {name: fingerprint(value) for name, value in outputs.items()}
        ):
            return None
        if _FINAL_SCRIPT_TOKEN.search(outputs["refined_script.txt"]):
            return None
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    with publication_guard():
        if load_brief(root) != brief:
            raise ValueError("Brief changed before writing publication recovery")
        for name, text in outputs.items():
            atomic_text(root / name, text)
        atomic_write_json(str(root / "adaptive_writing_receipt.json"), receipt)
    _remove_journal(journal)
    verify_written_episode(root)
    return receipt


def _cached_response(
    root: Path, prompt: str, ask: Callable[[str], str], model: type[Response]
) -> Response:
    recipe = fingerprint(
        {
            "version": 2,
            "prompt": prompt,
            "schema": model.model_json_schema(),
            "model": getattr(ask, "model_name", "injected"),
        }
    )
    path = root / (recipe + ".json")
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("recipe") != recipe or fingerprint(cached["response"]) != cached["sha256"]:
            raise ValueError("Writing cache content mismatch")
        return model.model_validate(cached["response"])
    answer = request_json(prompt, ask, model)
    response = answer.model_dump()
    with publication_guard():
        atomic_write_json(
            str(path), {"recipe": recipe, "sha256": fingerprint(response), "response": response}
        )
    return answer


def write_episode(run_dir: str | Path, brief: Brief, ask: Callable[[str], str]) -> dict[str, Any]:
    """Write only a complete episode; interruptions preserve isolated paragraph caches."""
    root = Path(run_dir)
    if load_brief(root) != brief:
        raise ValueError("Writing brief is not the validated run brief")
    if (root / "source_audio_receipt.json").exists():
        raise ValueError("Source-narrated run cannot rewrite words already bound to published audio")
    recovered = _recover_pending_writing(root, brief)
    if recovered is not None:
        return recovered
    cache = root / "adaptive_writing"
    cache.mkdir(exist_ok=True)
    raw = (root / "raw_transcript.txt").read_text(encoding="utf-8-sig")
    words = raw.split()
    paragraphs = []
    for i in range(0, len(words), 1500):
        prompt = (
            writing_prompt(brief, "structure")
            + "\nInstead of prose, return this JSON schema:\n"
            + json.dumps(Paragraphs.model_json_schema())
            + "\nSOURCE:\n"
            + " ".join(words[i : i + 1500])
        )
        paragraphs.extend(_cached_response(cache, prompt, ask, Paragraphs).paragraphs)
    translated: list[str] = []
    refined: list[str] = []
    for index, source in enumerate(paragraphs, 1):
        for stage, text, target in (("translate", source, translated), ("refine", None, refined)):
            text = translated[-1] if text is None else text
            prompt = (
                writing_prompt(brief, stage)
                + "\nFor this request, replace prose/XML output formatting with this JSON schema:\n"
                + json.dumps(WrittenParagraph.model_json_schema())
            )
            prompt += (
                f"\nParagraph {index}/{len(paragraphs)}. Previous output for transition only:\n"
                + (target[-1][-700:] if target else "")
                + "\nSOURCE:\n"
                + text
            )
            output = _cached_response(cache, prompt, ask, WrittenParagraph).text
            target.append(output)
    outputs = {
        "breaked_paragraphs.txt": "\n\n".join(paragraphs),
        "final_output.txt": "\n\n".join(translated),
        # Keep raw refinements in cache and transition prompts; normalize only publication.
        "refined_script.txt": "\n\n".join(_final_script_text(text) for text in refined),
    }
    if load_brief(root) != brief:
        raise ValueError("Brief changed during writing")
    receipt = {
        "version": 1,
        "brief_sha256": narration_fingerprint(brief),
        "outputs": {name: fingerprint(text) for name, text in outputs.items()},
    }
    journal = _journal_path(root)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with publication_guard():
        atomic_write_json(
            str(journal),
            {"version": 1, "kind": "writing", "outputs": outputs, "receipt": receipt},
        )
    recovered = _recover_pending_writing(root, brief)
    if recovered is None:
        raise RuntimeError("Complete writing publication could not be recovered")
    return recovered


def publish_accepted_original(run_dir: str | Path, brief: Brief) -> dict[str, Any]:
    """Publish a human-accepted original script verbatim; never calls a model."""
    root = Path(run_dir)
    if load_brief(root) != brief:
        raise ValueError("Writing brief is not the validated run brief")
    if (root / "source_audio_receipt.json").exists():
        raise ValueError("Source-narrated run cannot rewrite words already bound to published audio")
    pending = _journal_path(root)
    if pending.exists():
        try:
            pending_mode = json.loads(pending.read_text(encoding="utf-8"))["receipt"].get("mode")
        except (OSError, KeyError, TypeError, AttributeError, ValueError):
            pending_mode = None
        if pending_mode != ACCEPTED_ORIGINAL_MODE:
            raise ValueError(
                "A pending non-accepted writing publication exists; finish it with the write stage"
            )
    recovered = _recover_pending_writing(root, brief)
    if recovered is not None:
        return recovered
    if (root / "adaptive_writing_receipt.json").exists():
        verify_written_episode(root)
        existing: dict[str, Any] = json.loads(
            (root / "adaptive_writing_receipt.json").read_text(encoding="utf-8")
        )
        if existing.get("mode") != ACCEPTED_ORIGINAL_MODE:
            raise ValueError("Run already has a different writing publication")
        return existing
    text, acceptance = _accepted_original_text(root, brief)
    outputs = dict.fromkeys(("breaked_paragraphs.txt", "final_output.txt", "refined_script.txt"), text)
    receipt = {
        "version": 1,
        "mode": ACCEPTED_ORIGINAL_MODE,
        "brief_sha256": narration_fingerprint(brief),
        "acceptance_sha256": fingerprint(acceptance),
        "outputs": {name: fingerprint(value) for name, value in outputs.items()},
    }
    journal = _journal_path(root)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with publication_guard():
        atomic_write_json(
            str(journal),
            {"version": 1, "kind": "writing", "outputs": outputs, "receipt": receipt},
        )
    recovered = _recover_pending_writing(root, brief)
    if recovered is None:
        raise RuntimeError("Complete writing publication could not be recovered")
    return recovered


def verify_written_episode(run_dir: str | Path) -> bool:
    root = Path(run_dir)
    brief = load_brief(root)
    receipt = json.loads((root / "adaptive_writing_receipt.json").read_text(encoding="utf-8"))
    if receipt["brief_sha256"] != narration_fingerprint(brief):
        raise ValueError("Writing receipt uses a stale brief")
    expected = {"breaked_paragraphs.txt", "final_output.txt", "refined_script.txt"}
    if set(receipt["outputs"]) != expected:
        raise ValueError("Incomplete writing receipt")
    for name, digest in receipt["outputs"].items():
        if fingerprint((root / name).read_text(encoding="utf-8")) != digest:
            raise ValueError(f"Writing output changed: {name}")
    source_receipt_exists = (root / "source_audio_receipt.json").exists()
    if not source_receipt_exists and receipt.get("mode") != "source_preserved":
        refined = (root / "refined_script.txt").read_text(encoding="utf-8")
        if _FINAL_SCRIPT_TOKEN.search(refined):
            raise ValueError("Refined script still contains <final_script> markup")
    if source_receipt_exists or receipt.get("mode") == "source_preserved":
        if not source_receipt_exists or receipt.get("mode") != "source_preserved":
            raise ValueError("Source narration and writing modes disagree")
        original = (root / "raw_transcript.txt").read_text(encoding="utf-8-sig").strip() + "\n"
        if any((root / name).read_text(encoding="utf-8") != original for name in expected):
            raise ValueError("Source-preserved writing differs from the spoken transcript")
        from .source_narration import verify_source_narration

        verify_source_narration(root)
    if receipt.get("mode") == ACCEPTED_ORIGINAL_MODE:
        text, acceptance = _accepted_original_text(root, brief)
        if receipt.get("acceptance_sha256") != fingerprint(acceptance):
            raise ValueError("Script acceptance changed since publication")
        if any((root / name).read_text(encoding="utf-8") != text for name in expected):
            raise ValueError("Accepted original writing differs from the accepted script")
    return True
