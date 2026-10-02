"""Channel-aware writing with resumable, content-bound paragraph artifacts."""

from __future__ import annotations

import json
import os
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
        "refined_script.txt": "\n\n".join(refined),
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
    if source_receipt_exists or receipt.get("mode") == "source_preserved":
        if not source_receipt_exists or receipt.get("mode") != "source_preserved":
            raise ValueError("Source narration and writing modes disagree")
        original = (root / "raw_transcript.txt").read_text(encoding="utf-8-sig").strip() + "\n"
        if any((root / name).read_text(encoding="utf-8") != original for name in expected):
            raise ValueError("Source-preserved writing differs from the spoken transcript")
        from .source_narration import verify_source_narration

        verify_source_narration(root)
    return True
