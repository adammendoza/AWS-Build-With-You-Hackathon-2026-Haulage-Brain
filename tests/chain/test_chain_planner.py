from pathlib import Path
import json, copy, os
from datetime import datetime
import pytest
from load_quoting_swarm.chain.chain_planner import plan_day, hours_rules_apply, evaluate, State, parse, road_miles

HERE = str(Path(__file__).resolve().parents[2] / "data" / "chain")
SCN = json.load(open(os.path.join(HERE, "chain_scenario_v1.json")))

@pytest.fixture
def plan(): return plan_day(copy.deepcopy(SCN))

def opt(dec, load_id): return next(o for o in dec["options"] if o["load_id"] == load_id)
def by_to(dec, town): return next(o for o in dec["options"] if o["to"].upper().startswith(town.upper()))

def test_chain_has_three_loads_and_ends_home_in_time(plan):
    s = plan["summary"]
    assert len(s["loads"]) == 3
    assert s["home_at"] <= SCN["config"]["home_by"]
    assert plan["decisions"][-1]["action"] == "AUTO_BOOK"

def test_daily_driving_never_exceeds_cap(plan):
    assert plan["summary"]["total_drive_h"] <= SCN["config"]["max_daily_driving_h"]

def test_break_inserted_before_4_5_hours_continuous_driving(plan):
    assert plan["summary"]["breaks"] == 1
    assert plan["summary"]["max_continuous_driving_h"] <= 4.5 + 1e-6

def test_job2_is_standard_mode_and_picks_best_legal_load(plan):
    d = plan["decisions"][0]
    assert d["mode"] == "STANDARD" and d["free_at"] < "15:00"
    assert d["action"] == "AUTO_BOOK" and d["chosen"] == 91000128          # Birmingham -> Nottingham

def test_job2_rejects_high_paying_loads_that_break_hours_rules(plan):
    d = plan["decisions"][0]
    for town in ("LEEDS", "MANCHESTER"):
        o = by_to(d, town)
        assert not o["feasible"] and any(r.startswith("OUT_OF_HOURS") for r in o["reasons"])
    assert by_to(d, "LEEDS")["rate"] == 430 and by_to(d, "LEEDS")["net_load_gbp"] > by_to(d, "NOTTINGHAM")["net_load_gbp"]  # tempting but illegal

def test_job2_other_rejection_reasons(plan):
    d = plan["decisions"][0]
    assert any(r.startswith("WINDOW_MISSED") for r in by_to(d, "DERBY")["reasons"])
    assert "VEHICLE_MISMATCH" in by_to(d, "LEICESTER")["reasons"]
    assert any(r.startswith("BELOW_MARGIN_FLOOR") for r in by_to(d, "READING")["reasons"])
    assert any(r.startswith("DEADHEAD_TOO_FAR") for o in d["options"] for r in o["reasons"])

def test_job3_switches_to_homeward_mode_after_3pm(plan):
    d = plan["decisions"][1]
    assert d["free_at"] >= "15:00" and d["mode"] == "HOMEWARD" and d["ranked_by"] == "net_to_home_gbp"
    assert d["chosen"] == 91000205                                          # Nottingham -> Dartford at the FleetConfig speed

def test_job3_rejections(plan):
    d = plan["decisions"][1]
    assert "MOVES_AWAY_FROM_HOME" in by_to(d, "SHEFFIELD")["reasons"]
    assert by_to(d, "DARTFORD")["feasible"]  # FleetConfig uses 40mph; now within 9h
    assert any(r.startswith("OUT_OF_HOURS") for r in by_to(d, "SHEFFIELD")["reasons"])
    assert any(r.startswith("WAIT_TOO_LONG") for r in opt(d, 91000212)["reasons"])
    assert "VEHICLE_MISMATCH" in opt(d, 91000219)["reasons"]

def test_empty_return_comparison(plan):
    d = plan["decisions"][1]
    e = d["empty_return"]
    assert e["feasible"] and e["net_gbp"] < 0
    assert d["uplift_vs_empty_gbp"] == pytest.approx(opt(d, d["chosen"])["net_to_home_gbp"] - e["net_gbp"], abs=0.01)
    low = by_to(d, "NORTHAMPTON")            # low-paying load toward London
    assert not low["feasible"] and any(r.startswith("BELOW_MARGIN_FLOOR") for r in low["reasons"])  # paid service/waiting time now included

def test_hours_rules_only_for_vehicles_over_3_5t():
    cfg = SCN["config"]
    assert hours_rules_apply("18t Curtain Side, Tail Lift", cfg) and hours_rules_apply("7.5t Box, Tail Lift", cfg) and hours_rules_apply("Artic 44t Flatbed", cfg)
    assert not hours_rules_apply("Luton, Tail Lift", cfg) and not hours_rules_apply("LWB up to 4m", cfg)

def test_van_driver_is_not_capped_by_hgv_hours():
    scn = copy.deepcopy(SCN); scn["driver"]["vehicle"] = "Luton, Tail Lift"
    leeds = copy.deepcopy(next(l for l in scn["candidate_pools"]["after_job_1"] if l["to"]["town"] == "LEEDS")); leeds["vehicle_requested"] = "Luton, Tail Lift"
    st = State(parse("2026-10-29T11:06"), (52.47, -1.88))
    res = evaluate(st, leeds, scn, homeward=False)
    assert not any(r.startswith("OUT_OF_HOURS") for r in res["reasons"])

def test_no_legal_option_escalates_to_human():
    scn = copy.deepcopy(SCN); scn["config"]["home_by"] = "14:00"      # impossible: even driving straight home from Birmingham arrives 15:04
    out = plan_day(scn)
    assert out["decisions"][-1]["action"] == "NEEDS_HUMAN" and out["decisions"][-1]["chosen"] is None

def test_homeward_only_applies_from_cutoff():
    scn = copy.deepcopy(SCN); scn["config"]["homeward_after"] = "23:00"
    out = plan_day(scn)
    assert out["decisions"][1]["mode"] == "STANDARD"

def test_planner_is_deterministic_and_does_not_mutate_input():
    a = copy.deepcopy(SCN); first = json.dumps(plan_day(a), sort_keys=True, default=str)
    assert a == SCN and first == json.dumps(plan_day(copy.deepcopy(SCN)), sort_keys=True, default=str)

def test_expected_plan_file_matches_planner(plan):
    exp = json.load(open(os.path.join(HERE, "expected_chain_plan.json")))
    assert exp["summary"] == plan["summary"]
    assert [d["chosen"] for d in exp["decisions"]] == [d["chosen"] for d in plan["decisions"]]
