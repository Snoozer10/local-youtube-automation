"""Atomic pipeline manifest state for the YouTube automation pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast

MANIFEST_FILENAME = "pipeline_manifest.json"


class PhaseStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ChunkStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REPAIRED = "REPAIRED"
    FAILED = "FAILED"


def compute_script_hash(transcript_text: str, prompt_template_text: str, presets_text: str) -> str:
    return hashlib.sha256(
        "\n\x00\n".join([transcript_text, prompt_template_text, presets_text]).encode("utf-8")
    ).hexdigest()


class PipelineManifest:
    def __init__(self, data: dict[str, Any], path: Path, was_reset: bool) -> None:
        self._data = data
        self._path = path
        self.was_reset = was_reset

    @classmethod
    def _default_data(cls, project_id: str) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "script_hash": "",
            "roadmap_phase": {
                "status": PhaseStatus.PENDING.value,
                "total_lines": 0,
                "completed_pages": [],
                "last_processed_index": 0,
            },
            "planning_phase": {
                "status": PhaseStatus.PENDING.value,
                "chunk_size": 15,
                "total_chunks": 0,
                "chunks": {},
            },
            "rendering_phase": {"completed_indices": []},
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    @classmethod
    def load_or_create(cls, folder_path: str | Path, script_hash: str) -> PipelineManifest:
        folder = Path(folder_path)
        path = folder / MANIFEST_FILENAME
        was_reset = False
        if path.exists():
            with open(path, encoding="utf-8") as handle:
                data: dict[str, Any] = json.load(handle)
            if data.get("script_hash") != script_hash:
                project_id = data.get("project_id", folder.name)
                data = cls._default_data(project_id)
                was_reset = True
            data["script_hash"] = script_hash
            instance = cls(data, path, was_reset)
        else:
            folder.mkdir(parents=True, exist_ok=True)
            data = cls._default_data(folder.name)
            data["script_hash"] = script_hash
            instance = cls(data, path, was_reset=False)
        instance.save()
        return instance

    @property
    def path(self) -> Path:
        return self._path

    @property
    def project_id(self) -> str:
        return str(self._data["project_id"])

    @property
    def rendered_indices(self) -> list[int]:
        return list(self._data["rendering_phase"]["completed_indices"])

    def save(self) -> None:
        self._data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", dir=self._path.parent, delete=False, encoding="utf-8", suffix=".tmp"
            ) as handle:
                tmp_path = handle.name
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self._path)
            tmp_path = None
        finally:
            if tmp_path is not None and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def set_roadmap_status(self, status: PhaseStatus) -> None:
        self._data["roadmap_phase"]["status"] = status.value

    def set_roadmap_totals(self, total_lines: int) -> None:
        self._data["roadmap_phase"]["total_lines"] = total_lines

    def mark_roadmap_page_complete(self, page_number: int, last_index: int) -> None:
        completed_pages: list[int] = self._data["roadmap_phase"]["completed_pages"]
        if page_number not in completed_pages:
            completed_pages.append(page_number)
        self._data["roadmap_phase"]["last_processed_index"] = last_index

    def init_planning(self, chunk_size: int, total_chunks: int) -> None:
        planning = self._data["planning_phase"]
        planning["chunk_size"] = chunk_size
        planning["total_chunks"] = total_chunks

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        chunks: dict[str, Any] = self._data["planning_phase"]["chunks"]
        chunk = chunks.get(chunk_id)
        return dict(chunk) if chunk is not None else None

    def set_chunk_status(
        self, chunk_id: str, indices: list[int], status: ChunkStatus, attempts: int
    ) -> None:
        self._data["planning_phase"]["chunks"][chunk_id] = {
            "indices": list(indices),
            "status": status.value,
            "attempts": attempts,
        }

    def set_planning_status(self, status: PhaseStatus) -> None:
        self._data["planning_phase"]["status"] = status.value

    def all_chunks_done(self) -> bool:
        if self._data["planning_phase"].get("status") == PhaseStatus.COMPLETED.value:
            return True
        chunks: dict[str, Any] = self._data["planning_phase"]["chunks"]
        if not chunks:
            return False
        done_statuses = {ChunkStatus.VERIFIED.value, ChunkStatus.REPAIRED.value}
        return all(chunk.get("status") in done_statuses for chunk in chunks.values())

    def record_rendered(self, index: int) -> None:
        indices: list[int] = self._data["rendering_phase"]["completed_indices"]
        if index not in indices:
            indices.append(index)
        indices.sort()

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(json.dumps(self._data, ensure_ascii=False)))
