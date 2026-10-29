from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import hashlib
import hmac
import html
import json
import mimetypes
import os
import secrets
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any
from http.cookies import CookieError, SimpleCookie
from urllib.parse import parse_qs, urlparse

from .analysis_runs import AnalysisRunManager
from .ledger import BookingLedger, LedgerError
from .pricing import quote
from .spooky_brain import plan_loops
from .brain_ai import respond
from .inference import InferenceError


ASSET_DIR = Path(__file__).with_name("web_assets")
ASSET_NAMES = (
    "index.html",
    "app.css",
    "app.js",
    "atmosphere.js",
    "easter-eggs.js",
    "haunted-road.jpg",
    "spooky-brain.js",
    "spooky-brain.css",
    "loop-demo.json",
    "zombie-brain.svg",
    "spooky-art.js",
    "creature-motion.js",
    "creature-motion.css",
    "brain-replies.js",
    "brain-replies.css",
    "creature-brain.webp",
    "creature-spider.webp",
    "creature-ghost.webp",
    "creature-pumpkin.webp",
    "creature-skeleton.webp",
)
SESSION_COOKIE = "haulage_brain_session"


def _basic_auth_valid(
    authorization: str | None, username: str, password: str
) -> bool:
    if not authorization or not authorization.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(
            authorization.removeprefix("Basic ").strip(), validate=True
        ).decode("utf-8")
        supplied_username, supplied_password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return False
    username_matches = secrets.compare_digest(supplied_username, username)
    password_matches = secrets.compare_digest(supplied_password, password)
    return username_matches and password_matches


def _session_token(username: str, password: str) -> str:
    message = f"haulage-brain-demo-session-v1:{username}".encode("utf-8")
    return hmac.new(password.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _session_cookie_valid(
    cookie_header: str | None, username: str, password: str
) -> bool:
    if not cookie_header:
        return False
    try:
        cookies = SimpleCookie()
        cookies.load(cookie_header)
        supplied = cookies[SESSION_COOKIE].value
    except (CookieError, KeyError):
        return False
    return secrets.compare_digest(supplied, _session_token(username, password))


def _resolve_parameter(name: str) -> None:
    parameter_name = os.getenv(f"{name}_PARAMETER")
    if os.getenv(name) or not parameter_name:
        return
    import boto3

    response = boto3.client("ssm").get_parameter(
        Name=parameter_name,
        WithDecryption=True,
    )
    os.environ[name] = response["Parameter"]["Value"]


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
    def __init__(self, loads_path: Path, ledger_path: Path, fleet_path: Path | None = None):
        self.loads_path = loads_path
        self.fleet_path = fleet_path or loads_path.resolve().parent.parent / "config/fleet.demo.json"
        self.ledger = BookingLedger(ledger_path)
        self._decision_lock = Lock()
        self._brain_slots = BoundedSemaphore(2)

    def brain(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self._brain_slots.acquire(blocking=False):
            raise RuntimeError("Spooky Brain is handling two requests. Please try again shortly.")
        try:
            fleet = json.loads(self.fleet_path.read_text(encoding="utf-8"))
            return asyncio.run(respond(body, fleet, self.plan))
        finally:
            self._brain_slots.release()

    def plan(self, body: dict[str, Any]) -> dict[str, Any]:
        fleet = json.loads(self.fleet_path.read_text(encoding="utf-8"))
        source = body.get("source", "demo")
        if source not in {"demo", "loadboard"}:
            raise ValueError("Choose demo or loadboard as the load source.")
        loads = (json.loads((ASSET_DIR / "loop-demo.json").read_text())
                 if source == "demo" else self.raw_loads())
        result = plan_loops(loads, fleet, body, self.ledger.state() if source == "loadboard" else {})
        result["source"] = source
        result["input_loads"] = len(loads)
        return result

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
            "brain": {
                "provider": "Parasail",
                "configured": bool(os.getenv("PARASAIL_API_KEY") and os.getenv("PARASAIL_MODEL")),
                "model": os.getenv("PARASAIL_MODEL", ""),
            },
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


def make_handler(
    state: LoadboardState,
    runs: AnalysisRunManager | None = None,
    *,
    auth_username: str | None = None,
    auth_password: str | None = None,
):
    class Handler(BaseHTTPRequestHandler):
        server_version = "HaulageBrain/0.1"

        def _has_valid_auth(self) -> bool:
            if auth_username is None and auth_password is None:
                return True
            if not auth_username or not auth_password:
                return False
            return _basic_auth_valid(
                self.headers.get("Authorization"), auth_username, auth_password
            ) or _session_cookie_valid(
                self.headers.get("Cookie"), auth_username, auth_password
            )

        def _require_auth(self, path: str) -> bool:
            if self._has_valid_auth():
                return True
            if path.startswith("/api/"):
                self._json(
                    {"error": "authentication required"}, HTTPStatus.UNAUTHORIZED
                )
            else:
                self._redirect("/login")
            return False

        def _redirect(self, location: str, *, cookie: str | None = None) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _login_page(self, *, invalid: bool = False) -> None:
            error = (
                '<p class="error" role="alert">Incorrect username or password.</p>'
                if invalid
                else ""
            )
            username = html.escape(auth_username or "", quote=True)
            payload = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign in · Haulage Brain</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ min-height: 100vh; margin: 0; display: grid; place-items: center; background: #11130f; color: #f4f6ef; }}
    main {{ width: min(92vw, 420px); padding: 34px; border: 1px solid #45543a; border-radius: 16px; background: #1b1e18; box-shadow: 0 24px 70px #0008; }}
    .eyebrow {{ color: #8dc65e; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; font-size: 12px; }}
    h1 {{ margin: 8px 0; font-size: 30px; }}
    .intro {{ margin: 0 0 24px; color: #b8bdb3; line-height: 1.5; }}
    label {{ display: block; margin: 16px 0 7px; color: #d9ddd4; font-weight: 700; }}
    input {{ width: 100%; padding: 13px 14px; border: 1px solid #4a5045; border-radius: 9px; background: #10120e; color: white; font: inherit; }}
    input:focus {{ outline: 2px solid #78b84a; border-color: transparent; }}
    button {{ width: 100%; margin-top: 22px; padding: 13px; border: 0; border-radius: 9px; background: #70ad45; color: #0d1408; font: inherit; font-weight: 900; cursor: pointer; }}
    button:hover {{ background: #84c455; }}
    .error {{ padding: 10px 12px; border-radius: 8px; background: #481f1f; color: #ffbcbc; }}
  </style>
</head>
<body>
  <main>
    <div class="eyebrow">Fleet operations demo</div>
    <h1>Haulage Brain</h1>
    <p class="intro">Sign in to review loads, run the agent swarm, and approve quotes.</p>
    {error}
    <form method="post" action="/login">
      <label for="username">Username</label>
      <input id="username" name="username" value="{username}" autocomplete="username" required autofocus>
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">Sign in</button>
    </form>
  </main>
</body>
</html>""".encode("utf-8")
            self.send_response(
                HTTPStatus.UNAUTHORIZED if invalid else HTTPStatus.OK
            )
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; "
                "form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(payload)

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
            if path == "/health":
                self._json({"status": "ok"})
                return
            if path == "/login":
                if self._has_valid_auth():
                    self._redirect("/")
                else:
                    self._login_page()
                return
            if path == "/logout":
                self._redirect(
                    "/login",
                    cookie=(
                        f"{SESSION_COOKIE}=; Path=/; Secure; HttpOnly; "
                        "SameSite=Strict; Max-Age=0"
                    ),
                )
                return
            if not self._require_auth(path):
                return
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
            if path == "/login":
                length = int(self.headers.get("Content-Length", "0"))
                if length > 4_096:
                    self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    return
                form = parse_qs(
                    self.rfile.read(length).decode("utf-8", errors="replace")
                )
                username = (form.get("username") or [""])[0]
                password = (form.get("password") or [""])[0]
                if (
                    auth_username
                    and auth_password
                    and secrets.compare_digest(username, auth_username)
                    and secrets.compare_digest(password, auth_password)
                ):
                    token = _session_token(auth_username, auth_password)
                    self._redirect(
                        "/",
                        cookie=(
                            f"{SESSION_COOKIE}={token}; Path=/; Secure; HttpOnly; "
                            "SameSite=Strict; Max-Age=28800"
                        ),
                    )
                else:
                    self._login_page(invalid=True)
                return
            if not self._require_auth(path):
                return
            if path not in {"/api/decision", "/api/runs", "/api/plan", "/api/brain"}:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 64_000:
                    raise ValueError("request body is too large")
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("request body must be a JSON object")
                if path == "/api/brain":
                    self._json(state.brain(body))
                elif path == "/api/plan":
                    self._json(state.plan(body))
                elif path == "/api/runs":
                    if runs is None:
                        raise ValueError("live analysis is not configured")
                    load_id = str(body.get("load_id") or "").strip()
                    if not load_id:
                        raise ValueError("load_id is required")
                    self._json(runs.start(load_id), HTTPStatus.ACCEPTED)
                else:
                    self._json(state.decide(body), HTTPStatus.CREATED)
            except OSError:
                self._json({"error": "Planner fixture or fleet configuration is unavailable. Check the configured file paths."}, HTTPStatus.INTERNAL_SERVER_ERROR)
            except InferenceError as exc:
                self._json({"error": str(exc), "provider": "Parasail"}, HTTPStatus.SERVICE_UNAVAILABLE)
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.TOO_MANY_REQUESTS)
            except (LedgerError, ValueError, TypeError, json.JSONDecodeError) as exc:
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
    parser.add_argument("--env-file", type=Path, help="Server-only credentials file; defaults to .env.local, then .env")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    return parser


def main() -> int:
    from dotenv import find_dotenv, load_dotenv

    args = build_parser().parse_args()
    if args.env_file and not args.env_file.is_file():
        raise SystemExit("The configured environment file does not exist.")
    env_file = args.env_file or find_dotenv(".env.local", usecwd=True) or find_dotenv(usecwd=True)
    load_dotenv(env_file)
    if not args.env_file:
        load_dotenv(find_dotenv(usecwd=True))
    for secret_name in ("YDC_API_KEY", "PARASAIL_API_KEY", "DEMO_PASSWORD", "DISCORD_WEBHOOK_URL"):
        _resolve_parameter(secret_name)
    if not args.loads.exists():
        raise SystemExit(f"load fixture not found: {args.loads}")
    state = LoadboardState(args.loads, args.ledger, args.fleet)
    runs = AnalysisRunManager(args.loads, args.fleet)
    auth_username = os.getenv("DEMO_USERNAME")
    auth_password = os.getenv("DEMO_PASSWORD")
    if bool(auth_username) != bool(auth_password):
        raise SystemExit("DEMO_USERNAME and DEMO_PASSWORD must be configured together")
    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(
            state,
            runs,
            auth_username=auth_username,
            auth_password=auth_password,
        ),
    )
    url = f"http://{args.host}:{args.port}"
    print(f"Haulage Brain UI: {url}")
    print(f"Fixture: {args.loads} · Ledger: {args.ledger}")
    print(f"Authentication: {'enabled' if auth_username else 'disabled'}")
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
