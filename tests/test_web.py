import json
from pathlib import Path

import pytest

from load_quoting_swarm.ledger import LedgerError
from load_quoting_swarm.web import LoadboardState


ROOT = Path(__file__).resolve().parents[1]


def test_updated_fixture_and_summary(tmp_path: Path) -> None:
    state = LoadboardState(
        ROOT / "data/loads_v2.json", tmp_path / "booking-ledger.jsonl"
    )

    payload = state.payload()

    assert payload["summary"]["loads"] == 89
    assert payload["summary"]["available"] == 89
    assert len(payload["loads"]) == 89
    assert all("quote_analysis" in item for item in payload["loads"])


def test_ui_approval_writes_booking_ledger(tmp_path: Path) -> None:
    state = LoadboardState(
        ROOT / "data/loads_v2.json", tmp_path / "booking-ledger.jsonl"
    )
    available = next(
        item for item in state.raw_loads() if item["status"] == "Available"
    )

    event = state.decide(
        {"load_id": available["load_id"], "decision": "APPROVE", "manager": "Adam"}
    )

    assert event["status"] == "BOOKED"
    assert event["manager"] == "Adam"


def test_ui_rejects_decision_for_non_available_load(tmp_path: Path) -> None:
    source = LoadboardState(
        ROOT / "data/loads_v2.json", tmp_path / "booking-ledger.jsonl"
    )
    loads = source.raw_loads()
    loads[0]["status"] = "Delivered"
    fixture = tmp_path / "loads.json"
    fixture.write_text(json.dumps(loads), encoding="utf-8")
    state = LoadboardState(fixture, tmp_path / "booking-ledger.jsonl")

    with pytest.raises(LedgerError, match="only Available"):
        state.decide(
            {"load_id": loads[0]["load_id"], "decision": "APPROVE", "manager": "Adam"}
        )
