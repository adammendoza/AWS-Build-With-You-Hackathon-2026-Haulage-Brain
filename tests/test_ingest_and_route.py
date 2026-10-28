from pathlib import Path

import pytest

from load_quoting_swarm.config import load_fleet_config
from load_quoting_swarm.flow import ingest_and_route
from load_quoting_swarm.ingest import available_loads, load_freight_loads
from load_quoting_swarm.models import InputError
from load_quoting_swarm.models import FreightLoad


ROOT = Path(__file__).resolve().parents[1]


def test_ingests_available_loads_and_routes_first_three() -> None:
    result = ingest_and_route(ROOT / "data/loads.demo.json", limit=3)

    assert result["source_count"] == 4
    assert result["available_count"] == 3
    assert result["selected_count"] == 3
    assert set(result["routes"]) == {
        "luton_van:general_freight",
        "7.5t_rigid:premium_urgent",
        "artic:general_freight",
    }


def test_filters_non_available_statuses() -> None:
    loads = load_freight_loads(ROOT / "data/loads.demo.json")

    assert len(loads) == 4
    assert [load.load_id for load in available_loads(loads)] == [
        "UK-DEMO-001",
        "UK-DEMO-002",
        "UK-DEMO-003",
    ]


def test_ingests_updated_nested_uk_fixture() -> None:
    loads = load_freight_loads(ROOT / "data/loads_v2.json")
    selected = available_loads(loads)

    assert len(loads) == 89
    assert len(selected) == 41
    assert selected[0].origin_postcode == "PL6 2WS"
    assert selected[0].journey_minutes_est == 259
    assert selected[0].delivery_is_estimated is True


def test_fleet_example_refuses_placeholder_economics() -> None:
    with pytest.raises(InputError, match="placeholder_values"):
        load_fleet_config(ROOT / "config/fleet.example.json")


def test_demo_fleet_is_explicit_and_loadable() -> None:
    fleet = load_fleet_config(ROOT / "config/fleet.demo.json")

    assert fleet.fleet_name == "Synthetic Demo Fleet"
    assert set(fleet.vehicle_profiles) == {"luton van", "7.5t rigid", "artic"}
    assert len(fleet.vehicles) == 3


def test_normalizes_likely_camel_case_export_fields() -> None:
    load = FreightLoad.from_raw(
        {
            "id": "CAMEL-001",
            "status": "AVAILABLE",
            "origin": {"city": "London"},
            "destination": {"city": "Leeds"},
            "pickupWindow": {"start": "2026-10-29 09:00"},
            "deliveryWindow": {"start": "2026-10-29 17:00"},
            "vehicleRequested": "Luton Van",
            "loadCategory": "General",
            "distanceMiles": "200 miles",
            "weightKg": "900",
            "offeredRateGbp": "£450",
            "paymentTerms": "30 days",
        }
    )

    assert load.load_id == "CAMEL-001"
    assert load.is_available
    assert load.origin == "London"
    assert load.pickup_at.tzinfo is not None
    assert load.offered_rate_gbp == 450


def test_preserves_unsupplied_weight_for_compliance_review() -> None:
    load = FreightLoad.from_raw(
        {
            "id": "INCOMPLETE-001",
            "origin": "London",
            "destination": "Leeds",
            "pickupAt": "2026-10-29T09:00:00+00:00",
            "deliveryAt": "2026-10-29T17:00:00+00:00",
            "vehicleType": "Luton Van",
            "distanceMiles": 200,
            "offeredRateGbp": 450,
        }
    )

    assert load.weight_kg is None
