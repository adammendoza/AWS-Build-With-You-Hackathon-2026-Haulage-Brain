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
