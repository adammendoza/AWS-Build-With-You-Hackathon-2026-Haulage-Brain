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
    assert payload["summary"]["available"] == 41
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


def test_ui_rejects_decision_for_delivered_load(tmp_path: Path) -> None:
    state = LoadboardState(
        ROOT / "data/loads_v2.json", tmp_path / "booking-ledger.jsonl"
    )
    delivered = next(
        item for item in state.raw_loads() if item["status"] == "Delivered"
    )

    with pytest.raises(LedgerError, match="only Available"):
        state.decide(
            {"load_id": delivered["load_id"], "decision": "APPROVE", "manager": "Adam"}
        )
