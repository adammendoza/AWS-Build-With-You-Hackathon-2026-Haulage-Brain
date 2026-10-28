import json

import pytest

from load_quoting_swarm.discord_webhook import (
    DiscordWebhookError,
    DiscordWebhookPublisher,
)


class _Response:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_webhook_publishes_quote_without_mentions(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setenv("PUBLIC_APP_URL", "https://haulage.example")
    monkeypatch.setattr(
        "load_quoting_swarm.discord_webhook.urlopen", fake_urlopen
    )
    publisher = DiscordWebhookPublisher(
        "https://discord.com/api/webhooks/example/token"
    )

    result = publisher.publish(
        {
            "quote_id": "Q-123",
            "load_id": "123",
            "recommendation": "REPRICE",
            "proposed_quote_gbp": 450,
            "rationale": "The offered rate is below the required margin.",
            "pricing": {"offered_margin_pct": -2.5},
            "fleet_fit": {"selected_vehicle_id": "LUTON-01"},
        }
    )

    body = json.loads(captured["request"].data)
    assert result == {"status_code": 204, "delivery": "venue_webhook_fallback"}
    assert "Q-123" in body["content"]
    assert "https://haulage.example/?load=123" in body["content"]
    assert body["allowed_mentions"] == {"parse": []}
    assert captured["timeout"] == 15
    assert captured["request"].get_header("User-agent").startswith("DiscordBot ")


def test_webhook_rejects_non_discord_url() -> None:
    with pytest.raises(DiscordWebhookError, match="missing or invalid"):
        DiscordWebhookPublisher("https://example.com/not-a-webhook")
