"""One-first exception delivery and authenticated Discord interaction verification."""
import json
import os
import time
from urllib.request import Request, urlopen

from ..one_discord import OneDiscordPublisher


class ExceptionPublisher(OneDiscordPublisher):
    def execute_one_action(self, payload):
        """Discover the send action at runtime; preserve One's existing CLI contract."""
        return self._run([
            "actions", "execute", "discord", self._resolve_send_action(), self.connection_key,
            "--path-vars", json.dumps({"channelId": self.channel_id}), "-d", json.dumps(payload),
        ])


def exception_message(item):
    key = item["exception_id"]
    return {
        "content": (f"**Haulage Brain · simulation exception · {key}**\n"
                    f"{item['truck_id']} · {item['reason']}: {item['detail']}\n"
                    "Approve acknowledges the legal plan; Escalate leaves it for manual dispatch. "
                    "Hours limits cannot be overridden here."),
        "allowed_mentions": {"parse": []},
        "components": [{"type": 1, "components": [
            {"type": 2, "style": 3, "label": "Approve legal plan / acknowledge",
             "custom_id": f"chain:APPROVE:{key}"},
            {"type": 2, "style": 4, "label": "Escalate",
             "custom_id": f"chain:ESCALATE:{key}"},
        ]}],
    }


def publish_exception(item, *, publisher_factory=ExceptionPublisher, opener=urlopen):
    """One gets exactly two attempts. Never persist raw provider errors or secret URLs."""
    payload = exception_message(item)
    attempts = []
    for attempt in range(1, 3):
        try:
            publisher = publisher_factory()
            result = publisher.execute_one_action(payload)
            # Explicit provider failure envelopes must not be counted as success.
            if not isinstance(result, dict) or not result or result.get("success") is False or result.get("error") or result.get("isError"):
                raise RuntimeError("One did not confirm execution")
            return {"delivery": "one", "execute_one_action_succeeded": True,
                    "attempts": attempts + [{"attempt": attempt, "status": "succeeded"}]}
        except Exception as exc:
            attempts.append({"attempt": attempt, "status": "failed", "error_type": type(exc).__name__})
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook.startswith("https://discord.com/api/webhooks/"):
        return {"delivery": "unavailable", "execute_one_action_succeeded": False, "attempts": attempts}
    # Incoming webhooks cannot implement application interaction buttons. Give the authenticated
    # server review URL as the fallback; do not imply that webhook delivery closes Discord ingress.
    fallback = dict(payload)
    fallback.pop("components")
    fallback["content"] += "\nReview in the authenticated fleet UI: " + os.getenv("HB_PUBLIC_URL", "http://127.0.0.1:8765").rstrip("/") + "/fleet.html"
    request = Request(webhook, data=json.dumps(fallback).encode(), headers={
        "Content-Type": "application/json", "User-Agent": "HaulageBrain/chain-simulation"}, method="POST")
    try:
        with opener(request, timeout=20) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError("webhook rejected delivery")
        return {"delivery": "webhook_fallback", "execute_one_action_succeeded": False, "attempts": attempts}
    except Exception as exc:
        return {"delivery": "failed", "execute_one_action_succeeded": False,
                "attempts": attempts, "error_type": type(exc).__name__}


def verify_interaction(body, signature, timestamp, public_key):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise ValueError("stale interaction")
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(signature), timestamp.encode() + body)
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ValueError("invalid Discord signature") from exc
