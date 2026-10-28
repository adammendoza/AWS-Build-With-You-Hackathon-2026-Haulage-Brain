import asyncio
from pathlib import Path

from load_quoting_swarm.config import load_fleet_config
from load_quoting_swarm.grounding import DemoGrounding
from load_quoting_swarm.ingest import available_loads, load_freight_loads
from load_quoting_swarm.inference import DemoInference
from load_quoting_swarm.memory import ScopedMemory
from load_quoting_swarm.pipeline import QuotePipeline
from load_quoting_swarm.specialists import check_compliance, price_load


ROOT = Path(__file__).resolve().parents[1]


def _fixtures():
    fleet = load_fleet_config(ROOT / "config/fleet.demo.json")
    loads = available_loads(load_freight_loads(ROOT / "data/loads.demo.json"))
    return fleet, loads


def test_live_diesel_price_changes_margin_and_quote() -> None:
    fleet, loads = _fixtures()
    load = loads[1]
    low = asyncio.run(DemoGrounding(diesel_price_ppl=100).market_inputs(load))
    high = asyncio.run(DemoGrounding(diesel_price_ppl=200).market_inputs(load))

    low_price = price_load(load, fleet, low)
    high_price = price_load(load, fleet, high)

    assert high_price.fuel_cost_gbp > low_price.fuel_cost_gbp
    assert high_price.target_quote_gbp > low_price.target_quote_gbp
    assert high_price.offered_margin_pct < low_price.offered_margin_pct


def test_ulez_charge_is_added_to_noncompliant_vehicle() -> None:
    fleet, loads = _fixtures()
    load = loads[0]
    market = asyncio.run(
        DemoGrounding(diesel_price_ppl=145, ulez_charge_gbp=12.5).market_inputs(load)
    )

    pricing = price_load(load, fleet, market)
    compliance = check_compliance(load, fleet, market)

    assert pricing.restriction_cost_gbp == 12.5
    assert "live_ulez_charge_added" in pricing.risk_flags
    assert compliance.ulez_charge_required is True


def test_pipeline_runs_three_loads_in_parallel() -> None:
    fleet, loads = _fixtures()

    class TrackingGrounding(DemoGrounding):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.max_active = 0

        async def market_inputs(self, load):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                await asyncio.sleep(0.01)
                return await super().market_inputs(load)
            finally:
                self.active -= 1

    grounding = TrackingGrounding()
    pipeline = QuotePipeline(
        fleet=fleet,
        grounding=grounding,
        inference=DemoInference(),
        memory=ScopedMemory(),
        max_parallel_loads=3,
    )

    result = asyncio.run(pipeline.quote_many(loads))

    assert result["fixture_count"] == 3
    assert grounding.max_active == 3
    assert len(result["decisions"]) == 3
    assert {item["load_id"] for item in result["decisions"]} == {
        "UK-DEMO-001",
        "UK-DEMO-002",
        "UK-DEMO-003",
    }
    assert all(item["approval_status"] == "PENDING" for item in result["decisions"])
