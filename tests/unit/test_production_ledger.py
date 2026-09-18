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
