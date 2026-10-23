"""Offline production-boundary and caller-selected artifact receipt tests."""

import hashlib
import json

import pytest

from youtube_automation.production.contracts import (
    Analysis,
    Brief,
    fingerprint,
    load_channel,
    narration_fingerprint,
)
from youtube_automation.production.direction_stage import (
    VoiceDirectionError,
    ensure_direction_candidate,
)


def test_snoozer_null_voice_fails_at_public_stage_before_transport(tmp_path):
    channel = load_channel("channels/snoozer-anime.json")
    assert channel.voice is None
    assert channel.channel_id == "snoozer-anime"
    source = "A short source used only to exercise the local production guard."
    script = "A local test narration with enough words for a direction request."
    brief = Brief(
        source_sha256=fingerprint(source),
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=Analysis(
            topics=["test"],
            claim_basis="factual",
            form="chronology",
            proposition="A local guard test",
            narrative_strategy="Follow the supplied source",
            treatments=["subject_scene"],
            rationale="A bounded offline unit fixture",
        ),
    )
    (tmp_path / "raw_transcript.txt").write_text(source, encoding="utf-8")
    (tmp_path / "episode_brief.json").write_text(brief.model_dump_json(), encoding="utf-8")
    outputs = {}
    for name in ("breaked_paragraphs.txt", "final_output.txt", "refined_script.txt"):
        (tmp_path / name).write_text(script, encoding="utf-8")
        outputs[name] = fingerprint(script)
    (tmp_path / "adaptive_writing_receipt.json").write_text(
        json.dumps(
            {
                "brief_sha256": narration_fingerprint(brief),
                "outputs": outputs,
            }
        ),
        encoding="utf-8",
    )

    transport_calls = []
    with pytest.raises(VoiceDirectionError, match="selected channel voice"):
        ensure_direction_candidate(
            tmp_path,
            lambda prompt: transport_calls.append(prompt),
        )
    assert transport_calls == []


def test_explicit_artifact_receipt_verifier_uses_only_selected_tmp_files(tmp_path):
    from tools.audit_adaptive_artifact_receipt import audit_receipt

    artifact = tmp_path / "selected.bin"
    artifact.write_bytes(b"sanitized acceptance fixture")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "artifacts": [
                    {
                        "path": artifact.name,
                        "size_bytes": artifact.stat().st_size,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = audit_receipt(receipt)
    assert result[0]["path"] == str(artifact.resolve())
    assert result[0]["size_bytes"] == artifact.stat().st_size


def test_explicit_artifact_receipt_verifier_rejects_changed_bytes(tmp_path):
    from tools.audit_adaptive_artifact_receipt import ReceiptError, audit_receipt

    artifact = tmp_path / "selected.bin"
    artifact.write_bytes(b"before")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "artifacts": [
                    {
                        "path": artifact.name,
                        "size_bytes": artifact.stat().st_size,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    artifact.write_bytes(b"after")

    with pytest.raises(ReceiptError, match="pin mismatch"):
        audit_receipt(receipt)


def test_explicit_artifact_receipt_verifier_rejects_unknown_semantic_check(tmp_path):
    from tools.audit_adaptive_artifact_receipt import ReceiptError, audit_receipt

    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "artifacts": [],
                "semantic_checks": [{"type": "unknown"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReceiptError, match="unknown semantic check"):
        audit_receipt(receipt)
