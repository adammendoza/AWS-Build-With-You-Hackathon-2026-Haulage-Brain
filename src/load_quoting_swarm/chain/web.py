"""Additive server: python -m load_quoting_swarm.chain.web [--offline]."""
import argparse
import asyncio
import json
import os
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..web import LoadboardState, make_handler as base_handler, _resolve_parameter
from ..analysis_runs import AnalysisRunManager
from .chain_planner import plan_day
from .discord import verify_interaction
from .economics import ROOT, DEFAULT_CONFIG
from .service import ChainService, enabled

ASSETS = Path(__file__).parent


def make_handler(state, service, runs=None, **auth):
    base = base_handler(state, runs, **auth)

    class Handler(base):
        def _chain_asset(self, name):
            content = (ASSETS / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8" if name.endswith("html") else "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'unsafe-inline' 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def _asset(self, name):
            if name == "index.html" and enabled():
                # Add a fleet link at response time; existing assets stay byte-for-byte unchanged.
                content = (ROOT / "src/load_quoting_swarm/web_assets/index.html").read_text().replace("</nav>", '<a class="nav-item" href="/fleet.html">Fleet policy simulation · exceptions</a></nav>', 1).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'")
                self.end_headers()
                self.wfile.write(content)
            else:
                super()._asset(name)

        def do_GET(self):
            path = urlparse(self.path).path
            if path not in {"/api/chain", "/api/fleet", "/fleet_results.json", "/fleet.html", "/fleet.js"}:
                return super().do_GET()
            if not enabled() or service is None:
                return self.send_error(404)
            if not self._require_auth(path):
                return
            try:
                if path == "/api/chain":
                    scn = json.loads((ROOT / "data/chain/chain_scenario_v1.json").read_text())
                    self._json(plan_day(scn, fleet_config_path=service.config_path, diesel_ppl=service.diesel_ppl))
                elif path in {"/api/fleet", "/fleet_results.json"}:
                    self._json(service.payload())
                else:
                    self._chain_asset(path.lstrip("/"))
            except (ValueError, OSError):
                self._json({"error": "chain simulation could not be loaded"}, HTTPStatus.BAD_REQUEST)

        def do_POST(self):
            path = urlparse(self.path).path
            if path not in {"/api/fleet", "/api/chain/decision", "/api/chain/discord/interactions"}:
                return super().do_POST()
            if not enabled() or service is None:
                return self.send_error(404)
            discord = path.endswith("/discord/interactions")
            if not discord and not self._require_auth(path):
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 64_000:
                    raise ValueError("invalid request size")
                raw = self.rfile.read(length)
                if discord:
                    try:
                        verify_interaction(raw, self.headers.get("X-Signature-Ed25519", ""),
                                           self.headers.get("X-Signature-Timestamp", ""), os.getenv("DISCORD_PUBLIC_KEY", ""))
                    except ValueError:
                        return self._json({"error": "invalid Discord signature"}, HTTPStatus.UNAUTHORIZED)
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError("request must be an object")
                if discord:
                    if body.get("type") == 1:
                        return self._json({"type": 1})
                    user = str((body.get("member", {}).get("user") or body.get("user") or {}).get("id", ""))
                    managers = set(filter(None, os.getenv("HB_DISCORD_MANAGER_IDS", "").split(",")))
                    channel = os.getenv("ONE_DISCORD_CHANNEL_ID", "")
                    if not channel or body.get("channel_id") != channel or user not in managers:
                        return self._json({"type": 4, "data": {"content": "Manager or channel is not authorized.", "flags": 64}})
                    if body.get("type") != 3:
                        raise ValueError("only exception buttons are supported")
                    prefix, action, key = body.get("data", {}).get("custom_id", "").split(":", 2)
                    if prefix != "chain":
                        raise ValueError("unsupported interaction")
                    result = service.resolve(key, action, f"discord:{user}")
                    return self._json({"type": 4, "data": {"content": result["status"], "flags": 64}})
                if path == "/api/fleet":
                    if body.get("commit") is not True:
                        raise ValueError("commit=true is required")
                    self._json(service.commit())
                else:
                    self._json(service.resolve(str(body.get("exception_id", "")), str(body.get("action", "")), str(body.get("manager", ""))))
            except (ValueError, PermissionError) as exc:
                if discord:
                    self._json({"type": 4, "data": {"content": str(exc), "flags": 64}})
                else:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    return Handler


def main():
    from dotenv import load_dotenv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--offline", action="store_true", help="Explicit synthetic diesel snapshot; no partner calls")
    parser.add_argument("--fleet", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--storage", type=Path, default=Path("var/chain"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    username, password = os.getenv("DEMO_USERNAME"), os.getenv("DEMO_PASSWORD")
    if bool(username) != bool(password):
        raise SystemExit("DEMO_USERNAME and DEMO_PASSWORD must be configured together")
    service = None
    if enabled():
        diesel, market = None, None
        if not args.offline:
            from ..grounding import YouSearchGrounding
            from ..models import FreightLoad
            _resolve_parameter("YDC_API_KEY")
            fleet = json.loads((ROOT / "data/fleet/fleet_100_v1.json").read_text())
            result = asyncio.run(YouSearchGrounding().market_inputs(FreightLoad.from_raw(fleet["trucks"][0]["first_job"])))
            diesel, market = result.diesel_price_ppl, result.to_dict()
        service = ChainService(storage=args.storage, config_path=args.fleet, diesel_ppl=diesel, market=market)
    state = LoadboardState(ROOT / "data/loads_v2.json", args.storage / "loadboard-ledger.jsonl")
    handler = make_handler(state, service, AnalysisRunManager(ROOT / "data/loads_v2.json", args.fleet), auth_username=username, auth_password=password)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Chain server: http://{args.host}:{args.port}/fleet.html · enabled={enabled()} · offline={args.offline}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
