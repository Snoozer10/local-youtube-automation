import json
from pathlib import Path

import pytest

from pipeline_manifest import (
    MANIFEST_FILENAME,
    ChunkStatus,
    PhaseStatus,
    PipelineManifest,
    compute_script_hash,
)


def _load_json(folder: Path) -> dict:
    with open(folder / MANIFEST_FILENAME, encoding="utf-8") as handle:
        return json.load(handle)


def test_create_default_roundtrip(tmp_path: Path) -> None:
    manifest = PipelineManifest.load_or_create(tmp_path, "hash1")
    assert manifest.project_id == tmp_path.name
    assert manifest.was_reset is False
    data = _load_json(tmp_path)
    assert data["project_id"] == tmp_path.name
    assert data["script_hash"] == "hash1"
    assert data["roadmap_phase"]["status"] == "PENDING"
    assert data["roadmap_phase"]["total_lines"] == 0
    assert data["roadmap_phase"]["completed_pages"] == []
    assert data["roadmap_phase"]["last_processed_index"] == 0
    assert data["planning_phase"]["status"] == "PENDING"
    assert data["planning_phase"]["chunk_size"] == 15
    assert data["planning_phase"]["total_chunks"] == 0
    assert data["planning_phase"]["chunks"] == {}
    assert data["rendering_phase"] == {"completed_indices": []}
    assert "last_updated" in data


def test_load_existing_preserves_state(tmp_path: Path) -> None:
    first = PipelineManifest.load_or_create(tmp_path, "hash1")
    first.set_roadmap_status(PhaseStatus.IN_PROGRESS)
    first.set_roadmap_totals(120)
    first.mark_roadmap_page_complete(2, 40)
    first.set_chunk_status("chunk_1", [1, 15], ChunkStatus.VERIFIED, 1)
    first.record_rendered(3)
    first.save()

    second = PipelineManifest.load_or_create(tmp_path, "hash1")
    assert second.was_reset is False
    assert second.get_chunk("chunk_1") is not None
    assert second.rendered_indices == [3]
    assert _load_json(tmp_path)["roadmap_phase"]["status"] == "IN_PROGRESS"


def test_hash_mismatch_resets_phases(tmp_path: Path) -> None:
    first = PipelineManifest.load_or_create(tmp_path, "old-hash")
    first.set_roadmap_totals(99)
    first.set_chunk_status("chunk_1", [1, 15], ChunkStatus.FAILED, 3)
    first.record_rendered(7)
    first.save()

    second = PipelineManifest.load_or_create(tmp_path, "new-hash")
    assert second.was_reset is True
    assert second.project_id == tmp_path.name
    assert second.rendered_indices == []
    assert second.get_chunk("chunk_1") is None
    assert second.all_chunks_done() is False
    reloaded = _load_json(tmp_path)
    assert reloaded["script_hash"] == "new-hash"
    assert reloaded["roadmap_phase"]["total_lines"] == 0


def test_save_produces_valid_json_readable_back(tmp_path: Path) -> None:
    manifest = PipelineManifest.load_or_create(tmp_path, "hash1")
    manifest.set_chunk_status("chunk_2", [16, 30], ChunkStatus.REPAIRED, 2)
    manifest.save()
    data = _load_json(tmp_path)
    assert data["planning_phase"]["chunks"]["chunk_2"] == {
        "indices": [16, 30],
        "status": "REPAIRED",
        "attempts": 2,
    }
    again = PipelineManifest.load_or_create(tmp_path, "hash1")
    chunk = again.get_chunk("chunk_2")
    assert chunk is not None
    assert chunk["status"] == "REPAIRED"


def test_mark_roadmap_page_complete_appends_and_sets_last_index(tmp_path: Path) -> None:
    manifest = PipelineManifest.load_or_create(tmp_path, "hash1")
    manifest.mark_roadmap_page_complete(3, 45)
    manifest.mark_roadmap_page_complete(5, 75)
    manifest.mark_roadmap_page_complete(3, 80)
    manifest.save()
    roadmap = _load_json(tmp_path)["roadmap_phase"]
    assert roadmap["completed_pages"] == [3, 5]
    assert roadmap["last_processed_index"] == 80


@pytest.mark.parametrize(
    "status", [ChunkStatus.VERIFIED, ChunkStatus.REPAIRED, ChunkStatus.FAILED, ChunkStatus.PENDING]
)
def test_set_chunk_status_writes_enum_strings(tmp_path: Path, status: ChunkStatus) -> None:
    manifest = PipelineManifest.load_or_create(tmp_path, "hash1")
    manifest.set_chunk_status("chunk_1", [1, 15], status, 4)
    manifest.save()
    chunk = _load_json(tmp_path)["planning_phase"]["chunks"]["chunk_1"]
    assert chunk["status"] == status.value
    assert chunk["indices"] == [1, 15]
    assert chunk["attempts"] == 4


def test_get_chunk_unknown_returns_none(tmp_path: Path) -> None:
    manifest = PipelineManifest.load_or_create(tmp_path, "hash1")
    assert manifest.get_chunk("missing") is None


def test_all_chunks_done_logic(tmp_path: Path) -> None:
    empty = PipelineManifest.load_or_create(tmp_path, "hash1")
    assert empty.all_chunks_done() is False

    empty.init_planning(15, 2)
    empty.set_chunk_status("chunk_1", [1, 15], ChunkStatus.PENDING, 0)
    assert empty.all_chunks_done() is False

    mixed = PipelineManifest.load_or_create(tmp_path, "hash1")
    mixed.init_planning(15, 3)
    mixed.set_chunk_status("chunk_1", [1, 15], ChunkStatus.VERIFIED, 1)
    mixed.set_chunk_status("chunk_2", [16, 30], ChunkStatus.REPAIRED, 2)
    mixed.set_chunk_status("chunk_3", [31, 45], ChunkStatus.PENDING, 0)
    assert mixed.all_chunks_done() is False

    done = PipelineManifest.load_or_create(tmp_path, "hash1")
    done.init_planning(15, 2)
    done.set_chunk_status("chunk_1", [1, 15], ChunkStatus.VERIFIED, 1)
    done.set_chunk_status("chunk_2", [16, 30], ChunkStatus.REPAIRED, 2)
    assert done.all_chunks_done() is True

    failed = PipelineManifest.load_or_create(tmp_path, "hash1")
    failed.init_planning(15, 2)
    failed.set_chunk_status("chunk_1", [1, 15], ChunkStatus.VERIFIED, 1)
    failed.set_chunk_status("chunk_2", [16, 30], ChunkStatus.FAILED, 3)
    assert failed.all_chunks_done() is False

    # Status override to COMPLETED allows all_chunks_done to return True
    completed_manifest = PipelineManifest.load_or_create(tmp_path, "hash1")
    completed_manifest.set_planning_status(PhaseStatus.COMPLETED)
    assert completed_manifest.all_chunks_done() is True


def test_record_rendered_dedup_and_sort(tmp_path: Path) -> None:
    manifest = PipelineManifest.load_or_create(tmp_path, "hash1")
    for index in (5, 1, 9, 5, 3, 9):
        manifest.record_rendered(index)
    manifest.save()
    assert manifest.rendered_indices == [1, 3, 5, 9]
    assert _load_json(tmp_path)["rendering_phase"]["completed_indices"] == [1, 3, 5, 9]


def test_atomic_save_leaves_no_tmp_residue(tmp_path: Path) -> None:
    manifest = PipelineManifest.load_or_create(tmp_path, "hash1")
    manifest.set_roadmap_totals(10)
    manifest.save()
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == [MANIFEST_FILENAME]


def test_compute_script_hash_deterministic_and_separator_sensitive() -> None:
    a = compute_script_hash("transcript", "template", "presets")
    b = compute_script_hash("transcript", "template", "presets")
    c = compute_script_hash("transcript\ntemplate\npresets", "", "")
    assert a == b
    assert len(a) == 64
    assert a != c
