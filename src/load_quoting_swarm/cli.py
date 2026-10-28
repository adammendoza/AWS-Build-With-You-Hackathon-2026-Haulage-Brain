from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from .config import load_fleet_config
from .flow import LoadIngestFlow, ingest_and_route, run_quote_flow
from .grounding import DemoGrounding, YouSearchGrounding
from .inference import DemoInference, ParasailInference
from .ingest import available_loads, load_freight_loads
from .ledger import BookingLedger, LedgerError
from .memory import ScopedMemory
from .one_discord import OneDiscordPublisher
from .pipeline import QuotePipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="haulage-brain")
    subcommands = parser.add_subparsers(dest="command", required=True)

    ingest = subcommands.add_parser("ingest", help="ingest and route Available loads")
    ingest.add_argument("--loads", type=Path, default=Path("data/loads_v2.json"))
    ingest.add_argument("--limit", type=int, default=3)
    ingest.add_argument(
        "--crewai",
        action="store_true",
        help="run through the CrewAI Flow (requires project dependencies)",
    )

    run = subcommands.add_parser("run", help="evaluate Available loads")
    run.add_argument("--loads", type=Path, default=Path("data/loads_v2.json"))
    run.add_argument("--fleet", type=Path, default=Path("config/fleet.demo.json"))
    run.add_argument("--limit", type=int, default=3)
    run.add_argument("--parallel", type=int, default=8)
    run.add_argument(
        "--live",
        action="store_true",
        help="require You.com and Parasail instead of explicit synthetic test doubles",
    )
    run.add_argument("--discord", action="store_true", help="publish quotes through One")
    run.add_argument(
        "--ledger", type=Path, default=Path("var/booking-ledger.jsonl")
    )
    run.add_argument("--record-ledger", action="store_true")
    run.add_argument("--output", type=Path)

    decide = subcommands.add_parser("decide", help="record a human APPROVE or PASS")
    decide.add_argument("quote_id")
    decide.add_argument("decision", choices=("APPROVE", "PASS"))
    decide.add_argument("--manager", required=True)
    decide.add_argument("--ledger", type=Path, default=Path("var/booking-ledger.jsonl"))

    ledger = subcommands.add_parser("ledger", help="show the booking ledger")
    ledger.add_argument("--ledger", type=Path, default=Path("var/booking-ledger.jsonl"))
    return parser


def main() -> int:
    load_dotenv(find_dotenv(usecwd=True))
    args = build_parser().parse_args()
    if args.command == "ingest":
        if args.crewai:
            result = LoadIngestFlow(args.loads, limit=args.limit).kickoff()
            if not isinstance(result, dict) or "routes" not in result:
                # CrewAI returns the last listener result; show the complete state when available.
                result = getattr(result, "state", result)
        else:
            result = ingest_and_route(args.loads, limit=args.limit)
        print(json.dumps(result, indent=2, default=str))
        return 0
    if args.command == "run":
        fleet = load_fleet_config(args.fleet)
        loads = available_loads(load_freight_loads(args.loads), limit=args.limit)
        grounding = YouSearchGrounding() if args.live else DemoGrounding()
        inference = ParasailInference() if args.live else DemoInference()
        pipeline = QuotePipeline(
            fleet=fleet,
            grounding=grounding,
            inference=inference,
            memory=ScopedMemory(use_crewai=args.live),
            max_parallel_loads=args.parallel,
        )
        result = asyncio.run(
            run_quote_flow(args.loads, pipeline, limit=args.limit)
        )
        ledger = BookingLedger(args.ledger)
        publishers = []
        if args.discord:
            publisher = OneDiscordPublisher()
            publishers = [publisher]
        if args.record_ledger or publishers:
            decisions_by_id = {
                decision.load_id: decision for decision in pipeline.last_decisions
            }
            for item in result["decisions"]:
                decision = decisions_by_id[item["load_id"]]
                if args.record_ledger:
                    ledger.record_quote(decision)
                for publisher in publishers:
                    publisher.publish(decision)
        rendered = json.dumps(result, indent=2, default=str)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0
    if args.command == "decide":
        event = BookingLedger(args.ledger).decide(
            args.quote_id, decision=args.decision, manager=args.manager
        )
        print(json.dumps(event, indent=2))
        return 0
    if args.command == "ledger":
        print(json.dumps(BookingLedger(args.ledger).state(), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
