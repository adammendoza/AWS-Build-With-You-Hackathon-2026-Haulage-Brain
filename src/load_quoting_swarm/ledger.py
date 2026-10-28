from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import QuoteDecision


class LedgerError(RuntimeError):
    pass


class BookingLedger:
    """Append-only ledger. QUOTED can become BOOKED only through explicit approval."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _append(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, sort_keys=True) + "\n"
        with self.path.open("a", encoding="utf-8") as stream:
            try:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            except ImportError:
                pass
            stream.write(line)
            stream.flush()
            try:
                import os

                os.fsync(stream.fileno())
            finally:
                try:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                except ImportError:
                    pass

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def state(self) -> dict[str, dict[str, Any]]:
        state: dict[str, dict[str, Any]] = {}
        for event in self.events():
            quote_id = event["quote_id"]
            current = state.setdefault(quote_id, {})
            current.update(event)
        return state

    def record_quote(self, decision: QuoteDecision) -> None:
        self.record_quote_summary(
            quote_id=decision.quote_id,
            load_id=decision.load_id,
            recommendation=decision.recommendation,
            proposed_quote_gbp=decision.proposed_quote_gbp,
        )

    def record_quote_summary(
        self,
        *,
        quote_id: str,
        load_id: str,
        recommendation: str,
        proposed_quote_gbp: float,
    ) -> None:
        if quote_id in self.state():
            raise LedgerError(f"quote already exists: {quote_id}")
        self._append(
            {
                "event": "QUOTED",
                "quote_id": quote_id,
                "load_id": load_id,
                "status": "PENDING",
                "recommendation": recommendation,
                "proposed_quote_gbp": proposed_quote_gbp,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def decide(self, quote_id: str, *, decision: str, manager: str) -> dict[str, Any]:
        if not manager.strip():
            raise LedgerError("manager identity is required")
        current = self.state().get(quote_id)
        if current is None:
            raise LedgerError(f"unknown quote: {quote_id}")
        if current.get("status") != "PENDING":
            raise LedgerError(f"quote is already decided: {quote_id}")
        normalized = decision.upper()
        if normalized not in {"APPROVE", "PASS"}:
            raise LedgerError("decision must be APPROVE or PASS")
        event = {
            "event": "HUMAN_DECISION",
            "quote_id": quote_id,
            "load_id": current["load_id"],
            "status": "BOOKED" if normalized == "APPROVE" else "PASSED",
            "human_decision": normalized,
            "manager": manager.strip(),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self._append(event)
        return event
