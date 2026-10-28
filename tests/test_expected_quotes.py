import json
from pathlib import Path

from load_quoting_swarm.web import LoadboardState
from scripts.build_pages import validate_quotes


ROOT = Path(__file__).resolve().parents[1]


def test_all_quotes_match_supplied_expected_fixture(tmp_path: Path) -> None:
    payload = LoadboardState(
        ROOT / "data/loads_v2.json", tmp_path / "ledger.jsonl"
    ).payload()
    expected = json.loads(
        (ROOT / "data/expected_quotes_v2.json").read_text(encoding="utf-8")
    )

    validate_quotes(payload, expected)


def test_recorded_live_run_is_complete_and_sanitized() -> None:
    path = ROOT / "data/demo_run.json"
    text = path.read_text(encoding="utf-8")
    run = json.loads(text)

    assert run["mode"] == "recorded-live"
    assert run["status"] == "COMPLETED"
    assert run["load_id"] == "90857138"
    assert {event["type"] for event in run["events"]} >= {
        "crewai.route.completed",
        "you.grounding.completed",
        "parasail.specialist.completed",
        "parasail.supervisor.completed",
        "safety.gate.completed",
    }
    assert "ydc-sk-" not in text
    assert "psk-hackathon" not in text
