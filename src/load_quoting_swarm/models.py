from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


class InputError(ValueError):
    """Raised when fixture data cannot be normalized safely."""


def _first(raw: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        value = raw.get(name)
        if value is not None and value != "":
            return value
    return default


def _text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("label", "name", "city", "value"):
            if value.get(key):
                return str(value[key]).strip()
    return str(value or "").strip()


def _float(value: Any, *, field_name: str, required: bool = True) -> float | None:
    if value is None or value == "":
        if required:
            raise InputError(f"missing required numeric field: {field_name}")
        return None
    if isinstance(value, str):
        value = (
            value.replace("£", "")
            .replace("GBP", "")
            .replace(",", "")
            .replace(" miles", "")
            .replace(" mi", "")
            .strip()
        )
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"invalid numeric field {field_name}: {value!r}") from exc


def _datetime(value: Any, *, field_name: str) -> datetime:
    if not value:
        raise InputError(f"missing required datetime field: {field_name}")
    if isinstance(value, dict):
        value = _first(value, "start", "from", "earliest", "datetime", "value")
        if not value:
            raise InputError(f"{field_name} window has no start value")
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
        for date_format in (
            "%Y-%m-%d %H:%M",
            "%d %b %Y %H:%M",
            "%d/%m/%Y %H:%M",
        ):
            try:
                parsed = datetime.strptime(text, date_format)
                break
            except ValueError:
                continue
        if parsed is None:
            raise InputError(
                f"{field_name} must contain a parseable UK date and time: {value!r}"
            )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Europe/London"))
    return parsed


def _slug(value: str) -> str:
    return "_".join(value.lower().replace("/", " ").replace("-", " ").split())


@dataclass(frozen=True)
class FreightLoad:
    load_id: str
    status: str
    origin: str
    destination: str
    pickup_at: datetime
    delivery_at: datetime
    vehicle_type: str
    category: str
    distance_miles: float
    weight_kg: float
    offered_rate_gbp: float
    payment_terms: str = ""
    loading_minutes: int = 60
    expected_waiting_minutes: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def route_key(self) -> str:
        return f"{_slug(self.vehicle_type)}:{_slug(self.category)}"

    @property
    def is_available(self) -> bool:
        return self.status.casefold() == "available"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "FreightLoad":
        notes_value = _first(raw, "notes", "special_instructions", default=[])
        if isinstance(notes_value, str):
            notes = (notes_value.strip(),) if notes_value.strip() else ()
        elif isinstance(notes_value, list):
            notes = tuple(_text(item) for item in notes_value if _text(item))
        else:
            notes = (_text(notes_value),) if _text(notes_value) else ()

        load_id = _text(_first(raw, "load_id", "id", "reference"))
        if not load_id:
            raise InputError("load is missing load_id/id/reference")
        origin = _text(_first(raw, "origin", "pickup_location"))
        destination = _text(_first(raw, "destination", "delivery_location"))
        vehicle_type = _text(
            _first(
                raw,
                "vehicle_type",
                "vehicleType",
                "vehicle_requested",
                "vehicleRequested",
                "vehicle",
            )
        )
        for field_name, value in (
            ("origin", origin),
            ("destination", destination),
            ("vehicle_type", vehicle_type),
        ):
            if not value:
                raise InputError(f"load {load_id} is missing {field_name}")

        return cls(
            load_id=load_id,
            status=_text(_first(raw, "status", default="Available")),
            origin=origin,
            destination=destination,
            pickup_at=_datetime(
                _first(
                    raw,
                    "pickup_at",
                    "pickupAt",
                    "pickup_window",
                    "pickupWindow",
                    "pickup_datetime",
                    "pickupDateTime",
                    "pickupDate",
                    "pickup",
                ),
                field_name="pickup_at",
            ),
            delivery_at=_datetime(
                _first(
                    raw,
                    "delivery_at",
                    "deliveryAt",
                    "delivery_window",
                    "deliveryWindow",
                    "delivery_datetime",
                    "deliveryDateTime",
                    "deliveryDate",
                    "delivery",
                ),
                field_name="delivery_at",
            ),
            vehicle_type=vehicle_type,
            category=_text(
                _first(raw, "category", "load_category", "loadCategory", default="general")
            ),
            distance_miles=float(
                _float(
                    _first(raw, "distance_miles", "distanceMiles", "distance", "miles"),
                    field_name="distance_miles",
                )
            ),
            weight_kg=float(
                _float(
                    _first(raw, "weight_kg", "weightKg", "weight"),
                    field_name="weight_kg",
                )
            ),
            offered_rate_gbp=float(
                _float(
                    _first(
                        raw,
                        "offered_rate_gbp",
                        "offeredRateGbp",
                        "offeredRate",
                        "rate_gbp",
                        "rateGbp",
                        "rate",
                        "price",
                    ),
                    field_name="offered_rate_gbp",
                )
            ),
            payment_terms=_text(
                _first(raw, "payment_terms", "paymentTerms", default="")
            ),
            loading_minutes=int(
                _float(
                    _first(raw, "loading_minutes", "loadingMinutes", default=60),
                    field_name="loading_minutes",
                )
            ),
            expected_waiting_minutes=int(
                _float(
                    _first(
                        raw,
                        "expected_waiting_minutes",
                        "expectedWaitingMinutes",
                        "waiting_minutes",
                        "waitingMinutes",
                        default=0,
                    ),
                    field_name="expected_waiting_minutes",
                )
            ),
            notes=notes,
            raw=dict(raw),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["pickup_at"] = self.pickup_at.isoformat()
        result["delivery_at"] = self.delivery_at.isoformat()
        result["notes"] = list(self.notes)
        result.pop("raw", None)
        result["route_key"] = self.route_key
        return result


@dataclass(frozen=True)
class VehicleProfile:
    vehicle_type: str
    mpg: float
    fixed_cost_per_mile_gbp: float
    max_payload_kg: float
    typical_speed_mph: float
    ulez_compliant: bool


@dataclass(frozen=True)
class FleetVehicle:
    vehicle_id: str
    vehicle_type: str
    available_from: datetime
    available_until: datetime
    location: str


@dataclass(frozen=True)
class FleetConfig:
    fleet_name: str
    target_margin_pct: float
    minimum_margin_pct: float
    driver_cost_per_hour_gbp: float
    vehicle_profiles: dict[str, VehicleProfile]
    vehicles: tuple[FleetVehicle, ...]


@dataclass(frozen=True)
class RoutedLoad:
    load: FreightLoad
    route_key: str


@dataclass(frozen=True)
class Citation:
    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True)
class MarketInputs:
    diesel_price_ppl: float
    restriction_summary: str
    ulez_charge_gbp: float
    retrieved_at: datetime
    citations: tuple[Citation, ...]
    source: str = "you.com"

    def to_dict(self) -> dict[str, Any]:
        return {
            "diesel_price_ppl": self.diesel_price_ppl,
            "restriction_summary": self.restriction_summary,
            "ulez_charge_gbp": self.ulez_charge_gbp,
            "retrieved_at": self.retrieved_at.isoformat(),
            "citations": [asdict(item) for item in self.citations],
            "source": self.source,
        }


@dataclass(frozen=True)
class PricingAssessment:
    fuel_litres: float
    fuel_cost_gbp: float
    fixed_vehicle_cost_gbp: float
    driver_hours: float
    driver_cost_gbp: float
    restriction_cost_gbp: float
    estimated_total_cost_gbp: float
    offered_rate_gbp: float
    offered_profit_gbp: float
    offered_margin_pct: float
    break_even_rate_gbp: float
    target_quote_gbp: float
    minimum_viable_rate_gbp: float
    summary: str = ""
    risk_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["risk_flags"] = list(self.risk_flags)
        return result


@dataclass(frozen=True)
class ComplianceAssessment:
    feasible: bool
    payload_ok: bool
    schedule_ok: bool
    ulez_applies: bool
    ulez_charge_required: bool
    service_hours: float
    minimum_trip_hours: float
    flags: tuple[str, ...]
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["flags"] = list(self.flags)
        return result


@dataclass(frozen=True)
class FleetFitAssessment:
    feasible: bool
    selected_vehicle_id: str | None
    matching_vehicle_ids: tuple[str, ...]
    flags: tuple[str, ...]
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["matching_vehicle_ids"] = list(self.matching_vehicle_ids)
        result["flags"] = list(self.flags)
        return result


@dataclass(frozen=True)
class QuoteDecision:
    quote_id: str
    load_id: str
    recommendation: str
    proposed_quote_gbp: float
    confidence: float
    rationale: str
    pricing: PricingAssessment
    compliance: ComplianceAssessment
    fleet_fit: FleetFitAssessment
    market_inputs: MarketInputs
    specialist_notes: dict[str, dict[str, Any]]
    approval_status: str = "PENDING"

    def to_dict(self) -> dict[str, Any]:
        return {
            "quote_id": self.quote_id,
            "load_id": self.load_id,
            "recommendation": self.recommendation,
            "proposed_quote_gbp": self.proposed_quote_gbp,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "pricing": self.pricing.to_dict(),
            "compliance": self.compliance.to_dict(),
            "fleet_fit": self.fleet_fit.to_dict(),
            "market_inputs": self.market_inputs.to_dict(),
            "specialist_notes": self.specialist_notes,
            "approval_status": self.approval_status,
        }
