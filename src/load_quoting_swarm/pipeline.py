from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Any, Callable

from .grounding import GroundingClient
from .inference import InferenceClient
from .memory import ScopedMemory
from .models import FleetConfig, FreightLoad, QuoteDecision
from .specialists import check_compliance, check_fleet_fit, price_load


class QuotePipeline:
    def __init__(
        self,
        *,
        fleet: FleetConfig,
        grounding: GroundingClient,
        inference: InferenceClient,
        memory: ScopedMemory,
        max_parallel_loads: int = 8,
        event_sink: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self.fleet = fleet
        self.grounding = grounding
        self.inference = inference
        self.memory = memory
        self._semaphore = asyncio.Semaphore(max(1, max_parallel_loads))
        self.event_sink = event_sink
        self.last_decisions: list[QuoteDecision] = []
        self._seed_specialist_memory()

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self.event_sink:
            self.event_sink(event_type, data)

    def _seed_specialist_memory(self) -> None:
        for profile in self.fleet.vehicle_profiles.values():
            metadata = {"vehicle_type": profile.vehicle_type, "kind": "fleet_profile"}
            self.memory.remember(
                (
                    f"{profile.vehicle_type}: {profile.mpg} MPG, fixed vehicle cost "
                    f"£{profile.fixed_cost_per_mile_gbp}/mile."
                ),
                scope="/pricing",
                metadata=metadata,
            )
            self.memory.remember(
                (
                    f"{profile.vehicle_type}: max payload {profile.max_payload_kg}kg, "
                    f"ULEZ compliant={profile.ulez_compliant}."
                ),
                scope="/compliance",
                metadata=metadata,
            )
        for vehicle in self.fleet.vehicles:
            self.memory.remember(
                (
                    f"{vehicle.vehicle_id}: available {vehicle.available_from.isoformat()} "
                    f"to {vehicle.available_until.isoformat()} from {vehicle.location}."
                ),
                scope="/fleet-fit",
                metadata={
                    "vehicle_type": vehicle.vehicle_type,
                    "vehicle_id": vehicle.vehicle_id,
                    "kind": "vehicle_availability",
                },
            )

    async def quote(self, load: FreightLoad) -> QuoteDecision:
        async with self._semaphore:
            market_task = asyncio.create_task(self.grounding.market_inputs(load))
            fleet_fit = check_fleet_fit(load, self.fleet)
            market = await market_task
            pricing = price_load(load, self.fleet, market)
            compliance = check_compliance(load, self.fleet, market)
            baseline_market = replace(
                market,
                diesel_price_ppl=145.0,
                ulez_charge_gbp=12.5 if load.ulez_flagged else 0.0,
                source="synthetic-baseline",
            )
            baseline_pricing = price_load(load, self.fleet, baseline_market)
            self._emit(
                "tools.assessment.completed",
                {
                    "load_id": load.load_id,
                    "diesel_price_ppl": market.diesel_price_ppl,
                    "fuel_cost_gbp": pricing.fuel_cost_gbp,
                    "estimated_total_cost_gbp": pricing.estimated_total_cost_gbp,
                    "target_quote_gbp": pricing.target_quote_gbp,
                    "offered_rate_gbp": pricing.offered_rate_gbp,
                    "offered_margin_pct": pricing.offered_margin_pct,
                    "baseline_diesel_price_ppl": 145.0,
                    "baseline_target_quote_gbp": baseline_pricing.target_quote_gbp,
                    "live_quote_delta_gbp": round(
                        pricing.target_quote_gbp - baseline_pricing.target_quote_gbp, 2
                    ),
                    "compliance_flags": list(compliance.flags),
                    "fleet_fit": fleet_fit.to_dict(),
                },
            )

            base_context = {
                "load": load.to_dict(),
                "market_inputs": market.to_dict(),
            }
            specialist_memory = {
                role: [
                    item.value
                    for item in self.memory.recall(
                        scope=scope,
                        metadata_key="vehicle_type",
                        metadata_value=load.vehicle_type,
                    )
                ]
                for role, scope in (
                    ("pricing", "/pricing"),
                    ("compliance", "/compliance"),
                    ("fleet_fit", "/fleet-fit"),
                )
            }
            notes = await asyncio.gather(
                self.inference.specialist(
                    "pricing",
                    {
                        **base_context,
                        "assessment": pricing.to_dict(),
                        "scoped_memory": specialist_memory["pricing"],
                    },
                ),
                self.inference.specialist(
                    "compliance",
                    {
                        **base_context,
                        "assessment": compliance.to_dict(),
                        "scoped_memory": specialist_memory["compliance"],
                    },
                ),
                self.inference.specialist(
                    "fleet-fit",
                    {
                        **base_context,
                        "assessment": fleet_fit.to_dict(),
                        "scoped_memory": specialist_memory["fleet_fit"],
                    },
                ),
            )
            specialist_notes = dict(zip(("pricing", "compliance", "fleet_fit"), notes))
            for scope, note in (
                ("/pricing", specialist_notes["pricing"]),
                ("/compliance", specialist_notes["compliance"]),
                ("/fleet-fit", specialist_notes["fleet_fit"]),
            ):
                self.memory.remember(
                    str(note.get("summary", "")),
                    scope=scope,
                    metadata={"load_id": load.load_id, "route_key": load.route_key},
                )

            pricing = replace(pricing, summary=str(notes[0].get("summary", "")))
            compliance = replace(
                compliance, summary=str(notes[1].get("summary", ""))
            )
            fleet_fit = replace(
                fleet_fit, summary=str(notes[2].get("summary", ""))
            )
            deterministic_eligible = (
                pricing.offered_margin_pct >= self.fleet.minimum_margin_pct
                and compliance.feasible
                and fleet_fit.feasible
            )
            supervisor = await self.inference.supervise(
                {
                    "load_id": load.load_id,
                    "deterministic_eligible": deterministic_eligible,
                    "pricing": pricing.to_dict(),
                    "compliance": compliance.to_dict(),
                    "fleet_fit": fleet_fit.to_dict(),
                    "specialists": specialist_notes,
                }
            )
            requested = str(supervisor.get("recommendation", "REVIEW")).upper()
            if requested not in {"APPROVE", "PASS", "REVIEW"}:
                requested = "REVIEW"
            # Models can downgrade a safe load but cannot override deterministic gates.
            recommendation = requested if deterministic_eligible else "PASS"
            rationale = str(supervisor.get("rationale", "")).strip()
            confidence = max(0.0, min(1.0, float(supervisor.get("confidence", 0))))
            self.memory.remember(
                rationale,
                scope="/supervisor",
                metadata={"load_id": load.load_id, "recommendation": recommendation},
            )
            self._emit(
                "safety.gate.completed",
                {
                    "load_id": load.load_id,
                    "model_recommendation": requested,
                    "deterministic_eligible": deterministic_eligible,
                    "final_recommendation": recommendation,
                    "confidence": confidence,
                    "rationale": rationale,
                },
            )
            return QuoteDecision(
                quote_id=f"Q-{load.load_id}",
                load_id=load.load_id,
                recommendation=recommendation,
                proposed_quote_gbp=max(
                    pricing.offered_rate_gbp, pricing.target_quote_gbp
                ),
                confidence=confidence,
                rationale=rationale,
                pricing=pricing,
                compliance=compliance,
                fleet_fit=fleet_fit,
                market_inputs=market,
                specialist_notes=specialist_notes,
            )

    async def quote_many(self, loads: list[FreightLoad]) -> dict[str, Any]:
        started = time.perf_counter()
        decisions = await asyncio.gather(*(self.quote(load) for load in loads))
        self.last_decisions = list(decisions)
        elapsed = time.perf_counter() - started
        throughput = len(decisions) / elapsed * 60 if elapsed else 0
        return {
            "fixture_count": len(decisions),
            "elapsed_seconds": round(elapsed, 3),
            "loads_per_minute": round(throughput, 2),
            "projected_minutes_per_1000": round(1000 / throughput, 2)
            if throughput
            else None,
            "inference_usage": self.inference.usage(),
            "decisions": [decision.to_dict() for decision in decisions],
        }
