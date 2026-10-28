"""Deterministic DispatchIQ PRD v2.0 quote formula.

Agents call this module as a tool. The model never performs the arithmetic.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "hourly_rate": 40.0,
    "minimum_charge": 65.0,
    "rounding_minutes": 30,
    "fuel_tiers": [(100, 30), (160, 50), (230, 70), (330, 100), (450, 150)],
    "london_areas": ["EC", "WC", "E", "N", "NW", "SE", "SW", "W"],
    "london_peak_congestion": 18.0,
    "london_operational": 30.0,
    # PRD 3.1 and its worked example compare the total with the minimum.
    "min_charge_applies_to": "total",
}


def postcode_area(postcode: str) -> str:
    match = re.match(r"^([A-Z]{1,2})\d", postcode.strip().upper())
    return match.group(1) if match else ""


def is_london(postcode: str, config: dict[str, Any]) -> bool:
    return postcode_area(postcode) in config["london_areas"]


def is_london_peak(value: datetime) -> bool:
    """Peak is Mon-Fri 07:00-18:00 and Saturday 12:00-18:00."""

    weekday = value.weekday()
    hour = value.hour + value.minute / 60
    return (weekday <= 4 and 7 <= hour < 18) or (
        weekday == 5 and 12 <= hour < 18
    )


def quote(
    distance_miles: float,
    journey_minutes: int,
    pickup_postcode: str,
    delivery_postcode: str,
    pickup_at: datetime,
    config: dict[str, Any] = DEFAULT_CONFIG,
) -> dict[str, Any]:
    rounding_minutes = int(config["rounding_minutes"])
    billed_minutes = math.ceil(journey_minutes / rounding_minutes) * rounding_minutes
    base = billed_minutes / 60 * float(config["hourly_rate"])

    fuel: float | None = None
    status = "ok"
    for maximum_miles, surcharge in config["fuel_tiers"]:
        if distance_miles <= maximum_miles:
            fuel = float(surcharge)
            break
    if fuel is None:
        fuel = 0.0
        status = "needs_human: 450+ miles fuel tier not configured (TBC in PRD)"

    city = 0.0
    if is_london(pickup_postcode, config) and is_london(
        delivery_postcode, config
    ):
        city = float(config["london_operational"])
        if is_london_peak(pickup_at):
            city += float(config["london_peak_congestion"])

    total = base + fuel + city
    minimum_applied = False
    if config["min_charge_applies_to"] == "total":
        if total < float(config["minimum_charge"]):
            total = float(config["minimum_charge"])
            minimum_applied = True
    elif journey_minutes <= 60 and base < float(config["minimum_charge"]):
        total = float(config["minimum_charge"]) + fuel + city
        minimum_applied = True

    return {
        "billed_minutes": billed_minutes,
        "base": round(base, 2),
        "fuel": round(fuel, 2),
        "city": round(city, 2),
        "total": round(total, 2),
        "minimum_applied": minimum_applied,
        "status": status,
    }
