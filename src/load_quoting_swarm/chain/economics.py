"""FleetConfig-backed economics. Offline fixtures are explicit; live callers supply diesel."""
import json
import math
import os
from pathlib import Path

from ..config import load_fleet_config
from ..specialists import IMPERIAL_GALLON_LITRES

ROOT = Path(os.getenv("HB_CHAIN_ROOT", str(Path(__file__).resolve().parents[3])))
DEFAULT_CONFIG = ROOT / "config/fleet.chain.demo.json"


def fleet_economics(base, vehicle, path=DEFAULT_CONFIG, diesel_ppl=None):
    raw = json.loads(Path(path).read_text())
    fleet = load_fleet_config(path)
    profile = fleet.vehicle_profiles[raw["board_vehicle_map"][vehicle].casefold()]
    diesel = float(raw["diesel_price_ppl_demo"] if diesel_ppl is None else diesel_ppl)
    if not math.isfinite(diesel) or not 50 <= diesel <= 300:
        raise ValueError("diesel price must be a finite pence-per-litre input")
    cfg = dict(base)
    cfg.update(cost_per_mile_gbp=IMPERIAL_GALLON_LITRES / profile.mpg * diesel / 100
               + profile.fixed_cost_per_mile_gbp,
               driver_cost_per_hour_gbp=fleet.driver_cost_per_hour_gbp,
               hgv_speed_mph=profile.typical_speed_mph,
               min_margin=fleet.minimum_margin_pct / 100,
               max_payload_kg=profile.max_payload_kg, diesel_price_ppl=diesel)
    if not 0 < cfg["max_daily_driving_h"] <= 9 or not 0 < cfg["break_after_h"] <= 4.5 or cfg["break_minutes"] < 45:
        raise ValueError("policy cannot relax the 9h cap or 4.5h/45-minute break rule")
    return cfg


def validate_fleet(fleet):
    if not fleet["trucks"]:
        raise ValueError("fleet must contain trucks")
    trucks = [t["truck_id"] for t in fleet["trucks"]]
    loads = [t["first_job"]["load_id"] for t in fleet["trucks"]] + [l["load_id"] for l in fleet["board"]]
    if len(trucks) != len(set(trucks)) or len(loads) != len(set(loads)):
        raise ValueError("duplicate truck or load IDs")
