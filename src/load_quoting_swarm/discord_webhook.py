from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DiscordWebhookError(RuntimeError):
    pass


def _clip(value: Any, limit: int) -> str:
    rendered = " ".join(str(value or "").split())
    return rendered if len(rendered) <= limit else rendered[: limit - 3] + "..."


def _event_data(
    events: list[dict[str, Any]], event_type: str, *, role: str | None = None
) -> dict[str, Any]:
    for event in events:
        if event.get("type") != event_type:
            continue
        data = event.get("data") or {}
        if role is None or data.get("role") == role:
            return data
    return {}


class DiscordWebhookPublisher:
    """Server-side fallback publisher for the event's venue webhook."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        if not self.webhook_url.startswith("https://discord.com/api/webhooks/"):
            raise DiscordWebhookError("DISCORD_WEBHOOK_URL is missing or invalid")
        self.app_url = os.getenv("PUBLIC_APP_URL", "").rstrip("/")

    def publish(
        self,
        decision: dict[str, Any],
        *,
        events: list[dict[str, Any]] | None = None,
        run_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        events = events or []
        run_summary = run_summary or {}
        quote_id = str(decision.get("quote_id") or "unknown quote")
        load_id = str(decision.get("load_id") or "unknown load")
        recommendation = str(decision.get("recommendation") or "REVIEW")
        quote = float(decision.get("proposed_quote_gbp") or 0)
        pricing = decision.get("pricing") or {}
        margin = pricing.get("offered_margin_pct")
        vehicle = (decision.get("fleet_fit") or {}).get("selected_vehicle_id")
        margin_text = f"{float(margin):.1f}%" if margin is not None else "unknown"

        ingest = _event_data(events, "crewai.ingest.completed")
        routing = _event_data(events, "crewai.route.completed")
        market = _event_data(events, "you.grounding.completed")
        tools = _event_data(events, "tools.assessment.completed")
        supervisor = _event_data(events, "parasail.supervisor.completed")
        safety = _event_data(events, "safety.gate.completed")
        route_names = ", ".join((routing.get("route_counts") or {}).keys())

        citations = market.get("citations") or []
        source_lines = []
        for citation in citations[:2]:
            title = _clip(citation.get("title"), 70).replace("]", "")
            url = str(citation.get("url") or "")
            if title and url.startswith("https://"):
                source_lines.append(f"[{title}]({url})")
        source_text = " · ".join(source_lines) or "No citations returned"

        specialists = []
        for role in ("pricing", "compliance", "fleet-fit"):
            data = _event_data(events, "parasail.specialist.completed", role=role)
            summary = _clip(data.get("summary"), 190) or "Structured checks completed."
            confidence = data.get("confidence")
            confidence_text = (
                f" · confidence {float(confidence):.0%}"
                if confidence is not None
                else ""
            )
            specialists.append(
                f"**{role.replace('-', ' ').title()}**{confidence_text}: {summary}"
            )

        approval_url = (
            f"{self.app_url}/?load={load_id}" if self.app_url else "Haulage Brain UI"
        )
        inference_usage = run_summary.get("inference_usage") or {}
        elapsed = run_summary.get("elapsed_seconds")
        footer_parts = [f"{inference_usage.get('requests', 0)} Parasail calls"]
        if elapsed is not None:
            footer_parts.append(f"{float(elapsed):.1f}s pipeline time")
        footer_parts.append("venue webhook fallback")

        content = (
            f"**Haulage Brain · Full decision audit · {quote_id}**\n"
            f"Load `{load_id}` · final recommendation **{recommendation}** · "
            f"proposed quote **£{quote:,.2f}**\n"
            "Every step below is runtime evidence from this load."
        )
        embed = {
            "title": "Closed-loop load processing trace",
            "description": (
                f"Vehicle: **{vehicle or 'not assigned'}** · "
                f"offered margin: **{margin_text}** · human status: **PENDING**"
            ),
            "color": 0xD9534F if recommendation == "PASS" else 0x70AD45,
            "fields": [
                {
                    "name": "1 · CrewAI — ingest and route",
                    "value": (
                        f"Selected **{ingest.get('selected_count', 1)}** load from "
                        f"{ingest.get('source_count', 'the fixture')} records. "
                        f"Route: `{route_names or 'vehicle/category route'}`."
                    ),
                    "inline": False,
                },
                {
                    "name": "2 · You.com — live market grounding",
                    "value": (
                        f"Diesel **{float(market.get('diesel_price_ppl') or 0):.2f}p/L** · "
                        f"ULEZ/restriction charge **£{float(market.get('ulez_charge_gbp') or 0):,.2f}**.\n"
                        f"Sources: {source_text}"
                    ),
                    "inline": False,
                },
                {
                    "name": "3 · Deterministic quote tools — live data changes price",
                    "value": (
                        f"Offered **£{float(tools.get('offered_rate_gbp') or 0):,.2f}** · "
                        f"cost **£{float(tools.get('estimated_total_cost_gbp') or 0):,.2f}** · "
                        f"target **£{float(tools.get('target_quote_gbp') or quote):,.2f}** · "
                        f"live-data effect **£{float(tools.get('live_quote_delta_gbp') or 0):+,.2f}**."
                    ),
                    "inline": False,
                },
                {
                    "name": "4 · Parasail — three scoped specialists",
                    "value": "\n".join(specialists),
                    "inline": False,
                },
                {
                    "name": "5 · Parasail supervisor + deterministic safety gate",
                    "value": (
                        f"Model: **{supervisor.get('recommendation', 'REVIEW')}** → "
                        f"gate: **{safety.get('final_recommendation', recommendation)}**. "
                        f"{_clip(safety.get('rationale') or decision.get('rationale'), 500)}"
                    ),
                    "inline": False,
                },
                {
                    "name": "6 · Human approval — action remains gated",
                    "value": (
                        f"[Open Haulage Brain to approve or pass]({approval_url}). "
                        "Nothing books without a fleet manager's explicit approval."
                    ),
                    "inline": False,
                },
            ],
            "footer": {"text": " · ".join(footer_parts)},
        }
        payload = json.dumps(
            {
                "content": content,
                "embeds": [embed],
                "allowed_mentions": {"parse": []},
            }
        ).encode("utf-8")
        request = Request(
            self.webhook_url,
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": (
                    "DiscordBot "
                    "(https://github.com/adammendoza/"
                    "AWS-Build-With-You-Hackathon-2026-Haulage-Brain, 0.1.0)"
                ),
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                status = response.status
        except HTTPError as exc:
            detail = exc.read(500).decode("utf-8", errors="replace")
            raise DiscordWebhookError(
                f"Discord webhook returned HTTP {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise DiscordWebhookError(f"Discord webhook request failed: {exc.reason}") from exc
        if status != 204:
            raise DiscordWebhookError(
                f"Discord webhook returned unexpected HTTP {status}"
            )
        return {"status_code": status, "delivery": "venue_webhook_fallback"}
