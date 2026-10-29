from pathlib import Path
"""Invariant tests for the fleet simulation. Run from this folder:  python -m pytest -q
Repo-compat tests run only when the haulage-brain package is importable (pip install -e . in the repo)."""
import json, os, sys, time
from collections import Counter
import pytest
HERE = str(Path(__file__).resolve().parents[2] / "data" / "fleet")

from load_quoting_swarm.chain import fleet_planner as P
from load_quoting_swarm.chain.chain_planner import road_miles, parse

FLEET = json.load(open(os.path.join(HERE, "fleet_100_v1.json")))
BOARD = {l["load_id"]: l for l in FLEET["board"]}
CFG = P.base_config()

@pytest.fixture(scope="module")
def res(): return P.run(FLEET)

def test_runs_fast_and_is_deterministic(res):
    t = time.time(); again = P.run(FLEET)
    assert time.time() - t < 10
    assert json.dumps(res, sort_keys=True) == json.dumps(again, sort_keys=True)

def test_matches_stored_results_file(res):
    stored = json.load(open(os.path.join(HERE, "fleet_results.json")))
    assert stored["kpis"] == res["kpis"] and stored["rejection_counts"] == res["rejection_counts"]

def test_shape_100_trucks_30_dispatchers(res):
    assert len(res["trucks"]) == 100 and res["dispatchers"]["count"] == 30
    assert Counter(t["dispatcher_id"] for t in res["trucks"]).keys() == set(range(1, 31))
    assert max(Counter(t["dispatcher_id"] for t in res["trucks"]).values()) <= 4
    assert sum(t["hgv"] for t in res["trucks"]) == 70

def test_no_load_is_booked_twice(res):
    ids = [l["load_id"] for t in res["trucks"] for l in t["loads"]]
    assert len(ids) == len(set(ids))

def test_chained_loads_match_vehicle_and_window(res):
    for t in res["trucks"]:
        for l in t["loads"]:
            if l["role"] != "chained": continue
            b = BOARD[l["load_id"]]
            assert b["vehicle_requested"] == t["vehicle"]
            start = next(e["start"] for e in t["events"] if e["type"] == "load" and e["load_id"] == l["load_id"])
            assert start <= b["pickup"]["end"][11:16]            # loading began before the pickup window closed

def test_hgv_hours_rules_never_broken(res):
    for t in res["trucks"]:
        if t["hgv"] and t["status"] == "HOME":
            assert t["summary"]["drive_h"] <= CFG["max_daily_driving_h"] + 1e-6, t["truck_id"]
        if t["hgv"]:
            assert t["summary"]["max_continuous_h"] <= CFG["break_after_h"] + 1e-6, t["truck_id"]

def test_vans_are_not_capped_by_hgv_rules(res):
    assert all(not t["hgv"] for t in res["trucks"] if "van" in t["vehicle"].lower() or t["vehicle"] in ("LWB up to 4m", "Luton, Tail Lift"))

def test_everyone_not_escalated_is_home_by_deadline(res):
    for t in res["trucks"]:
        if t["status"] == "HOME": assert t["home_at"] <= CFG["home_by"], t["truck_id"]
        else: assert t["home_at"] is None and t["decisions"][-1]["action"] == "NEEDS_HUMAN"

def test_homeward_mode_only_after_cutoff_and_moves_toward_home(res):
    for tr in res["trucks"]:
        home = (tr["home"]["lat"], tr["home"]["lng"])
        def drop_of(load_id):
            if load_id == tr["loads"][0]["load_id"]:
                j = next(x for x in FLEET["trucks"] if x["truck_id"] == tr["truck_id"])["first_job"]; return (j["to"]["lat"], j["to"]["lng"])
            b = BOARD[load_id]; return (b["to"]["lat"], b["to"]["lng"])
        for k, d in enumerate(tr["decisions"]):
            assert (d["free_at"] >= CFG["homeward_after"]) == (d["mode"] == "HOMEWARD")
            if d["mode"] == "HOMEWARD" and d["chosen"]:
                here = drop_of(tr["loads"][k]["load_id"]); new = drop_of(d["chosen"])
                assert road_miles(new, home) <= road_miles(here, home) - CFG["min_progress_miles"] + 1e-6, (tr["truck_id"], d["chosen"])

def test_breaks_present_when_needed(res):
    for t in res["trucks"]:
        if t["hgv"] and t["summary"]["drive_h"] > CFG["break_after_h"] + 0.01:
            assert t["summary"]["breaks"] >= 1, t["truck_id"]

def test_totals_and_kpis_are_consistent(res):
    k, T = res["kpis"], res["trucks"]
    assert k["trucks_home_on_time"] + k["trucks_escalated"] == 100
    assert k["loads_booked"] == sum(len(t["loads"]) for t in T)
    assert k["decisions_total"] == sum(len(t["decisions"]) for t in T) == k["decisions_auto"] + k["decisions_escalated"]
    assert k["profit_planned_gbp"] == pytest.approx(sum(t["summary"]["profit_gbp"] for t in T), abs=0.05)
    assert k["empty_miles_planned"] == pytest.approx(sum(t["summary"]["empty_miles"] for t in T), abs=0.2)
    assert k["share_auto"] == pytest.approx(k["decisions_auto"] / k["decisions_total"], abs=1e-4)

def test_reason_codes_are_only_the_allowed_set(res):
    assert set(res["rejection_counts"]) <= P.ALLOWED_CODES
    for t in res["trucks"]:
        for d in t["decisions"]:
            for o in d["options"]:
                assert all(P.code(r) in P.ALLOWED_CODES for r in o["reasons"]) and o["feasible"] == (not o["reasons"])

def test_exceptions_are_the_only_human_touchpoints(res):
    ex = {(e["truck_id"], e["free_at"]) for e in res["exceptions"]}
    flagged = {(t["truck_id"], d["free_at"]) for t in res["trucks"] for d in t["decisions"] if d.get("exception_reason")}
    assert ex == flagged and {e["reason"] for e in res["exceptions"]} <= {"NEEDS_HUMAN", "THIN_MARGIN", "OVER_HOURS_OPPORTUNITY"}

def test_agent_plan_beats_first_job_then_drive_home_baseline(res):
    k = res["kpis"]
    assert k["profit_planned_gbp"] > k["profit_baseline_gbp"] and k["empty_miles_planned"] < k["empty_miles_baseline"]

def test_event_blocks_are_ordered_and_non_overlapping(res):
    for t in res["trucks"]:
        prev = "00:00"
        for e in t["events"]:
            assert e["start"] >= prev and e["end"] >= e["start"], (t["truck_id"], e); prev = e["end"]

# ---- compatibility with the existing repo (skipped if the package is not installed) ----
def test_every_load_parses_with_the_repo_model():
    m = pytest.importorskip("load_quoting_swarm.models")
    loads = FLEET["board"] + [t["first_job"] for t in FLEET["trucks"]]
    assert all(m.FreightLoad.from_raw(l).load_id for l in loads)

def test_fleet_config_loads_with_the_repo_loader():
    c = pytest.importorskip("load_quoting_swarm.config")
    cfg = c.load_fleet_config(os.path.join(HERE, "..", "..", "config", "fleet.chain.demo.json"))
    assert len(cfg.vehicles) == 100 and cfg.minimum_margin_pct == 8
    mapping = json.load(open(os.path.join(HERE, "..", "..", "config", "fleet.chain.demo.json")))["board_vehicle_map"]
    assert {mapping[t["vehicle"]].casefold() for t in FLEET["trucks"]} <= set(cfg.vehicle_profiles)
