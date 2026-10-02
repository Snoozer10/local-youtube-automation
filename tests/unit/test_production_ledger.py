import pytest

from youtube_automation.production.ledger import Ledger


def test_exclusive_claim_expiry_and_fencing(tmp_path):
    one = Ledger(tmp_path / "jobs.db")
    two = Ledger(tmp_path / "jobs.db")
    first = one.claim("browser", "r1", "worker1", now=100)
    assert two.claim("browser", "r1", "worker2", now=101) is None
    second = two.claim("browser", "r1", "worker2", now=161)
    assert second > first
    with pytest.raises(RuntimeError, match="Stale"):
        one.finish("browser", "worker1", first, "SUCCEEDED", {}, now=162)
    two.heartbeat("browser", "worker2", second, now=170)
    two.finish("browser", "worker2", second, "SUCCEEDED", {"verified": True}, now=171)
    assert one.status()[0]["state"] == "SUCCEEDED"


def test_expired_worker_cannot_renew_without_reclaim(tmp_path):
    db = Ledger(tmp_path / "jobs.db")
    fence = db.claim("render", "hash", "one", seconds=1, now=0)
    with pytest.raises(RuntimeError, match="Lost"):
        db.heartbeat("render", "one", fence, now=2)


def test_stale_lease_cannot_publish(tmp_path, monkeypatch):
    from youtube_automation.production import ledger

    database = tmp_path / "jobs.db"
    now = [100.0]
    monkeypatch.setattr(ledger.time, "time", lambda: now[0])
    published = tmp_path / "active.json"
    with pytest.raises(RuntimeError, match="publication blocked"):
        with ledger.leased_resource(database, "encoder"):
            now[0] = 161.0
            replacement = Ledger(database)
            assert replacement.claim("encoder", "new", "second", now=now[0]) is not None
            with ledger.publication_guard():
                published.write_text("wrong worker")
    assert not published.exists()
    assert Ledger(database).status()[0]["owner"] == "second"


def test_current_lease_can_publish_and_release(tmp_path):
    from youtube_automation.production.ledger import leased_resource, publication_guard

    database = tmp_path / "jobs.db"
    with leased_resource(database, "encoder"):
        with publication_guard():
            (tmp_path / "active.json").write_text("verified")
    assert Ledger(database).status()[0]["state"] == "SUCCEEDED"


def test_durable_stage_skips_success_and_restarts_for_new_recipe(tmp_path):
    from youtube_automation.production.ledger import durable_stage, publication_guard

    database = tmp_path / "jobs.db"
    with durable_stage(database, "stage:run:plan", "recipe-1") as execute:
        assert execute is True
        with publication_guard():
            (tmp_path / "plan.json").write_text("one")
    with durable_stage(database, "stage:run:plan", "recipe-1") as execute:
        assert execute is False
    with durable_stage(database, "stage:run:plan", "recipe-2") as execute:
        assert execute is True
        with publication_guard():
            (tmp_path / "plan.json").write_text("two")
    row = Ledger(database).status()[0]
    assert row["recipe"] == "recipe-2"
    assert row["attempts"] == 1


def test_stage_circuit_breaker_and_force_retry(tmp_path):
    database = tmp_path / "jobs.db"
    ledger = Ledger(database)
    for attempt in range(3):
        owner = f"worker-{attempt}"
        claim = ledger.claim_stage("stage:run:generate", "recipe", owner, now=attempt * 10)
        assert claim.state == "CLAIMED"
        ledger.finish(
            "stage:run:generate",
            owner,
            claim.fence,
            "FAILED",
            {"error": "provider failed"},
            now=attempt * 10 + 1,
        )
    assert ledger.claim_stage("stage:run:generate", "recipe", "blocked", now=40).state == "BLOCKED"
    forced = ledger.claim_stage(
        "stage:run:generate", "recipe", "operator", force=True, now=41
    )
    assert forced.state == "CLAIMED"
    assert Ledger(database).status()[0]["attempts"] == 1


def test_expired_stage_worker_is_reclaimed_and_fenced(tmp_path):
    database = tmp_path / "jobs.db"
    ledger = Ledger(database)
    first = ledger.claim_stage("stage:run:generate", "recipe", "first", seconds=1, now=0)
    second = ledger.claim_stage("stage:run:generate", "recipe", "second", seconds=1, now=2)
    assert first.state == second.state == "CLAIMED"
    assert second.fence > first.fence
    with pytest.raises(RuntimeError, match="Stale"):
        ledger.finish(
            "stage:run:generate", "first", first.fence, "SUCCEEDED", {}, now=2.5
        )


def test_stage_and_resource_leases_nest_and_both_fence_publication(tmp_path):
    from youtube_automation.production.ledger import (
        durable_stage,
        leased_resource,
        publication_guard,
    )

    database = tmp_path / "jobs.db"
    with durable_stage(database, "stage:run:preview", "recipe") as execute:
        assert execute is True
        with leased_resource(database, "encoder"):
            with publication_guard():
                (tmp_path / "active.json").write_text("verified")
    rows = {row["key"]: row for row in Ledger(database).status()}
    assert rows["stage:run:preview"]["state"] == "SUCCEEDED"
    assert rows["encoder"]["state"] == "SUCCEEDED"
