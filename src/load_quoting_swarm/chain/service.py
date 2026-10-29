"""Persistent simulation snapshot and exception decisions, using the existing ledger API."""
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from datetime import datetime, timezone
from ..pricing import quote
from ..ledger import BookingLedger
from .economics import ROOT, DEFAULT_CONFIG
from .fleet_planner import run

LABEL = "Policy auto-booking (simulation)"


def enabled():
    return os.getenv("HB_ENABLE_CHAIN") == "1"


class ChainService:
    def __init__(self, *, storage=Path("var/chain"), fleet_path=ROOT / "data/fleet/fleet_100_v1.json",
                 config_path=DEFAULT_CONFIG, diesel_ppl=None, market=None):
        self.storage = Path(storage)
        self.storage.mkdir(parents=True, exist_ok=True)
        self.db = self.storage / "chain.sqlite3"
        self.ledger = BookingLedger(self.storage / "booking-ledger.jsonl")
        self.fleet = json.loads(Path(fleet_path).read_text())
        self.config_path, self.diesel_ppl, self.market = config_path, diesel_ppl, market
        self.run_key = self.fleet["meta"]["day"] + ":" + self.fleet["meta"]["scenario"]
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, result TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS resolutions (id TEXT PRIMARY KEY, action TEXT, manager TEXT, event TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS bookings (day TEXT, load TEXT, truck TEXT, PRIMARY KEY(day, load))")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.db, timeout=30)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _snapshot(self, db):
        row = db.execute("SELECT result FROM snapshots WHERE id=?", (self.run_key,)).fetchone()
        if row:
            return json.loads(row[0])
        result = run(self.fleet, fleet_config_path=self.config_path, diesel_ppl=self.diesel_ppl)
        result["meta"].update(policy_label=LABEL, bookings_are_projected=True,
                              market=self.market or {"source": "synthetic-demo"})
        for i, item in enumerate(result["exceptions"]):
            item["exception_id"] = hashlib.sha256(f"{self.run_key}:{i}".encode()).hexdigest()[:20]
            truck = next(t for t in result["trucks"] if t["truck_id"] == item["truck_id"])
            decision = next(d for d in truck["decisions"] if d["free_at"] == item["free_at"])
            item["chosen"] = decision["chosen"]
        db.execute("INSERT INTO snapshots VALUES (?,?)", (self.run_key, json.dumps(result)))
        return result

    def payload(self):
        with self.connection() as db:
            result = self._snapshot(db)
            resolved = {row[0]: json.loads(row[1]) for row in db.execute("SELECT id,event FROM resolutions")}
            for item in result["exceptions"]:
                item["resolution"] = resolved.get(item["exception_id"])
            result["ledger"] = self.ledger.state()
            return result

    def _book(self, db, load_id, truck_id, manager):
        day = self.fleet["meta"]["day"]
        quote_id = f"CHAIN-{day}-{load_id}"
        current = self.ledger.state().get(quote_id)
        if current and current["status"] != "PENDING":
            return current
        if not current:
            raw = next(l for l in self.fleet["board"] if l["load_id"] == load_id)
            self.ledger.record_quote_summary(quote_id=quote_id, load_id=str(load_id),
                                            recommendation="APPROVE", proposed_quote_gbp=max(raw["agreed_rate_gbp"], quote(
                                                raw["distance_miles"], raw["journey_minutes_est"],
                                                raw["from_"].get("postcode", ""), raw["to"].get("postcode", ""),
                                                datetime.fromisoformat(raw["pickup"]["start"]))["total"]))
        owner = db.execute("SELECT truck FROM bookings WHERE day=? AND load=?", (day, str(load_id))).fetchone()
        if owner and owner[0] != truck_id:
            raise ValueError("load already claimed by another truck")
        db.execute("INSERT OR IGNORE INTO bookings VALUES (?,?,?)", (day, str(load_id), truck_id))
        return self.ledger.decide(quote_id, decision="APPROVE", manager=manager)

    def commit(self):
        if not enabled():
            raise PermissionError("HB_ENABLE_CHAIN=1 is required")
        with self.connection() as db:
            result = self._snapshot(db)
            events = []
            for truck in result["trucks"]:
                for decision in truck["decisions"]:
                    # Later simulated legs depend on resolving any earlier exception.
                    if decision.get("exception_reason"):
                        item = next(e for e in result["exceptions"] if e["truck_id"] == truck["truck_id"] and e["free_at"] == decision["free_at"])
                        resolved = db.execute("SELECT action FROM resolutions WHERE id=?", (item["exception_id"],)).fetchone()
                        if not resolved or resolved[0] != "APPROVE":
                            break
                        continue
                    if decision["action"] == "AUTO_BOOK":
                        events.append(self._book(db, decision["chosen"], truck["truck_id"], "policy:auto-book-v1"))
            return {"label": LABEL, "events": events}

    def resolve(self, exception_id, action, manager):
        if not enabled():
            raise PermissionError("HB_ENABLE_CHAIN=1 is required")
        if action not in {"APPROVE", "ESCALATE"} or not manager.strip() or manager.startswith("policy:"):
            raise ValueError("explicit human identity and APPROVE or ESCALATE required")
        with self.connection() as db:
            prior = db.execute("SELECT event FROM resolutions WHERE id=?", (exception_id,)).fetchone()
            if prior:
                raise ValueError("exception already resolved")
            result = self._snapshot(db)
            item = next((e for e in result["exceptions"] if e["exception_id"] == exception_id), None)
            if item is None:
                raise ValueError("unknown exception")
            truck = next(t for t in result["trucks"] if t["truck_id"] == item["truck_id"])
            decision_index = next(i for i,d in enumerate(truck["decisions"]) if d["free_at"] == item["free_at"])
            for earlier in truck["decisions"][:decision_index]:
                if action == "APPROVE" and earlier.get("exception_reason"):
                    earlier_item = next(e for e in result["exceptions"] if e["truck_id"] == truck["truck_id"] and e["free_at"] == earlier["free_at"])
                    earlier_resolution = db.execute("SELECT action FROM resolutions WHERE id=?", (earlier_item["exception_id"],)).fetchone()
                    if not earlier_resolution or earlier_resolution[0] != "APPROVE":
                        raise ValueError("resolve earlier truck exception before approving later legs")
                if action == "APPROVE" and earlier.get("chosen"):
                    self._book(db, earlier["chosen"], truck["truck_id"], manager)
            event = {"exception_id": exception_id, "action": action, "manager": manager, "status": "ESCALATED", "at": datetime.now(timezone.utc).isoformat()}
            if action == "APPROVE":
                if item["chosen"] is not None:
                    # OVER_HOURS_OPPORTUNITY only acknowledges/books the already selected legal option.
                    event["booking"] = self._book(db, item["chosen"], item["truck_id"], manager)
                    event["status"] = "APPROVED_LEGAL_PLAN"
                else:
                    event["status"] = "ACKNOWLEDGED_NEEDS_MANUAL_DISPATCH"
            db.execute("INSERT INTO resolutions VALUES (?,?,?,?)", (exception_id, action, manager, json.dumps(event)))
            return event
