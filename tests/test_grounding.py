import json

import pytest

from load_quoting_swarm.grounding import (
    GroundingError,
    YouSearchGrounding,
    _extract_diesel_price,
    _extract_gbp_charge,
)


def test_extracts_diesel_price_from_you_result_shape() -> None:
    payload = {
        "results": {
            "web": [
                {
                    "title": "Fuel watch",
                    "snippets": ["The latest diesel price is 143.72 pence per litre."],
                }
            ]
        }
    }

    assert _extract_diesel_price(payload) == 143.72


def test_refuses_to_invent_missing_diesel_price() -> None:
    with pytest.raises(GroundingError, match="parseable"):
        _extract_diesel_price({"results": [{"snippet": "No numeric value here"}]})


def test_extracts_restriction_charge() -> None:
    assert _extract_gbp_charge({"snippet": "The daily charge is £12.50."}) == 12.5


def test_you_search_uses_current_highlights_request_shape(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"results":{"web":[]}}'

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("load_quoting_swarm.grounding.urlopen", fake_urlopen)

    YouSearchGrounding(api_key="test-key")._search("current UK diesel price")

    assert captured["body"]["country"] == "GB"
    assert captured["body"]["extraction"] == {
        "extraction_mode": "highlights"
    }
