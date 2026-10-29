import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from load_quoting_swarm.chain.discord import publish_exception, verify_interaction
from load_quoting_swarm.chain.economics import ROOT, fleet_economics, validate_fleet
from load_quoting_swarm.chain.service import ChainService
from load_quoting_swarm.chain.web import make_handler
from load_quoting_swarm.chain.chain_planner import plan_day, evaluate, State, parse
from load_quoting_swarm.web import LoadboardState


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("HB_ENABLE_CHAIN", "1")
    fleet = json.loads((ROOT / "data/fleet/fleet_100_v1.json").read_text())
    fleet["trucks"] = fleet["trucks"][:3]  # includes a NEEDS_HUMAN truck
    path = tmp_path / "fleet.json"
    path.write_text(json.dumps(fleet))
    return ChainService(storage=tmp_path / "state", fleet_path=path)


def test_flag_is_required_and_read_does_not_book(service, monkeypatch):
    assert not service.ledger.events()
    service.payload()
    assert not service.ledger.events()
    monkeypatch.delenv("HB_ENABLE_CHAIN")
    with pytest.raises(PermissionError):
        service.commit()
    item = service.payload()["exceptions"][0]
    with pytest.raises(PermissionError):
        service.resolve(item["exception_id"], "APPROVE", "human")


def test_concurrent_commits_use_existing_ledger_once(service):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: service.commit(), range(4)))
    events = service.ledger.events()
    quoted = [e for e in events if e["event"] == "QUOTED"]
    decisions = [e for e in events if e["event"] == "HUMAN_DECISION"]
    assert quoted and len(quoted) == len(decisions)
    assert len({e["load_id"] for e in quoted}) == len(quoted)
    assert all(e["manager"] == "policy:auto-book-v1" for e in decisions)


def test_restart_uses_pinned_plan_and_idempotent_bookings(service):
    service.commit()
    original = service.payload()
    restarted = ChainService(storage=service.storage, fleet_path=service.storage.parent / "fleet.json", diesel_ppl=250)
    restarted.commit()
    assert restarted.payload() == original


def test_no_legal_home_approval_only_acknowledges(service):
    item = next(e for e in service.payload()["exceptions"] if e["reason"] == "NEEDS_HUMAN")
    result = service.resolve(item["exception_id"], "APPROVE", "discord:123")
    assert result["status"] == "ACKNOWLEDGED_NEEDS_MANUAL_DISPATCH"
    assert not service.ledger.events()
    with pytest.raises(ValueError, match="already resolved"):
        service.resolve(item["exception_id"], "APPROVE", "discord:123")
    assert service.payload()["exceptions"][0]["resolution"]["manager"] == "discord:123"


def test_escalation_remains_unbooked_and_requires_identity(service):
    item = service.payload()["exceptions"][0]
    for manager in ("", "policy:fake"):
        with pytest.raises(ValueError):
            service.resolve(item["exception_id"], "APPROVE", manager)
    assert service.resolve(item["exception_id"], "ESCALATE", "alice")["status"] == "ESCALATED"
    assert not service.ledger.events()


def test_impossible_single_chain_has_no_illegal_home_segment():
    scn = json.loads((ROOT / "data/chain/chain_scenario_v1.json").read_text())
    scn["config"]["home_by"] = "14:00"
    plan = plan_day(scn)
    assert plan["summary"]["home_at"] is None
    assert all(e.get("label") != "drive home" for e in plan["blocks"])


def test_config_and_diesel_change_cost_and_speed():
    base = {"max_daily_driving_h": 9, "break_after_h": 4.5, "break_minutes": 45}
    a = fleet_economics(base, "18t Curtain Side, Tail Lift", diesel_ppl=100)
    b = fleet_economics(base, "18t Curtain Side, Tail Lift", diesel_ppl=250)
    assert a["cost_per_mile_gbp"] < b["cost_per_mile_gbp"]
    assert a["hgv_speed_mph"] == 40 and a["driver_cost_per_hour_gbp"] == 18.5
    with pytest.raises(ValueError):
        fleet_economics(dict(base, max_daily_driving_h=10), "18t Curtain Side, Tail Lift")
    with pytest.raises(ValueError):
        fleet_economics(base, "18t Curtain Side, Tail Lift", diesel_ppl=float("nan"))


def test_duplicate_inputs_fail_instead_of_silently_overwriting(service):
    fleet = service.fleet
    fleet["board"].append(fleet["board"][0])
    with pytest.raises(ValueError, match="duplicate"):
        validate_fleet(fleet)


def test_one_retries_before_webhook_and_errors_are_sanitized(monkeypatch):
    calls = []
    class Failed:
        def execute_one_action(self, payload):
            calls.append("one")
            raise RuntimeError("secret-webhook-URL-must-not-leak")
    class Response:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def opener(request, **kwargs):
        calls.append("webhook")
        assert b"components" not in request.data
        return Response()
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/example/test")
    result = publish_exception(dict(exception_id="x", truck_id="T", reason="NEEDS_HUMAN", detail="test"), publisher_factory=Failed, opener=opener)
    assert calls == ["one", "one", "webhook"]
    assert result["delivery"] == "webhook_fallback"
    assert "secret-webhook" not in json.dumps(result)


def test_one_success_does_not_use_webhook():
    class Success:
        def execute_one_action(self, payload): return {"id": "message"}
    result = publish_exception(dict(exception_id="x", truck_id="T", reason="TEST", detail="test"), publisher_factory=Success)
    assert result["delivery"] == "one" and result["execute_one_action_succeeded"]


def test_discord_signature_and_staleness():
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw().hex()
    raw = b'{"type":1}'
    timestamp = str(int(time.time()))
    signature = key.sign(timestamp.encode() + raw).hex()
    verify_interaction(raw, signature, timestamp, public)
    for body, stamp in ((raw + b" ", timestamp), (raw, "0")):
        with pytest.raises(ValueError):
            verify_interaction(body, signature, stamp, public)


@pytest.fixture
def http_server(service, tmp_path):
    state = LoadboardState(ROOT / "data/loads_v2.json", tmp_path / "old-ledger.jsonl")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state, service, auth_username="test", auth_password="secret"))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown(); server.server_close(); worker.join()


def test_http_flag_auth_and_signed_exception_loop(http_server, service, monkeypatch):
    monkeypatch.delenv("HB_ENABLE_CHAIN")
    with pytest.raises(HTTPError) as error:
        urlopen(http_server + "/api/fleet")
    assert error.value.code == 404
    monkeypatch.setenv("HB_ENABLE_CHAIN", "1")
    with pytest.raises(HTTPError) as error:
        urlopen(http_server + "/api/fleet")
    assert error.value.code == 401
    request = Request(http_server + "/api/fleet", headers={"Authorization": "Basic dGVzdDpzZWNyZXQ="})
    with urlopen(request) as response:
        assert len(json.load(response)["trucks"]) == 3
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", key.public_key().public_bytes_raw().hex())
    monkeypatch.setenv("ONE_DISCORD_CHANNEL_ID", "channel")
    monkeypatch.setenv("HB_DISCORD_MANAGER_IDS", "123")
    item = service.payload()["exceptions"][0]
    body = {"type": 3, "channel_id": "channel", "member": {"user": {"id": "123"}},
            "data": {"custom_id": "chain:APPROVE:" + item["exception_id"]}}
    def send(value, signed=True):
        raw = json.dumps(value).encode(); timestamp = str(int(time.time()))
        headers = {"X-Signature-Timestamp": timestamp, "X-Signature-Ed25519": key.sign(timestamp.encode()+raw).hex() if signed else "bad"}
        return urlopen(Request(http_server + "/api/chain/discord/interactions", data=raw, headers=headers))
    with pytest.raises(HTTPError) as error:
        send(body, False)
    assert error.value.code == 401
    body["member"]["user"]["id"] = "attacker"
    with send(body) as response:
        assert "not authorized" in json.load(response)["data"]["content"]
    body["member"]["user"]["id"] = "123"
    with send(body) as response:
        assert json.load(response)["data"]["content"] == "ACKNOWLEDGED_NEEDS_MANUAL_DISPATCH"
    with send(body) as response:
        assert "already resolved" in json.load(response)["data"]["content"]
    assert service.payload()["exceptions"][0]["resolution"]["manager"] == "discord:123"


@pytest.mark.parametrize("reason", ["THIN_MARGIN", "OVER_HOURS_OPPORTUNITY"])
def test_exception_approves_only_chosen_legal_load_and_dependent_policy_waits(service, reason):
    # Pin a legal option plus an attractive illegal option; the callback cannot select the latter.
    chosen, later, illegal = [l["load_id"] for l in service.fleet["board"][:3]]
    result = {"trucks": [{"truck_id": "T-001", "decisions": [
        {"free_at": "12:00", "chosen": chosen, "action": "AUTO_BOOK", "exception_reason": reason},
        {"free_at": "15:00", "chosen": later, "action": "AUTO_BOOK"}]}],
        "exceptions": [{"exception_id": "case", "truck_id": "T-001", "free_at": "12:00", "chosen": chosen,
                        "reason": reason, "detail": f"Rejected illegal alternative {illegal}"}]}
    with service.connection() as db:
        db.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?)", (service.run_key, json.dumps(result)))
    assert service.commit()["events"] == []
    resolved = service.resolve("case", "APPROVE", "discord:123")
    assert resolved["booking"]["load_id"] == str(chosen)
    service.commit()
    booked = service.ledger.state()
    assert {r["load_id"] for r in booked.values()} == {str(chosen), str(later)}
    assert all(r["load_id"] != str(illegal) for r in booked.values())


def test_empty_one_response_is_not_reported_as_success(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    class Empty:
        def execute_one_action(self, payload): return {}
    result = publish_exception(dict(exception_id="x", truck_id="T", reason="TEST", detail="test"), publisher_factory=Empty)
    assert result["delivery"] == "unavailable" and not result["execute_one_action_succeeded"]
    assert len(result["attempts"]) == 2
