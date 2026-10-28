from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from .models import QuoteDecision


class OneError(RuntimeError):
    pass


def _find_candidates(value: Any):
    if isinstance(value, dict):
        if value.get("actionId") and value.get("method"):
            yield value
        for child in value.values():
            yield from _find_candidates(child)
    elif isinstance(value, list):
        for child in value:
            yield from _find_candidates(child)


class OneDiscordPublisher:
    """Publishes quotes via One's discover-then-execute CLI contract."""

    def __init__(self):
        self.connection_key = os.getenv("ONE_DISCORD_CONNECTION_KEY", "")
        self.channel_id = os.getenv("ONE_DISCORD_CHANNEL_ID", "")
        if not self.connection_key or not self.channel_id:
            raise OneError(
                "ONE_DISCORD_CONNECTION_KEY and ONE_DISCORD_CHANNEL_ID are required"
            )
        if shutil.which("one") is None:
            raise OneError("One CLI is not installed; run npm i -g @withone/cli")
        self._send_action_id: str | None = None

    def _run(self, args: list[str]) -> dict[str, Any]:
        result = subprocess.run(
            ["one", "--agent", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise OneError(result.stderr.strip() or result.stdout.strip())
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise OneError("One CLI returned non-JSON output") from exc

    def _resolve_send_action(self) -> str:
        if self._send_action_id:
            return self._send_action_id
        found = self._run(
            [
                "actions",
                "find",
                "discord",
                "send a message to a channel",
                "--task",
                "post a freight quote for human approval",
            ]
        )
        candidates = [
            item
            for item in _find_candidates(found)
            if str(item.get("method", "")).upper() == "POST"
            and "channel" in str(item.get("path", "")).casefold()
        ]
        if not candidates:
            raise OneError("One did not return a Discord channel-message action")
        self._send_action_id = str(candidates[0]["actionId"])
        return self._send_action_id

    def publish(self, decision: QuoteDecision) -> dict[str, Any]:
        action_id = self._resolve_send_action()
        flags = list(decision.pricing.risk_flags) + list(decision.compliance.flags)
        sources = "\n".join(
            f"- {item.title}: {item.url}"
            for item in decision.market_inputs.citations[:3]
        )
        content = (
            f"**{decision.quote_id} · Load {decision.load_id}**\n"
            f"Recommendation: **{decision.recommendation}**\n"
            f"Quote: **£{decision.proposed_quote_gbp:,.2f}** · "
            f"Cost: £{decision.pricing.estimated_total_cost_gbp:,.2f} · "
            f"Offered margin: {decision.pricing.offered_margin_pct:.1f}%\n"
            f"Vehicle: {decision.fleet_fit.selected_vehicle_id or 'none'}\n"
            f"Risks: {', '.join(flags) if flags else 'none'}\n"
            f"Diesel input: {decision.market_inputs.diesel_price_ppl:.1f}p/L\n"
            f"Sources:\n{sources}\n\n"
            f"Human decision required: `APPROVE {decision.quote_id}` or "
            f"`PASS {decision.quote_id}`. Nothing books automatically."
        )
        # The event's Discord action takes channelId in the path and content in the body.
        # Action IDs are always resolved at runtime rather than committed.
        return self._run(
            [
                "actions",
                "execute",
                "discord",
                action_id,
                self.connection_key,
                "--path-vars",
                json.dumps({"channelId": self.channel_id}),
                "-d",
                json.dumps({"content": content}),
            ]
        )
