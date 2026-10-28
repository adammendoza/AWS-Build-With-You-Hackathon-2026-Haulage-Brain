#!/usr/bin/env python3
"""Build the GitHub Pages demo from the production UI assets."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from load_quoting_swarm.web import ASSET_DIR, LoadboardState  # noqa: E402


EXPECTED_FIELDS = (
    "billed_minutes",
    "base",
    "fuel",
    "city",
    "total",
    "minimum_applied",
    "status",
)


def validate_quotes(
    payload: dict[str, Any], expected: dict[str, dict[str, Any]]
) -> None:
    actual = {str(item["load_id"]): item["quote_analysis"] for item in payload["loads"]}
    problems: list[str] = []
    for load_id, expected_quote in expected.items():
        quote = actual.get(load_id)
        if quote is None:
            problems.append(f"{load_id}: missing load")
            continue
        changed = [
            field
            for field in EXPECTED_FIELDS
            if quote.get(field) != expected_quote.get(field)
        ]
        expected_recommendation = {
            "accept": "APPROVE",
            "reject": "REPRICE",
            "needs_human": "REVIEW",
        }.get(expected_quote.get("decision"))
        if expected_recommendation != quote.get("recommendation"):
            changed.append("recommendation")
        if changed:
            problems.append(f"{load_id}: changed {', '.join(changed)}")
    extra = sorted(set(actual) - set(expected))
    if extra:
        problems.append(f"unexpected load IDs: {', '.join(extra)}")
    if problems:
        raise SystemExit("Expected quote validation failed:\n- " + "\n- ".join(problems))


def build(output: Path) -> None:
    loads_path = ROOT / "data" / "loads_v2.json"
    expected_path = ROOT / "data" / "expected_quotes_v2.json"
    demo_run_path = ROOT / "data" / "demo_run.json"
    state = LoadboardState(loads_path, output / ".unused-ledger.jsonl")
    payload = state.payload()
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    demo_run = json.loads(demo_run_path.read_text(encoding="utf-8"))
    validate_quotes(payload, expected)
    if demo_run.get("status") != "COMPLETED" or not demo_run.get("load_id"):
        raise SystemExit("recorded API run must be completed and identify its load")
    payload["deployment"] = {
        "mode": "static-demo",
        "decision_store": "browser localStorage only",
        "recorded_run_load_id": str(demo_run["load_id"]),
    }

    (output / "api").mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "app.css", "app.js"):
        shutil.copy2(ASSET_DIR / name, output / name)
    (output / "api" / "loads").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    shutil.copy2(demo_run_path, output / "api" / "demo-run")
    (output / ".nojekyll").touch()
    print(
        f"Built Haulage Brain Pages site with {len(payload['loads'])} validated loads "
        f"at {output}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    build(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
