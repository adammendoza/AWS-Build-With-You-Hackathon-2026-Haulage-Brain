import json
from pathlib import Path

import pytest

from load_quoting_swarm.ledger import LedgerError
from load_quoting_swarm.web import LoadboardState


ROOT = Path(__file__).resolve().parents[1]


def test_updated_fixture_and_summary(tmp_path: Path) -> None:
    state = LoadboardState(
        ROOT / "data/loads_v2.json", tmp_path / "booking-ledger.jsonl"
    )

    payload = state.payload()

    assert payload["summary"]["loads"] == 89
    assert payload["summary"]["available"] == 89
    assert len(payload["loads"]) == 89
    assert all("quote_analysis" in item for item in payload["loads"])


def test_ui_approval_writes_booking_ledger(tmp_path: Path) -> None:
    state = LoadboardState(
        ROOT / "data/loads_v2.json", tmp_path / "booking-ledger.jsonl"
    )
    available = next(
        item for item in state.raw_loads() if item["status"] == "Available"
    )

    event = state.decide(
        {"load_id": available["load_id"], "decision": "APPROVE", "manager": "Adam"}
    )

    assert event["status"] == "BOOKED"
    assert event["manager"] == "Adam"


def test_ui_rejects_decision_for_non_available_load(tmp_path: Path) -> None:
    source = LoadboardState(
        ROOT / "data/loads_v2.json", tmp_path / "booking-ledger.jsonl"
    )
    loads = source.raw_loads()
    loads[0]["status"] = "Delivered"
    fixture = tmp_path / "loads.json"
    fixture.write_text(json.dumps(loads), encoding="utf-8")
    state = LoadboardState(fixture, tmp_path / "booking-ledger.jsonl")

    with pytest.raises(LedgerError, match="only Available"):
        state.decide(
            {"load_id": loads[0]["load_id"], "decision": "APPROVE", "manager": "Adam"}
        )


@pytest.mark.parametrize("manager", ["", "   ", None])
def test_ui_blank_manager_uses_default(tmp_path: Path, manager: str | None) -> None:
    state = LoadboardState(
        ROOT / "data/loads_v2.json", tmp_path / "booking-ledger.jsonl"
    )
    load = state.raw_loads()[0]

    event = state.decide(
        {"load_id": load["load_id"], "decision": "APPROVE", "manager": manager}
    )

    assert event["manager"] == "Fleet Manager"


def test_theme_assets_are_served_locally_and_in_pages(tmp_path: Path) -> None:
    """An HTML-referenced asset must work in both deployments, including binary MIME."""
    from html.parser import HTMLParser
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.request import urlopen

    from load_quoting_swarm.web import make_handler
    from scripts.build_pages import build

    class AssetReferences(HTMLParser):
        def __init__(self):
            super().__init__()
            self.paths = []

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if tag in {"script", "img", "link"}:
                path = attributes.get("src") or attributes.get("href")
                if path:
                    self.paths.append(path.split("?")[0])

    output = tmp_path / "pages"
    build(output)
    references = AssetReferences()
    references.feed((output / "index.html").read_text())
    state = LoadboardState(ROOT / "data/loads_v2.json", tmp_path / "ledger.jsonl")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        for path in references.paths:
            with urlopen(f"http://127.0.0.1:{server.server_port}/{path}") as response:
                body = response.read()
                assert response.status == 200
                assert body == (output / path).read_bytes()
                if path.endswith(".png"):
                    assert response.headers["Content-Type"] == "image/png"
                    assert body.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
