from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import FleetConfig, FleetVehicle, InputError, VehicleProfile, _datetime


def _positive(raw: dict[str, Any], name: str, *, allow_zero: bool = False) -> float:
    if name not in raw:
        raise InputError(f"fleet config is missing {name}")
    try:
        value = float(raw[name])
    except (TypeError, ValueError) as exc:
        raise InputError(f"fleet config field {name} must be numeric") from exc
    if value < 0 or (value == 0 and not allow_zero):
        raise InputError(f"fleet config field {name} must be positive")
    return value


def load_fleet_config(path: str | Path) -> FleetConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise InputError(
            f"fleet config not found: {config_path}. Copy config/fleet.example.json "
            "to config/fleet.local.json and enter real fleet economics."
        )
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if raw.get("placeholder_values") is True:
        raise InputError(
            "fleet config still contains placeholder_values=true; refusing to invent margin"
        )

    profiles: dict[str, VehicleProfile] = {}
    for item in raw.get("vehicle_profiles", []):
        vehicle_type = str(item.get("vehicle_type", "")).strip()
        if not vehicle_type:
            raise InputError("vehicle profile is missing vehicle_type")
        profiles[vehicle_type.casefold()] = VehicleProfile(
            vehicle_type=vehicle_type,
            mpg=_positive(item, "mpg"),
            fixed_cost_per_mile_gbp=_positive(item, "fixed_cost_per_mile_gbp"),
            max_payload_kg=_positive(item, "max_payload_kg"),
            typical_speed_mph=_positive(item, "typical_speed_mph"),
            ulez_compliant=bool(item.get("ulez_compliant", False)),
        )
    if not profiles:
        raise InputError("fleet config requires at least one vehicle profile")

    vehicles: list[FleetVehicle] = []
    for item in raw.get("vehicles", []):
        vehicle_type = str(item.get("vehicle_type", "")).strip()
        if vehicle_type.casefold() not in profiles:
            raise InputError(f"vehicle references unknown profile: {vehicle_type}")
        vehicles.append(
            FleetVehicle(
                vehicle_id=str(item.get("vehicle_id", "")).strip(),
                vehicle_type=vehicle_type,
                available_from=_datetime(
                    item.get("available_from"), field_name="available_from"
                ),
                available_until=_datetime(
                    item.get("available_until"), field_name="available_until"
                ),
                location=str(item.get("location", "")).strip(),
            )
        )
    if not vehicles:
        raise InputError("fleet config requires at least one vehicle")

    return FleetConfig(
        fleet_name=str(raw.get("fleet_name", "")).strip(),
        target_margin_pct=_positive(raw, "target_margin_pct"),
        minimum_margin_pct=_positive(raw, "minimum_margin_pct", allow_zero=True),
        driver_cost_per_hour_gbp=_positive(raw, "driver_cost_per_hour_gbp"),
        vehicle_profiles=profiles,
        vehicles=tuple(vehicles),
    )
