"""Run live diesel + Parasail explanations on a few synthetic trucks and save safe evidence."""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from ..grounding import YouSearchGrounding
from .explanations import ChainExplanations
from ..models import FreightLoad
from .discord import publish_exception
from .economics import ROOT, DEFAULT_CONFIG
from .fleet_planner import run
from .service import ChainService


async def execute(args):
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    source = json.loads((ROOT / "data/fleet/fleet_100_v1.json").read_text())
    source["trucks"] = source["trucks"][:args.limit]
    source["meta"]["scenario"] += f"_live_{args.limit}"
    fleet_file = output / "sample-input.json"
    fleet_file.write_text(json.dumps(source))
    log = {"started_at": datetime.now(timezone.utc).isoformat(), "synthetic_trucks": True,
           "trucks": args.limit, "events": []}
    try:
        market = await YouSearchGrounding().market_inputs(FreightLoad.from_raw(source["trucks"][0]["first_job"]))
        log["market"] = market.to_dict()
        log["events"].append({"provider": "You.com", "status": "succeeded"})
        service = ChainService(storage=output / "state", fleet_path=fleet_file, config_path=args.fleet,
                               diesel_ppl=market.diesel_price_ppl, market=market.to_dict())
        result = service.payload()
        result["meta"]["is_sample"] = True
        inference = ChainExplanations()
        async def explain(truck):
            notes = await asyncio.gather(*(inference.specialist(role, {
                "truck": truck, "market": market.to_dict(),
                "instruction": "Explain this deterministic simulation plan. Do not change bookings, hours, or compliance gates."
            }) for role in ("pricing", "compliance", "fleet-fit")))
            return {"truck_id": truck["truck_id"], "specialists": dict(zip(("pricing", "compliance", "fleet-fit"), notes))}
        log["explanations"] = await asyncio.gather(*(explain(t) for t in result["trucks"]))
        log["inference_usage"] = inference.usage()
        log["events"].append({"provider": "Parasail", "status": "succeeded"})
        if args.discord:
            log["discord"] = [{"exception_id": e["exception_id"], **await asyncio.to_thread(publish_exception, e)} for e in result["exceptions"]]
            if not result["exceptions"]:
                log["discord"] = [{"delivery": "skipped", "reason": "no exceptions in sample"}]
        (output / "fleet_results.json").write_text(json.dumps(result, indent=2))
        log["status"] = "COMPLETED"
        if args.discord and any(d.get("delivery") in {"failed", "unavailable"} for d in log["discord"]):
            log["status"] = "PARTIAL_DISCORD_BLOCKED"
    except Exception as exc:
        # Provider errors may contain request URLs or credentials. Persist types only.
        log.update(status="FAILED", error_type=type(exc).__name__)
    (output / "live-run.json").write_text(json.dumps(log, indent=2))
    print(json.dumps({"status": log["status"], "trucks": args.limit,
                      "events": log["events"], "evidence": str(output)}))
    return 0 if log["status"] == "COMPLETED" else 1


def main():
    from dotenv import load_dotenv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--fleet", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--limit", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--discord", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("var/chain-evidence/live"))
    args = parser.parse_args()
    load_dotenv(args.env_file)
    return asyncio.run(execute(args))


if __name__ == "__main__":
    raise SystemExit(main())
