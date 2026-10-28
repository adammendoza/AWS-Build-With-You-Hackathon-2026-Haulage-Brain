from __future__ import annotations

from dataclasses import replace

from .models import (
    ComplianceAssessment,
    FleetConfig,
    FleetFitAssessment,
    FreightLoad,
    MarketInputs,
    PricingAssessment,
)


IMPERIAL_GALLON_LITRES = 4.54609


def _profile(load: FreightLoad, fleet: FleetConfig):
    profile = fleet.vehicle_profiles.get(load.vehicle_type.casefold())
    if profile is None:
        raise ValueError(f"fleet has no cost profile for {load.vehicle_type}")
    return profile


def price_load(
    load: FreightLoad, fleet: FleetConfig, market: MarketInputs
) -> PricingAssessment:
    profile = _profile(load, fleet)
    fuel_litres = load.distance_miles / profile.mpg * IMPERIAL_GALLON_LITRES
    fuel_cost = fuel_litres * market.diesel_price_ppl / 100
    fixed_cost = load.distance_miles * profile.fixed_cost_per_mile_gbp
    driver_hours = (
        load.distance_miles / profile.typical_speed_mph
        + (load.loading_minutes + load.expected_waiting_minutes) / 60
    )
    driver_cost = driver_hours * fleet.driver_cost_per_hour_gbp
    ulez_applies = "ulez" in " ".join(load.notes).casefold()
    restriction_cost = (
        market.ulez_charge_gbp if ulez_applies and not profile.ulez_compliant else 0.0
    )
    total = fuel_cost + fixed_cost + driver_cost + restriction_cost
    offered_profit = load.offered_rate_gbp - total
    offered_margin = offered_profit / load.offered_rate_gbp * 100
    target_quote = total / (1 - fleet.target_margin_pct / 100)
    minimum_viable = total / (1 - fleet.minimum_margin_pct / 100)
    flags: list[str] = []
    if offered_margin < fleet.minimum_margin_pct:
        flags.append("offered_rate_below_fleet_minimum_margin")
    if restriction_cost:
        flags.append("live_ulez_charge_added")
    return PricingAssessment(
        fuel_litres=round(fuel_litres, 2),
        fuel_cost_gbp=round(fuel_cost, 2),
        fixed_vehicle_cost_gbp=round(fixed_cost, 2),
        driver_hours=round(driver_hours, 2),
        driver_cost_gbp=round(driver_cost, 2),
        restriction_cost_gbp=round(restriction_cost, 2),
        estimated_total_cost_gbp=round(total, 2),
        offered_rate_gbp=round(load.offered_rate_gbp, 2),
        offered_profit_gbp=round(offered_profit, 2),
        offered_margin_pct=round(offered_margin, 2),
        break_even_rate_gbp=round(total, 2),
        target_quote_gbp=round(target_quote, 2),
        minimum_viable_rate_gbp=round(minimum_viable, 2),
        risk_flags=tuple(flags),
    )


def check_compliance(
    load: FreightLoad, fleet: FleetConfig, market: MarketInputs
) -> ComplianceAssessment:
    profile = _profile(load, fleet)
    flags: list[str] = []
    payload_ok = load.weight_kg <= profile.max_payload_kg
    if not payload_ok:
        flags.append("payload_exceeds_vehicle_profile")

    service_hours = (load.delivery_at - load.pickup_at).total_seconds() / 3600
    minimum_trip_hours = (
        load.distance_miles / profile.typical_speed_mph
        + (load.loading_minutes + load.expected_waiting_minutes) / 60
    )
    schedule_ok = service_hours >= minimum_trip_hours
    if not schedule_ok:
        flags.append("delivery_window_shorter_than_minimum_trip_time")
    if load.expected_waiting_minutes >= 60:
        flags.append("material_waiting_time")

    ulez_applies = "ulez" in " ".join(load.notes).casefold()
    ulez_charge_required = ulez_applies and not profile.ulez_compliant
    if ulez_charge_required:
        if market.ulez_charge_gbp <= 0:
            flags.append("ulez_charge_missing")
        else:
            flags.append("ulez_charge_required")

    return ComplianceAssessment(
        feasible=payload_ok and schedule_ok and "ulez_charge_missing" not in flags,
        payload_ok=payload_ok,
        schedule_ok=schedule_ok,
        ulez_applies=ulez_applies,
        ulez_charge_required=ulez_charge_required,
        service_hours=round(service_hours, 2),
        minimum_trip_hours=round(minimum_trip_hours, 2),
        flags=tuple(flags),
    )


def check_fleet_fit(load: FreightLoad, fleet: FleetConfig) -> FleetFitAssessment:
    matching = [
        vehicle
        for vehicle in fleet.vehicles
        if vehicle.vehicle_type.casefold() == load.vehicle_type.casefold()
        and vehicle.available_from <= load.pickup_at
        and vehicle.available_until >= load.delivery_at
    ]
    flags: list[str] = []
    if not matching:
        flags.append("no_matching_vehicle_for_pickup_window")
    else:
        origin_city = load.origin.split(",", 1)[0].strip().casefold()
        if origin_city and origin_city not in matching[0].location.casefold():
            flags.append("deadhead_distance_requires_review")
    return FleetFitAssessment(
        feasible=bool(matching),
        selected_vehicle_id=matching[0].vehicle_id if matching else None,
        matching_vehicle_ids=tuple(vehicle.vehicle_id for vehicle in matching),
        flags=tuple(flags),
    )


def with_specialist_summary(assessment, note: dict):
    summary = str(note.get("summary", "")).strip()
    return replace(assessment, summary=summary)
