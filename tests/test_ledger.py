import asyncio
from pathlib import Path

import pytest

from load_quoting_swarm.config import load_fleet_config
from load_quoting_swarm.grounding import DemoGrounding
from load_quoting_swarm.ingest import available_loads, load_freight_loads
from load_quoting_swarm.inference import DemoInference
from load_quoting_swarm.ledger import BookingLedger, LedgerError
from load_quoting_swarm.memory import ScopedMemory
from load_quoting_swarm.pipeline import QuotePipeline


ROOT = Path(__file__).resolve().parents[1]


def _decision():
    fleet = load_fleet_config(ROOT / "config/fleet.demo.json")
    load = available_loads(load_freight_loads(ROOT / "data/loads.demo.json"))[1]
    pipeline = QuotePipeline(
        fleet=fleet,
        grounding=DemoGrounding(),
        inference=DemoInference(),
        memory=ScopedMemory(),
    )
    return asyncio.run(pipeline.quote(load))


def test_approval_is_required_before_booking(tmp_path: Path) -> None:
    ledger = BookingLedger(tmp_path / "ledger.jsonl")
    decision = _decision()
    ledger.record_quote(decision)

    assert ledger.state()[decision.quote_id]["status"] == "PENDING"

    event = ledger.decide(
        decision.quote_id, decision="APPROVE", manager="fleet-manager@example.test"
    )

    assert event["status"] == "BOOKED"
    assert ledger.state()[decision.quote_id]["status"] == "BOOKED"


def test_quote_cannot_be_decided_twice(tmp_path: Path) -> None:
    ledger = BookingLedger(tmp_path / "ledger.jsonl")
    decision = _decision()
    ledger.record_quote(decision)
    ledger.decide(decision.quote_id, decision="PASS", manager="manager")

    with pytest.raises(LedgerError, match="already decided"):
        ledger.decide(decision.quote_id, decision="APPROVE", manager="manager")
