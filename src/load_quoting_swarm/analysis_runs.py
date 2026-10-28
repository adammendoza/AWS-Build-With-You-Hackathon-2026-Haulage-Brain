from __future__ import annotations

import asyncio
import copy
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .config import load_fleet_config
from .flow import run_quote_flow
from .grounding import YouSearchGrounding
from .inference import ParasailInference
from .ingest import available_loads, load_freight_loads
from .memory import ScopedMemory
from .pipeline import QuotePipeline


EventSink = Callable[[str, dict[str, Any]], None]


class TracedGrounding:
    def __init__(self, inner: YouSearchGrounding, emit: EventSink):
        self.inner = inner
        self.emit = emit

    async def market_inputs(self, load):
        started = time.perf_counter()
        self.emit(
            "you.grounding.started",
            {
                "load_id": load.load_id,
                "research": [
                    "latest UK diesel price",
                    "route restrictions and ULEZ charges",
                ],
            },
        )
        market = await self.inner.market_inputs(load)
        self.emit(
            "you.grounding.completed",
            {
                **market.to_dict(),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            },
        )
        return market


class TracedInference:
    def __init__(self, inner: ParasailInference, emit: EventSink):
        self.inner = inner
        self.emit = emit
        self.model = inner.model

    async def specialist(self, role: str, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        self.emit(
            "parasail.specialist.started",
            {"role": role, "model": self.model},
        )
        result = await self.inner.specialist(role, payload)
        self.emit(
            "parasail.specialist.completed",
            {
                "role": role,
                "model": self.model,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "summary": str(result.get("summary", "")),
                "risk_flags": list(result.get("risk_flags", [])),
                "confidence": result.get("confidence"),
            },
        )
        return result

    async def supervise(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        self.emit(
            "parasail.supervisor.started",
            {"model": self.model},
        )
        result = await self.inner.supervise(payload)
        self.emit(
            "parasail.supervisor.completed",
            {
                "model": self.model,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "recommendation": result.get("recommendation"),
                "rationale": str(result.get("rationale", "")),
                "confidence": result.get("confidence"),
            },
        )
        return result

    def usage(self) -> dict[str, Any]:
        return self.inner.usage()


class AnalysisRun:
    def __init__(self, load_id: str):
        self.run_id = uuid4().hex
        self.load_id = load_id
        self.status = "RUNNING"
        self.error: str | None = None
        self.result: dict[str, Any] | None = None
        self.started_at = datetime.now(timezone.utc)
        self._started_clock = time.perf_counter()
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(
                {
                    "sequence": len(self._events) + 1,
                    "type": event_type,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "elapsed_ms": round(
                        (time.perf_counter() - self._started_clock) * 1000
                    ),
                    "data": data,
                }
            )

    def complete(self, result: dict[str, Any]) -> None:
        with self._lock:
            self.result = result
            self.status = "COMPLETED"

    def fail(self, exc: Exception) -> None:
        message = str(exc) or exc.__class__.__name__
        self.emit("run.failed", {"error": message})
        with self._lock:
            self.error = message
            self.status = "FAILED"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(
                {
                    "run_id": self.run_id,
                    "load_id": self.load_id,
                    "mode": "live",
                    "status": self.status,
                    "started_at": self.started_at.isoformat(),
                    "events": self._events,
                    "result": self.result,
                    "error": self.error,
                }
            )


class AnalysisRunManager:
    def __init__(
        self,
        loads_path: str | Path,
        fleet_path: str | Path,
        *,
        max_active_runs: int = 2,
    ):
        self.loads_path = Path(loads_path)
        self.fleet_path = Path(fleet_path)
        self._runs: dict[str, AnalysisRun] = {}
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max(1, max_active_runs))

    def start(self, load_id: str) -> dict[str, Any]:
        available = available_loads(load_freight_loads(self.loads_path), limit=None)
        load = next((item for item in available if item.load_id == load_id), None)
        if load is None:
            raise ValueError(f"unknown Available load: {load_id}")
        if not self._slots.acquire(blocking=False):
            raise RuntimeError("two live analyses are already running; try again shortly")

        run = AnalysisRun(load_id)
        with self._lock:
            self._runs[run.run_id] = run
            if len(self._runs) > 30:
                completed = [
                    key
                    for key, value in self._runs.items()
                    if value.status != "RUNNING" and key != run.run_id
                ]
                for key in completed[: len(self._runs) - 30]:
                    self._runs.pop(key, None)
        thread = threading.Thread(
            target=self._execute,
            args=(run,),
            daemon=True,
            name=f"analysis-{run.run_id[:8]}",
        )
        thread.start()
        return run.snapshot()

    def get(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        return run.snapshot()

    def _execute(self, run: AnalysisRun) -> None:
        try:
            run.emit(
                "run.started",
                {
                    "load_id": run.load_id,
                    "fleet_notice": "Synthetic demo fleet economics",
                    "human_gate": "Nothing books without manager approval",
                },
            )
            inference = TracedInference(ParasailInference(), run.emit)
            grounding = TracedGrounding(YouSearchGrounding(), run.emit)
            pipeline = QuotePipeline(
                fleet=load_fleet_config(self.fleet_path),
                grounding=grounding,
                inference=inference,
                memory=ScopedMemory(use_crewai=True),
                max_parallel_loads=1,
                event_sink=run.emit,
            )
            result = asyncio.run(
                run_quote_flow(
                    self.loads_path,
                    pipeline,
                    limit=None,
                    load_ids={run.load_id},
                    event_sink=run.emit,
                )
            )
            if not result.get("decisions"):
                raise RuntimeError("CrewAI Flow completed without a decision")
            decision = result["decisions"][0]
            run.emit(
                "one.approval.pending",
                {
                    "quote_id": decision["quote_id"],
                    "message": "Ready to publish through One; human approval remains required.",
                },
            )
            run.emit(
                "run.completed",
                {
                    "elapsed_seconds": result.get("elapsed_seconds"),
                    "recommendation": decision["recommendation"],
                    "proposed_quote_gbp": decision["proposed_quote_gbp"],
                    "inference_usage": result.get("inference_usage", {}),
                },
            )
            run.complete(
                {
                    "decision": decision,
                    "elapsed_seconds": result.get("elapsed_seconds"),
                    "route_counts": result.get("route_counts", {}),
                    "inference_usage": result.get("inference_usage", {}),
                }
            )
        except Exception as exc:  # Surface provider failures to the trace UI.
            run.fail(exc)
        finally:
            self._slots.release()
