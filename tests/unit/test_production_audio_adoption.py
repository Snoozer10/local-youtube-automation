import hashlib
import json
import struct
import wave

import pytest

from youtube_automation.production.contracts import Analysis, Brief, Channel, fingerprint
from youtube_automation.production.shots import Shot, ShotPlan, resolve_editorial_policy
from youtube_automation.timeline.engine import (
    build_timeline,
    build_words_from_whisper,
    save_timeline_and_shims,
)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wav(path, value):
    with wave.open(str(path), "wb") as handle:
        handle.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        handle.writeframes(value.to_bytes(2, "little") * 96000)


def adoption_run(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    channel = Channel(channel_id="cat", name="Cat", audience="adults", language="English",
                      dialect="standard", voice="voice", tone="calm", style="illustration",
                      allowed_treatments=["subject_scene"])
    (root / "raw_transcript.txt").write_text("Words stay")
    brief = Brief(source_sha256=fingerprint("Words stay"), profile_sha256=fingerprint(channel), channel=channel,
                  analysis=Analysis(topics=["animals"], claim_basis="factual", form="explanation",
                                    proposition="Observe", narrative_strategy="Observe",
                                    treatments=["subject_scene"], rationale="Concrete"))
    (root / "episode_brief.json").write_text(brief.model_dump_json())
    (root / "refined_script.txt").write_text("Words stay")
    _wav(root / "original.wav", 1)
    audio = tmp_path / "accepted.wav"
    _wav(audio, 2)
    words = build_words_from_whisper([{"word": "Words", "start": 0, "end": 2},
                                      {"word": "stay", "start": 2, "end": 4}], 4)
    timeline = build_timeline(words, 4, "original.wav")
    save_timeline_and_shims(timeline, str(root))
    shot = Shot(shot_id="s1", scene_id="animal", asset_id="a1", entity_ids=["cat"],
                span_ids=list(range(len(timeline["spans"]))), start_frame=0, end_frame=120,
                purpose="Show the cat watching", treatment="subject_scene", subject="Cat",
                visible_state="Cat watching a hand", setting="Garden", framing="medium",
                composition="Eye level")
    plan = ShotPlan(version=2, shots=[shot], brief_sha256=fingerprint(brief),
                    timeline_sha256=fingerprint(timeline), fps=30, total_frames=120,
                    editorial_policy=resolve_editorial_policy(brief))
    (root / "shot_plan.json").write_text(plan.model_dump_json())
    (root / "voice_generation_manifest.json").write_text('{"mode":"raw_synthesis"}')
    authority = tmp_path / "acceptance.json"
    authority.write_text(json.dumps({"record_type": "direct_user_audio_acceptance",
                                    "user_response": "Both files accepted", "files": [
                                        {"path": str(audio), "sha256": _digest(audio)}]}))
    request = {"audio_file": audio, "audio_sha256": _digest(audio), "acceptance_file": authority,
                   "acceptance_sha256": _digest(authority)}
    return root, request


def test_adoption_preserves_exact_bytes_and_is_stable(tmp_path):
    from youtube_automation.production.audio_adoption import (
        adopt_polished_audio,
        adoption_recipe,
        verify_audio_adoption,
    )

    root, request = adoption_run(tmp_path)
    before = json.loads((root / "timeline.json").read_text())
    shim_names = ("image_timestamps.txt", "timestamped_transcript.txt", "timestamped_transcript.srt", "subtitle_chunks.srt")
    shim_bodies = {name: (root / name).read_bytes() for name in shim_names}
    manifest = (root / "voice_generation_manifest.json").read_bytes()
    (root / "editorial_review.json").write_text("old critic")
    recipe = adoption_recipe(root, **request)
    receipt = adopt_polished_audio(root, **request)
    assert _digest(root / receipt["audio_path"]) == request["audio_sha256"]
    after = json.loads((root / "timeline.json").read_text())
    assert {key: value for key, value in after.items() if key not in {"audio_file", "audio_sha256"}} == {
        key: value for key, value in before.items() if key not in {"audio_file", "audio_sha256"}}
    assert (root / "voice_generation_manifest.json").read_bytes() == manifest
    assert {name: (root / name).read_bytes() for name in shim_names} == shim_bodies
    timeline_digest = _digest(root / "timeline.json")
    assert all((root / (name + ".sha256")).read_text().strip() == timeline_digest for name in shim_names)
    assert not (root / "editorial_review.json").exists()
    assert adoption_recipe(root, **request) == recipe
    assert adopt_polished_audio(root, **request) == receipt == verify_audio_adoption(root)


def test_changed_acceptance_and_incomplete_publication_fail_closed(tmp_path):
    from youtube_automation.production.audio_adoption import (
        adopt_polished_audio,
        capture_audio_state,
    )

    root, request = adoption_run(tmp_path)
    request["acceptance_file"].write_text("{}")
    with pytest.raises(ValueError, match="acceptance"):
        adopt_polished_audio(root, **request)
    (root / ".audio_adoption_publication.json").write_text("{}")
    with pytest.raises(ValueError, match="pending"):
        capture_audio_state(root)


@pytest.mark.parametrize("phase", ["PREPARED", "INVALIDATED"])
def test_interrupted_phase_resumes_exact_request(tmp_path, monkeypatch, phase):
    from youtube_automation.production import audio_adoption as adoption

    root, request = adoption_run(tmp_path)
    real = adoption._checkpoint

    def interrupt(root, pending, current):
        real(root, pending, current)
        if current == phase:
            raise InterruptedError("preserved injected interruption")

    with monkeypatch.context() as patch:
        patch.setattr(adoption, "_checkpoint", interrupt)
        with pytest.raises(InterruptedError):
            adoption.adopt_polished_audio(root, **request)
    with pytest.raises(ValueError, match="pending"):
        adoption.capture_audio_state(root)
    assert adoption.adopt_polished_audio(root, **request) == adoption.verify_audio_adoption(root)


@pytest.mark.parametrize("filename", ["timeline.json", "shot_plan.json", "audio_adoption_receipt.json",
                                      "image_timestamps.txt.sha256", "timestamped_transcript.txt.sha256",
                                      "timestamped_transcript.srt.sha256", "subtitle_chunks.srt.sha256"])
def test_partial_activation_resumes_with_real_platform_writer(tmp_path, monkeypatch, filename):
    from youtube_automation.production import audio_adoption as adoption

    root, request = adoption_run(tmp_path)
    real = adoption._publish_bytes

    def interrupt(path, value):
        real(path, value)
        if str(path) == str(root / filename):
            raise InterruptedError("after exact activation write")

    with monkeypatch.context() as patch:
        patch.setattr(adoption, "_publish_bytes", interrupt)
        with pytest.raises(InterruptedError):
            adoption.adopt_polished_audio(root, **request)
    assert adoption.adopt_polished_audio(root, **request) == adoption.verify_audio_adoption(root)


def test_adoption_preserves_active_rejection_assets_budget_and_raw_provenance(tmp_path):
    from youtube_automation.production.audio_adoption import adopt_polished_audio

    root, request = adoption_run(tmp_path)
    keep = {"human_review_rejection.json": b'{"reasons":["wrong scene"]}',
            "visual_budget.json": b'{"max_images":20}', "visual_spending.json": b'{"spent":7}',
            "asset_receipts/a1.json": b'{"sha256":"historical image"}',
            "accepted_assets/image.png": b"preserved accepted pixels"}
    for name, data in keep.items():
        path = root / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
    adopt_polished_audio(root, **request)
    assert {name: (root / name).read_bytes() for name in keep} == keep


def test_later_coherent_replan_and_old_snapshot_publication(tmp_path):
    from youtube_automation.production.audio_adoption import (
        adopt_polished_audio,
        assert_current_audio_state,
        capture_audio_state,
        verify_audio_adoption,
    )
    from youtube_automation.production.ledger import publication_guard

    root, request = adoption_run(tmp_path)
    with publication_guard():
        previous = capture_audio_state(root)
    receipt = adopt_polished_audio(root, **request)
    with publication_guard(), pytest.raises(ValueError, match="changed"):
        assert_current_audio_state(root, previous)
    plan = json.loads((root / "shot_plan.json").read_text())
    plan["shots"][0]["purpose"] = "Show a more specific visual beat"
    (root / "shot_plan.json").write_text(json.dumps(plan))
    assert verify_audio_adoption(root) == receipt


def test_tampered_recovery_snapshot_stays_blocked(tmp_path, monkeypatch):
    from youtube_automation.production import audio_adoption as adoption

    root, request = adoption_run(tmp_path)
    real = adoption._checkpoint

    def interrupt(root, pending, phase):
        real(root, pending, phase)
        raise InterruptedError("after preparation")

    with monkeypatch.context() as patch:
        patch.setattr(adoption, "_checkpoint", interrupt)
        with pytest.raises(InterruptedError):
            adoption.adopt_polished_audio(root, **request)
    pending = json.loads((root / adoption.PENDING).read_text())
    (root / ".audio_adoption" / pending["recipe"] / "inputs/timeline.json").write_text("{}")
    with pytest.raises(ValueError, match="snapshot"):
        adoption.adopt_polished_audio(root, **request)
    assert (root / adoption.PENDING).exists()


def test_omitted_plan_defaults_are_preserved_byte_semantically(tmp_path):
    from youtube_automation.production.audio_adoption import adopt_polished_audio

    root, request = adoption_run(tmp_path)
    plan = json.loads((root / "shot_plan.json").read_text())
    for shot in plan["shots"]:
        shot.pop("character_ids", None)
    (root / "shot_plan.json").write_text(json.dumps(plan))
    adopt_polished_audio(root, **request)
    after = json.loads((root / "shot_plan.json").read_text())
    assert {k: v for k, v in after.items() if k != "timeline_sha256"} == {
        k: v for k, v in plan.items() if k != "timeline_sha256"}


def test_new_unrecorded_downstream_activation_blocks_prepared_recovery(tmp_path, monkeypatch):
    from youtube_automation.production import audio_adoption as adoption

    root, request = adoption_run(tmp_path)
    real = adoption._checkpoint

    def interrupt(root, pending, phase):
        real(root, pending, phase)
        raise InterruptedError("after preparation")

    with monkeypatch.context() as patch:
        patch.setattr(adoption, "_checkpoint", interrupt)
        with pytest.raises(InterruptedError):
            adoption.adopt_polished_audio(root, **request)
    (root / "visual_audit.json").write_bytes(b"new unrelated review")
    with pytest.raises(ValueError, match="Unknown downstream"):
        adoption.adopt_polished_audio(root, **request)
    assert (root / "visual_audit.json").read_bytes() == b"new unrelated review"
    assert (root / adoption.PENDING).exists()


def _critic_response(plan):
    return {"version": 1, "plan_sha256": fingerprint(plan), "approved": True,
            "render_evidence_sha256": "f" * 64,
            "shots": [{"shot_id": shot.shot_id, "semantic_match": 4, "takeaway_match": 4,
                       "visual_specificity": 4, "verdict": "accept", "rationale": "Specific visible beat"}
                      for shot in plan.shots]}


def test_critic_digest_is_system_owned_and_renderer_change_requires_fresh_review(tmp_path, monkeypatch):
    from youtube_automation.production import render, shots

    root, _ = adoption_run(tmp_path)
    plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_text())
    brief = Brief.model_validate_json((root / "episode_brief.json").read_text())
    calls = []

    def ask(prompt):
        calls.append(prompt)
        return json.dumps(_critic_response(plan))

    first = shots.ensure_editorial_review(root, plan, json.loads((root / "timeline.json").read_text()), brief, ask)
    assert first.render_evidence_sha256 != "f" * 64
    assert shots.ensure_editorial_review(root, plan, json.loads((root / "timeline.json").read_text()), brief, ask) == first
    assert len(calls) == 1
    monkeypatch.setattr(render, "overlay_review_evidence", lambda *args: {"renderer": "changed"})
    # A pure supplied v3 brief tests consumption without manufacturing canonical v3 strategy.
    critic_root = tmp_path / "critic"
    critic_root.mkdir()
    (critic_root / "editorial_review.json").write_text(first.model_dump_json())
    with pytest.raises(ValueError, match="renderer evidence"):
        shots.require_editorial_review(critic_root, plan, brief.model_copy(update={"version": 3}))
    second = shots.ensure_editorial_review(root, plan, json.loads((root / "timeline.json").read_text()), brief, ask)
    assert len(calls) == 2
    assert second.render_evidence_sha256 != first.render_evidence_sha256


def test_critic_started_before_adoption_cannot_publish_stale_review(tmp_path):
    from youtube_automation.production import audio_adoption as adoption
    from youtube_automation.production import shots

    root, request = adoption_run(tmp_path)
    brief = Brief.model_validate_json((root / "episode_brief.json").read_text())
    plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_text())
    timeline = json.loads((root / "timeline.json").read_text())

    def ask(_):
        adoption.adopt_polished_audio(root, **request)
        return json.dumps(_critic_response(plan))

    with pytest.raises(ValueError, match="changed"):
        shots.ensure_editorial_review(root, plan, timeline, brief, ask)
    assert not (root / "editorial_review.json").exists()


def test_cli_adoption_uses_stable_recipe_and_no_provider_setup(tmp_path, monkeypatch):
    from youtube_automation.production import cli

    root, request = adoption_run(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline adoption must not enter provider setup")

    monkeypatch.setattr(cli, "active_profile_index", forbidden)
    flags = ["adopt-polished-audio", "--run-dir", str(root), "--polished-audio-file", str(request["audio_file"]),
             "--polished-audio-sha256", request["audio_sha256"], "--audio-acceptance-file", str(request["acceptance_file"]),
             "--audio-acceptance-sha256", request["acceptance_sha256"]]
    cli.main(flags)
    before = (root / "audio_adoption_receipt.json").read_bytes()
    cli.main(flags)
    assert (root / "audio_adoption_receipt.json").read_bytes() == before


def test_plan_job_recipe_tracks_renderer_without_hashing_its_own_plan(tmp_path, monkeypatch):
    from argparse import Namespace

    from youtube_automation.production import cli

    root, _ = adoption_run(tmp_path)
    args = Namespace(stage="plan", channel_profile=None, strategy_feedback_file=None)
    before = cli._stage_recipe(root, args)
    (root / "shot_plan.json").write_text("changed output does not alter its input recipe")
    assert cli._stage_recipe(root, args) == before
    monkeypatch.setattr(cli, "RENDERER_VERSION", cli.RENDERER_VERSION + 1)
    assert cli._stage_recipe(root, args) != before


@pytest.mark.parametrize("name", ["timeline.json", "shot_plan.json", "editorial_review.json"])
def test_deactivation_move_interruption_is_reconciled(tmp_path, monkeypatch, name):
    from pathlib import Path

    from youtube_automation.production import audio_adoption as adoption
    from youtube_automation.production import invalidation

    root, request = adoption_run(tmp_path)
    (root / "editorial_review.json").write_text("old critic")
    real = invalidation.os.replace

    def interrupt(source, target):
        real(source, target)
        if Path(source).name == name and ".adaptive_history" in Path(target).parts:
            raise InterruptedError("after recorded invalidation move")

    with monkeypatch.context() as patch:
        patch.setattr(invalidation.os, "replace", interrupt)
        with pytest.raises(InterruptedError):
            adoption.adopt_polished_audio(root, **request)
    assert adoption.adopt_polished_audio(root, **request) == adoption.verify_audio_adoption(root)


def test_marker_removal_interruption_resumes_and_same_json_other_bytes_conflicts(tmp_path, monkeypatch):
    from pathlib import Path

    from youtube_automation.production import audio_adoption as adoption

    root, request = adoption_run(tmp_path)
    real = Path.unlink

    def interrupt(path, *args, **kwargs):
        if path == root / adoption.PENDING:
            raise InterruptedError("before pending marker removal")
        return real(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", interrupt)
        with pytest.raises(InterruptedError):
            adoption.adopt_polished_audio(root, **request)
    canonical = root / "timeline.json"
    canonical.write_text(json.dumps(json.loads(canonical.read_text()), separators=(",", ":")))
    with pytest.raises(ValueError, match="Conflicting audio adoption activation"):
        adoption.adopt_polished_audio(root, **request)
    assert (root / adoption.PENDING).exists()


def test_original_header_warning_is_preserved_but_accepted_wav_must_be_compliant(tmp_path):
    from youtube_automation.production import audio_adoption as adoption

    root, request = adoption_run(tmp_path)
    original = root / "original.wav"
    data = bytearray(original.read_bytes())
    struct.pack_into("<I", data, 28, 96000)
    original.write_bytes(data)
    receipt = adoption.adopt_polished_audio(root, **request)
    assert original.read_bytes() == data
    assert receipt["pcm"]["sample_rate"] == 24000


@pytest.mark.parametrize("name", ["image_timestamps.txt.sha256", "timestamped_transcript.txt.sha256",
                                 "timestamped_transcript.srt.sha256", "subtitle_chunks.srt.sha256"])
def test_unknown_sidecar_collision_blocks_before_any_partial_activation(tmp_path, monkeypatch, name):
    from youtube_automation.production import audio_adoption as adoption

    root, request = adoption_run(tmp_path)
    real = adoption._checkpoint

    def interrupt(root, pending, phase):
        real(root, pending, phase)
        if phase == "INVALIDATED":
            raise InterruptedError("after deactivation")

    with monkeypatch.context() as patch:
        patch.setattr(adoption, "_checkpoint", interrupt)
        with pytest.raises(InterruptedError):
            adoption.adopt_polished_audio(root, **request)
    (root / name).write_bytes(b"unknown sidecar")
    with pytest.raises(ValueError, match="Conflicting audio adoption activation"):
        adoption.adopt_polished_audio(root, **request)
    assert not (root / "timeline.json").exists()
    assert not (root / "shot_plan.json").exists()
    assert (root / name).read_bytes() == b"unknown sidecar"


def test_legacy_absolute_audio_selection_is_allowed_only_inside_run(tmp_path):
    from youtube_automation.production.audio_adoption import adopt_polished_audio

    root, request = adoption_run(tmp_path)
    timeline = json.loads((root / "timeline.json").read_text())
    timeline["audio_file"] = str(root / "original.wav")
    save_timeline_and_shims(timeline, str(root))
    plan = json.loads((root / "shot_plan.json").read_text())
    plan["timeline_sha256"] = fingerprint(timeline)
    (root / "shot_plan.json").write_text(json.dumps(plan))
    assert adopt_polished_audio(root, **request)["original_audio_path"] == str(root / "original.wav")


def test_planning_snapshot_can_record_missing_media_but_adoption_requires_it(tmp_path):
    from youtube_automation.production.audio_adoption import (
        adopt_polished_audio,
        capture_audio_state,
    )
    from youtube_automation.production.ledger import publication_guard

    root, request = adoption_run(tmp_path)
    (root / "original.wav").unlink()
    with publication_guard():
        assert capture_audio_state(root)["audio"][1] is None
    with pytest.raises(FileNotFoundError):
        adopt_polished_audio(root, **request)
    assert not (root / ".audio_adoption_publication.json").exists()


def test_visual_audit_rejects_plan_bound_to_another_timeline_before_encoder_work(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from youtube_automation.production import render, visual_gate

    (tmp_path / "timeline.json").write_text('{"audio_file":"missing.wav"}')

    def forbidden(*args, **kwargs):
        raise AssertionError("Lineage mismatch must stop before native render inputs")

    monkeypatch.setattr(render, "current_render_inputs", forbidden)
    with pytest.raises(ValueError, match="audio/plan lineage"):
        visual_gate._current_render_inputs_for_audit(tmp_path, SimpleNamespace(timeline_sha256="a" * 64), {}, None)


@pytest.mark.parametrize("entry", ["flow", "render", "proofs", "review", "audit", "assets"])
def test_adopted_v2_visual_entries_require_migration_before_side_effects(tmp_path, monkeypatch, entry):
    from youtube_automation.production import flow, render, render_proofs, review, visual_gate
    from youtube_automation.production.audio_adoption import adopt_polished_audio
    from youtube_automation.production.contracts import load_brief

    root, request = adoption_run(tmp_path)
    adopt_polished_audio(root, **request)
    brief = load_brief(root)
    plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_bytes())
    assert brief.version == 2

    def forbidden(*args, **kwargs):
        pytest.fail("Adopted v2 reached planning, provider, or render work before migration")

    monkeypatch.setattr(flow, "ensure_shot_plan", forbidden)
    monkeypatch.setattr(render, "validate_plan", forbidden)
    monkeypatch.setattr(render_proofs, "validate_plan", forbidden)
    monkeypatch.setattr(review, "validate_plan", forbidden)
    monkeypatch.setattr(visual_gate, "_current_render_inputs_for_audit", forbidden)
    calls = {
        "flow": lambda: flow.prepare_flow(root, forbidden),
        "render": lambda: render.render_plan(root, {}),
        "proofs": lambda: render_proofs.render_current_proofs(root),
        "review": lambda: review.review_context(root),
        "audit": lambda: visual_gate.require_visual_audit(root, plan, brief),
        "assets": lambda: flow.verify_generated_assets(root, plan, brief),
    }
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="editorial-policy v3 migration and a fresh critic"):
        calls[entry]()
    assert {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_adopted_v3_guard_delegates_current_critic_without_provider_work(tmp_path, monkeypatch):
    from youtube_automation.production import shots
    from youtube_automation.production.audio_adoption import adopt_polished_audio
    from youtube_automation.production.contracts import load_brief

    root, request = adoption_run(tmp_path)
    adopt_polished_audio(root, **request)
    from youtube_automation.production.audio_adoption import require_adopted_audio_review
    from youtube_automation.production.contracts import EpisodeVisualStrategy

    original = load_brief(root)
    channel = original.channel.model_copy(update={"version": 3,
        "visual_directives": ["Concrete narrative scenes"], "forbidden_motifs": ["Decorative dashboards"]})
    strategy = EpisodeVisualStrategy(source_sha256=original.source_sha256, topic="Words stay",
        viewer_question="What stays?", central_promise="Preserve the spoken words",
        evidence_mode="explanatory", emotional_arc=["curiosity", "understanding"],
        hook_archetype="mystery_gap", hook_microbeats=[
            {"beat_id": "problem", "function": "problem", "duration_seconds": 3,
             "viewer_takeaway": "Words matter", "visual_mode": "human_context"},
            {"beat_id": "gap", "function": "curiosity", "duration_seconds": 3,
             "viewer_takeaway": "What stays?", "visual_mode": "kinetic_type"},
            {"beat_id": "promise", "function": "promise", "duration_seconds": 3,
             "viewer_takeaway": "Preserve words", "visual_mode": "human_context"}],
        visual_modes=["human_context", "kinetic_type"], pacing="Three clear hook beats",
        motion_grammar=["Animate meaningful state changes"])
    brief = Brief(version=3, source_sha256=original.source_sha256,
        profile_sha256=fingerprint(channel), channel=channel, analysis=original.analysis,
        visual_strategy=strategy)
    (root / "episode_brief.json").write_text(brief.model_dump_json())
    plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_bytes())
    calls = []

    def current_critic(run, candidate, current_brief):
        calls.append((run, candidate, current_brief))
        raise ValueError("Fresh critic required")

    monkeypatch.setattr(shots, "require_editorial_review", current_critic)
    with pytest.raises(ValueError, match="Fresh critic required"):
        require_adopted_audio_review(root, brief, plan)
    assert calls == [(root, plan, brief)]
    assert not (root / "visual_audit.json").exists()



def test_flow_rechecks_policy_if_adoption_finishes_during_planning(tmp_path, monkeypatch):
    from youtube_automation.production import flow
    from youtube_automation.production.audio_adoption import adopt_polished_audio

    root, request = adoption_run(tmp_path)

    def complete_adoption_then_return_plan(run, ask):
        adopt_polished_audio(run, **request)
        return ShotPlan.model_validate_json((run / "shot_plan.json").read_bytes())

    monkeypatch.setattr(flow, "ensure_shot_plan", complete_adoption_then_return_plan)
    with pytest.raises(ValueError, match="editorial-policy v3 migration and a fresh critic"):
        flow.prepare_flow(root, lambda prompt: pytest.fail("No provider calls"))
    assert not (root / "flow_prompts.json").exists()


def test_visual_strategy_migration_preserves_accepted_audio_and_owner_rejection(tmp_path):
    from tests.unit.test_production_briefs import migration_fixture
    from youtube_automation.production.audio_adoption import (
        adopt_polished_audio,
        verify_audio_adoption,
    )
    from youtube_automation.production.briefs import load_brief, rebind_visual_policy
    from youtube_automation.production.contracts import narration_fingerprint
    from youtube_automation.production.review import HumanPreviewRejection

    root, request = adoption_run(tmp_path)
    receipt = adopt_polished_audio(root, **request)
    old = load_brief(root)
    _, target, strategy = migration_fixture(tmp_path / "policy-fixture", old.channel)
    rejection = HumanPreviewRejection(reviewer="owner", overall_rating=1.5,
        plan_sha256="1" * 64, preview_sha256="2" * 64, source_sha256=old.source_sha256,
        reasons=["Repeated generic scenes"], required_next="Fresh source-specific visual plan", source="owner")
    (root / "human_review_rejection.json").write_text(rejection.model_dump_json())
    (root / "visual_budget.json").write_text('{"spent":18,"maximum":20}')
    names = ["raw_transcript.txt", "refined_script.txt", "timeline.json", "audio_adoption_receipt.json",
             "voice_generation_manifest.json", "human_review_rejection.json", "visual_budget.json",
             "image_timestamps.txt", "timestamped_transcript.txt", "timestamped_transcript.srt", "subtitle_chunks.srt"]
    protected = {name: (root / name).read_bytes() for name in names}
    audio = (root / receipt["audio_path"]).read_bytes()
    prompts = []
    migrated = rebind_visual_policy(root, target, ask=lambda prompt: prompts.append(prompt) or strategy.model_dump_json())
    assert len(prompts) == 1 and "Repeated generic scenes" in prompts[0]
    assert narration_fingerprint(migrated) == narration_fingerprint(old)
    assert migrated.channel.voice == old.channel.voice
    assert all((root / name).read_bytes() == data for name, data in protected.items())
    assert (root / receipt["audio_path"]).read_bytes() == audio
    assert verify_audio_adoption(root) == receipt
    assert not (root / "shot_plan.json").exists()
