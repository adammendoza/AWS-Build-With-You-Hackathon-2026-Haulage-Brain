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
        },
        events=[
            {
                "type": "crewai.ingest.completed",
                "data": {"source_count": 89, "selected_count": 1},
            },
            {
                "type": "crewai.route.completed",
                "data": {"route_counts": {"luton:furniture": 1}},
            },
            {
                "type": "you.grounding.completed",
                "data": {
                    "diesel_price_ppl": 199.22,
                    "ulez_charge_gbp": 0,
                    "citations": [
                        {"title": "Fuel source", "url": "https://example.com/fuel"}
                    ],
                },
            },
            {
                "type": "tools.assessment.completed",
                "data": {
                    "offered_rate_gbp": 400,
                    "estimated_total_cost_gbp": 410,
                    "target_quote_gbp": 450,
                    "live_quote_delta_gbp": 25,
                },
            },
            *[
                {
                    "type": "parasail.specialist.completed",
                    "data": {
                        "role": role,
                        "summary": f"{role} evidence checked",
                        "confidence": 0.8,
                    },
                }
                for role in ("pricing", "compliance", "fleet-fit")
            ],
            {
                "type": "parasail.supervisor.completed",
                "data": {"recommendation": "REVIEW"},
            },
            {
                "type": "safety.gate.completed",
                "data": {
                    "final_recommendation": "REPRICE",
                    "rationale": "The deterministic gate requires a higher rate.",
                },
            },
        ],
        run_summary={
            "elapsed_seconds": 12.5,
            "inference_usage": {"requests": 4},
        },
    )

    body = json.loads(captured["request"].data)
    assert result == {"status_code": 204, "delivery": "venue_webhook_fallback"}
    assert "Q-123" in body["content"]
    assert "https://haulage.example/?load=123" in body["embeds"][0]["fields"][5]["value"]
    assert len(body["embeds"][0]["fields"]) == 6
    assert "You.com" in body["embeds"][0]["fields"][1]["name"]
    assert "Parasail" in body["embeds"][0]["fields"][3]["name"]
    assert "4 Parasail calls" in body["embeds"][0]["footer"]["text"]
    assert body["allowed_mentions"] == {"parse": []}
    assert captured["timeout"] == 15
    assert captured["request"].get_header("User-agent").startswith("DiscordBot ")


def test_webhook_rejects_non_discord_url() -> None:
    with pytest.raises(DiscordWebhookError, match="missing or invalid"):
        DiscordWebhookPublisher("https://example.com/not-a-webhook")
