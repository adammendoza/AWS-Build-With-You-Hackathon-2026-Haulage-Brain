from __future__ import annotations

import argparse
import json
import mimetypes
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from .analysis_runs import AnalysisRunManager
from .ledger import BookingLedger, LedgerError
from .pricing import quote


ASSET_DIR = Path(__file__).with_name("web_assets")
ASSET_NAMES = (
    "index.html", "app.css", "app.js", "atmosphere.js", "haunt-lantern.png"
)


def _pickup_at(load: dict[str, Any]) -> datetime:
    pickup = load.get("pickup") or {}
    value = pickup.get("time") or pickup.get("start")
    if not value:
        raise ValueError("pickup time is missing")
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def quote_analysis(load: dict[str, Any]) -> dict[str, Any]:
    origin = load.get("from_") or {}
    destination = load.get("to") or {}
    result = quote(
        float(load["distance_miles"]),
        int(load["journey_minutes_est"]),
        str(origin.get("postcode") or ""),
        str(destination.get("postcode") or ""),
        _pickup_at(load),
    )
    offered = float(load.get("agreed_rate_gbp") or 0)
    result["offered_rate_gbp"] = offered
    result["difference_gbp"] = round(offered - result["total"], 2)
    result["offered_margin_pct"] = (
        round((offered - result["total"]) / offered * 100, 2) if offered else None
    )
    if result["status"] != "ok":
        result["recommendation"] = "REVIEW"
    elif offered >= result["total"]:
        result["recommendation"] = "APPROVE"
    else:
        result["recommendation"] = "REPRICE"
    return result


class LoadboardState:
    def __init__(self, loads_path: Path, ledger_path: Path):
        self.loads_path = loads_path
        self.ledger = BookingLedger(ledger_path)
        self._decision_lock = Lock()

    def raw_loads(self) -> list[dict[str, Any]]:
        payload = json.loads(self.loads_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("loadboard JSON must contain an array")
        return payload

    def payload(self) -> dict[str, Any]:
        loads = self.raw_loads()
        ledger = self.ledger.state()
        enriched: list[dict[str, Any]] = []
        for load in loads:
            item = dict(load)
            item["quote_analysis"] = quote_analysis(load)
            quote_id = f"Q-{load['load_id']}"
            item["ledger"] = ledger.get(quote_id)
            enriched.append(item)

        rates = [float(item.get("agreed_rate_gbp") or 0) for item in loads]
        rates_per_mile = [
            float(item["rate_per_mile"])
            for item in loads
            if item.get("rate_per_mile") is not None
        ]
        return {
            "deployment": {
                "mode": "server",
                "decision_store": "append-only booking ledger",
            },
            "summary": {
                "loads": len(loads),
                "available": sum(item.get("status") == "Available" for item in loads),
                "average_rate_gbp": round(sum(rates) / len(rates), 0) if rates else 0,
                "average_rate_per_mile_gbp": round(
                    sum(rates_per_mile) / len(rates_per_mile), 2
                )
                if rates_per_mile
                else 0,
            },
            "loads": enriched,
        }

    def decide(self, body: dict[str, Any]) -> dict[str, Any]:
        load_id = str(body.get("load_id") or "")
        decision = str(body.get("decision") or "").upper()
        manager = str(body.get("manager") or "").strip() or "Fleet Manager"
        load = next(
            (item for item in self.raw_loads() if str(item.get("load_id")) == load_id),
            None,
        )
        if load is None:
            raise LedgerError(f"unknown load: {load_id}")
        if load.get("status") != "Available":
            raise LedgerError("only Available loads can receive a manager decision")

        analysis = quote_analysis(load)
        quote_id = f"Q-{load_id}"
        with self._decision_lock:
            if quote_id not in self.ledger.state():
                self.ledger.record_quote_summary(
                    quote_id=quote_id,
                    load_id=load_id,
                    recommendation=analysis["recommendation"],
                    proposed_quote_gbp=float(analysis["total"]),
                )
            return self.ledger.decide(
                quote_id, decision=decision, manager=manager
            )


def make_handler(state: LoadboardState, runs: AnalysisRunManager | None = None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "HaulageBrain/0.1"

        def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def _asset(self, name: str) -> None:
            safe_name = name if name in ASSET_NAMES else ""
            path = ASSET_DIR / safe_name
            if not safe_name or not path.exists():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            payload = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            if content_type.startswith("text/") or content_type == "application/javascript":
                content_type += "; charset=utf-8"
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; object-src 'none'",
            )
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlparse(self.path).path
            try:
                if path in {"/api/loads", "/api/loads.json"}:
                    self._json(state.payload())
                elif path == "/api/raw":
                    self._json(state.raw_loads())
                elif path == "/api/ledger":
                    self._json(state.ledger.state())
                elif path.startswith("/api/runs/") and runs is not None:
                    run_id = path.removeprefix("/api/runs/")
                    self._json(runs.get(run_id))
                elif path in {"/", "/index.html"}:
                    self._asset("index.html")
                elif path.removeprefix("/") in ASSET_NAMES:
                    self._asset(path.lstrip("/"))
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except KeyError:
                self._json({"error": "analysis run not found"}, HTTPStatus.NOT_FOUND)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlparse(self.path).path
            if path not in {"/api/decision", "/api/runs"}:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 64_000:
                    raise ValueError("request body is too large")
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("request body must be a JSON object")
                if path == "/api/runs":
                    if runs is None:
                        raise ValueError("live analysis is not configured")
                    load_id = str(body.get("load_id") or "").strip()
                    if not load_id:
                        raise ValueError("load_id is required")
                    self._json(runs.start(load_id), HTTPStatus.ACCEPTED)
                else:
                    self._json(state.decide(body), HTTPStatus.CREATED)
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.TOO_MANY_REQUESTS)
            except (LedgerError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def log_message(self, format_string: str, *args: Any) -> None:
            print(f"[loadboard] {self.address_string()} {format_string % args}")

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="haulage-brain-ui")
    parser.add_argument("--loads", type=Path, default=Path("data/loads_v2.json"))
    parser.add_argument(
        "--ledger", type=Path, default=Path("var/booking-ledger.jsonl")
    )
    parser.add_argument("--fleet", type=Path, default=Path("config/fleet.demo.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    return parser


def main() -> int:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
    args = build_parser().parse_args()
    if not args.loads.exists():
        raise SystemExit(f"load fixture not found: {args.loads}")
    state = LoadboardState(args.loads, args.ledger)
    runs = AnalysisRunManager(args.loads, args.fleet)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state, runs))
    url = f"http://{args.host}:{args.port}"
    print(f"Haulage Brain UI: {url}")
    print(f"Fixture: {args.loads} · Ledger: {args.ledger}")
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping loadboard.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
