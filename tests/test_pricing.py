from datetime import datetime

from load_quoting_swarm.pricing import DEFAULT_CONFIG, quote


def test_prd_worked_example() -> None:
    result = quote(
        124,
        151,
        "BD8 1AA",
        "CV21 1AA",
        datetime(2026, 10, 29, 9, 0),
    )

    assert result["billed_minutes"] == 180
    assert result["total"] == 170


def test_london_to_london_peak_surcharges() -> None:
    result = quote(
        20,
        45,
        "SW1X 7XL",
        "EC1A 1BB",
        datetime(2026, 10, 29, 9, 0),
    )

    assert result["city"] == (
        DEFAULT_CONFIG["london_operational"]
        + DEFAULT_CONFIG["london_peak_congestion"]
    )


def test_over_450_miles_requires_human_fuel_price() -> None:
    result = quote(
        451,
        600,
        "BD8 1AA",
        "CV21 1AA",
        datetime(2026, 10, 29, 9, 0),
    )

    assert result["status"].startswith("needs_human")
