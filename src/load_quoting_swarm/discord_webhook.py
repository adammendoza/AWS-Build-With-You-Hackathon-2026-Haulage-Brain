from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DiscordWebhookError(RuntimeError):
    pass


class DiscordWebhookPublisher:
    """Server-side fallback publisher for the event's venue webhook."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        if not self.webhook_url.startswith("https://discord.com/api/webhooks/"):
            raise DiscordWebhookError("DISCORD_WEBHOOK_URL is missing or invalid")
        self.app_url = os.getenv("PUBLIC_APP_URL", "").rstrip("/")

    def publish(self, decision: dict[str, Any]) -> dict[str, Any]:
        quote_id = str(decision.get("quote_id") or "unknown quote")
        load_id = str(decision.get("load_id") or "unknown load")
        recommendation = str(decision.get("recommendation") or "REVIEW")
        quote = float(decision.get("proposed_quote_gbp") or 0)
        pricing = decision.get("pricing") or {}
        margin = pricing.get("offered_margin_pct")
        vehicle = (decision.get("fleet_fit") or {}).get("selected_vehicle_id")
        rationale = " ".join(str(decision.get("rationale") or "").split())
        if len(rationale) > 500:
            rationale = rationale[:497] + "..."
        approval = (
            f"\nReview and approve/pass: {self.app_url}/?load={load_id}"
            if self.app_url
            else "\nHuman approval required in Haulage Brain."
        )
        margin_text = f"{float(margin):.1f}%" if margin is not None else "unknown"
        content = (
            f"**Haulage Brain · {quote_id} · Load {load_id}**\n"
            f"Recommendation: **{recommendation}**\n"
            f"Proposed quote: **£{quote:,.2f}** · Offered margin: {margin_text}\n"
            f"Vehicle: {vehicle or 'not assigned'}\n"
            f"Rationale: {rationale or 'See the analysis trace.'}"
            f"{approval}\n"
            "Nothing books without a fleet manager's approval. "
            "Delivery: venue webhook fallback."
        )
        payload = json.dumps(
            {"content": content, "allowed_mentions": {"parse": []}}
        ).encode("utf-8")
        request = Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
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
