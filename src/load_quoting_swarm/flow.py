from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .ingest import available_loads, load_freight_loads
from .models import FreightLoad
from .routing import route_loads

if TYPE_CHECKING:
    from .pipeline import QuotePipeline

try:
    from crewai.flow.flow import Flow, listen, router, start
except ImportError:  # Core ingestion remains testable before hackathon dependencies install.
    Flow = None  # type: ignore[assignment]


def ingest_and_route(loads_path: str | Path, *, limit: int | None = 3) -> dict[str, Any]:
    all_loads = load_freight_loads(loads_path)
    selected = available_loads(all_loads, limit=limit)
    groups = route_loads(selected)
    return {
        "source_count": len(all_loads),
        "available_count": len([item for item in all_loads if item.is_available]),
        "selected_count": len(selected),
        "routes": {
            key: [item.load.to_dict() for item in values]
            for key, values in groups.items()
        },
    }


if Flow is not None:

    class LoadIngestFlow(Flow):
        """CrewAI Flow for the first working milestone: ingest then route."""

        def __init__(self, loads_path: str | Path, limit: int | None = 3):
            super().__init__()
            self.loads_path = str(loads_path)
            self.limit = limit

        @start()
        def ingest(self) -> dict[str, Any]:
            all_loads = load_freight_loads(self.loads_path)
            selected = available_loads(all_loads, limit=self.limit)
            self.state["source_count"] = len(all_loads)
            self.state["available_count"] = len(
                [item for item in all_loads if item.is_available]
            )
            self.state["loads"] = [item.to_dict() for item in selected]
            self.state["selected_count"] = len(selected)
            return {"selected_count": len(selected)}

        @router(ingest)
        def choose_route(self) -> str:
            return "route_available" if self.state.get("loads") else "no_available"

        @listen("route_available")
        def build_routes(self) -> dict[str, Any]:
            loads = [FreightLoad.from_raw(item) for item in self.state["loads"]]
            groups = route_loads(loads)
            routes = {
                key: [item.load.to_dict() for item in values]
                for key, values in groups.items()
            }
            self.state["routes"] = routes
            return {
                "source_count": self.state["source_count"],
                "available_count": self.state["available_count"],
                "selected_count": self.state["selected_count"],
                "routes": routes,
            }

        @listen("no_available")
        def build_empty_routes(self) -> dict[str, Any]:
            self.state["routes"] = {}
            return {
                "source_count": self.state["source_count"],
                "available_count": self.state["available_count"],
                "selected_count": 0,
                "routes": {},
            }

else:

    class LoadIngestFlow:  # type: ignore[no-redef]
        def __init__(self, loads_path: str | Path, limit: int | None = 3):
            self.loads_path = loads_path
            self.limit = limit

        def kickoff(self) -> dict[str, Any]:
            return ingest_and_route(self.loads_path, limit=self.limit)


if Flow is not None:

    class LoadQuoteFlow(Flow):
        """CrewAI Flow owning ingest, vehicle/category routing, and swarm execution."""

        def __init__(
            self,
            loads_path: str | Path,
            pipeline: "QuotePipeline",
            limit: int | None = 3,
        ):
            super().__init__()
            self.loads_path = str(loads_path)
            self.pipeline = pipeline
            self.limit = limit
            self._selected = []
            self.result: dict[str, Any] | None = None

        @start()
        def ingest(self) -> dict[str, Any]:
            all_loads = load_freight_loads(self.loads_path)
            self._selected = available_loads(all_loads, limit=self.limit)
            self.state["source_count"] = len(all_loads)
            self.state["available_count"] = len(
                [item for item in all_loads if item.is_available]
            )
            self.state["selected_count"] = len(self._selected)
            return {"selected_count": len(self._selected)}

        @router(ingest)
        def route(self) -> str:
            groups = route_loads(self._selected)
            self.state["route_counts"] = {
                key: len(items) for key, items in groups.items()
            }
            return "analyze_available" if self._selected else "nothing_to_analyze"

        @listen("analyze_available")
        async def run_analysis(self) -> dict[str, Any]:
            self.result = await self.pipeline.quote_many(self._selected)
            self.result["route_counts"] = dict(self.state["route_counts"])
            return self.result

        @listen("nothing_to_analyze")
        def build_empty_result(self) -> dict[str, Any]:
            self.result = {
                "fixture_count": 0,
                "route_counts": {},
                "decisions": [],
                "inference_usage": self.pipeline.inference.usage(),
            }
            return self.result

else:

    class LoadQuoteFlow:  # type: ignore[no-redef]
        def __init__(
            self,
            loads_path: str | Path,
            pipeline: "QuotePipeline",
            limit: int | None = 3,
        ):
            self.loads_path = loads_path
            self.pipeline = pipeline
            self.limit = limit
            self.result: dict[str, Any] | None = None

        async def kickoff_async(self) -> dict[str, Any]:
            selected = available_loads(
                load_freight_loads(self.loads_path), limit=self.limit
            )
            groups = route_loads(selected)
            self.result = await self.pipeline.quote_many(selected)
            self.result["route_counts"] = {
                key: len(items) for key, items in groups.items()
            }
            return self.result


async def run_quote_flow(
    loads_path: str | Path,
    pipeline: "QuotePipeline",
    *,
    limit: int | None,
) -> dict[str, Any]:
    flow = LoadQuoteFlow(loads_path, pipeline, limit=limit)
    await flow.kickoff_async()
    if flow.result is None:
        raise RuntimeError("load quote Flow completed without a result")
    return flow.result
