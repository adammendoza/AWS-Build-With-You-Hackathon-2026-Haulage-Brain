"""Fleet simulation: 100 trucks, one shared load board, event-driven allocation. Reference oracle + results writer.
Reuses chain_planner primitives (rules, evaluation, breaks). Deterministic: same input -> same output.
Run: python fleet_planner.py   (writes fleet_results.json next to this file)"""
import heapq, json, math, os, sys
from collections import Counter
from datetime import timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
from .economics import DEFAULT_CONFIG, fleet_economics, validate_fleet
from .chain_planner import (State, add_service, add_wait, drive, evaluate, haversine_miles, hhmm, hours_rules_apply, leg_cost, parse, road_miles)


THIN_MARGIN, OVER_HOURS_VALUE_GBP, OVER_HOURS_MAX_H, PREFILTER_MILES = 0.12, 50.0, 10.0, 60.0
ALLOWED_CODES = {"VEHICLE_MISMATCH", "DEADHEAD_TOO_FAR", "WINDOW_MISSED", "WAIT_TOO_LONG", "BELOW_MARGIN_FLOOR", "OUT_OF_HOURS", "HOME_DEADLINE", "MOVES_AWAY_FROM_HOME", "PAYLOAD_EXCEEDED", "QUOTE_REQUIRES_HUMAN"}

def base_config():
    return json.loads((Path(__file__).resolve().parents[3] / "data/chain/chain_scenario_v1.json").read_text())["config"]

def truck_config(base, vehicle, fleet_config_path=DEFAULT_CONFIG, diesel_ppl=None):
    return fleet_economics(base, vehicle, fleet_config_path, diesel_ppl)

def code(reason): return reason.split(" ")[0]
def hm(dt): return hhmm(dt)

def run(fleet, base=None, *, fleet_config_path=DEFAULT_CONFIG, diesel_ppl=None):
    validate_fleet(fleet)
    base = base or base_config(); day = fleet["meta"]["day"]; cutoff = parse(f"{day}T{base['homeward_after']}"); deadline = parse(f"{day}T{base['home_by']}")
    board = {l["load_id"]: l for l in fleet["board"]}; claimed = {t["first_job"]["load_id"]: t["truck_id"] for t in fleet["trucks"]}; heap = []; T = []
    for idx, t in enumerate(fleet["trucks"]):
        cfg = truck_config(base, t["vehicle"], fleet_config_path, diesel_ppl); home = (t["home"]["lat"], t["home"]["lng"]); reg = hours_rules_apply(t["vehicle"], cfg)
        scn = dict(config=cfg, driver=dict(vehicle=t["vehicle"], home=dict(coords=list(home)), driver_id=t["driver_id"]), day=day)
        j = t["first_job"]; p = (j["from_"]["lat"], j["from_"]["lng"]); d = (j["to"]["lat"], j["to"]["lng"])
        st = State(parse(f"{day}T{t['leaves_home_at']}"), home)
        drive(st, p, road_miles(home, p), cfg, "home to pickup", reg)
        add_wait(st, parse(j["pickup"]["start"]), event=False)
        add_service(st, "load", j["load_id"], cfg["load_minutes"])
        drive(st, d, road_miles(p, d), cfg, f"loaded to {j['to']['town']}", reg)
        add_service(st, "unload", j["load_id"], cfg["unload_minutes"])
        base_st = st.copy(); drive(base_st, home, road_miles(d, home), cfg, "drive home", reg)
        rec = dict(t=t, cfg=cfg, scn=scn, reg=reg, home=home, st=st, loads=[dict(load_id=j["load_id"], role="first", **{"from": j["from_"]["town"].title(), "to": j["to"]["town"].title()}, rate_gbp=j["agreed_rate_gbp"])],
                   revenue=j["agreed_rate_gbp"], decisions=[], status="HOME", baseline=base_st)
        T.append(rec); heapq.heappush(heap, (st.t, idx))
    exceptions, rej, illegal = [], Counter(), [0]
    while heap:
        _, idx = heapq.heappop(heap); r = T[idx]; st = r["st"]; cfg = r["cfg"]; scn = r["scn"]; stage = len(r["decisions"]) + 1
        if stage > cfg.get("max_chained_loads", 2): continue
        homeward = st.t >= cutoff; key = "net_to_home_gbp" if homeward else "net_load_gbp"
        res = []
        for lid, l in board.items():
            if lid in claimed or parse(l["pickup"]["end"]) < st.t: continue
            if haversine_miles(st.loc, (l["from_"]["lat"], l["from_"]["lng"])) * 1.22 > PREFILTER_MILES: continue
            res.append(evaluate(st, l, scn, homeward))
        for x in res:
            if "VEHICLE_MISMATCH" in x["reasons"]: continue          # not a real option for this truck: do not count
            for c in {code(rs) for rs in x["reasons"]}: rej[c] += 1
            if any(rs.startswith(("OUT_OF_HOURS", "HOME_DEADLINE")) for rs in x["reasons"]): illegal[0] += 1
        ok = [x for x in res if x["feasible"]]
        hm_ = road_miles(st.loc, r["home"]); hh = st.copy(); drive(hh, r["home"], hm_, cfg, "drive home", r["reg"])
        empty = dict(net_gbp=round(-(hm_ * cfg["cost_per_mile_gbp"] + (hh.t - st.t).total_seconds() / 3600 * cfg["driver_cost_per_hour_gbp"]), 2), home_at=hm(hh.t), feasible=(not r["reg"] or hh.drive_h <= cfg["max_daily_driving_h"] + 1e-9) and hh.t <= deadline)
        dec = dict(free_at=hm(st.t), mode="HOMEWARD" if homeward else "STANDARD", action=None, chosen=None, empty_return=empty)
        if ok:
            best = max(ok, key=lambda x: (x[key], -x["load_id"])); claimed[best["load_id"]] = r["t"]["truck_id"]
            dec.update(action="AUTO_BOOK", chosen=best["load_id"]); dec["uplift_vs_empty_gbp"] = round(best["net_to_home_gbp"] - empty["net_gbp"], 2)
            if best["margin"] < THIN_MARGIN:
                dec["exception_reason"] = "THIN_MARGIN"; exceptions.append(dict(truck_id=r["t"]["truck_id"], free_at=dec["free_at"], reason="THIN_MARGIN", detail=f"load {best['load_id']} margin {best['margin']*100:.0f}% (floor 8%, review under 12%)"))
            else:
                for x in res:
                    if (not x["feasible"] and x["reasons"] and all(rs.startswith("OUT_OF_HOURS") for rs in x["reasons"]) and x["total_drive_h"] <= OVER_HOURS_MAX_H and x[key] - best[key] >= OVER_HOURS_VALUE_GBP):
                        dec["exception_reason"] = "OVER_HOURS_OPPORTUNITY"
                        exceptions.append(dict(truck_id=r["t"]["truck_id"], free_at=dec["free_at"], reason="OVER_HOURS_OPPORTUNITY", detail=f"load {x['load_id']} to {x['to']} would add £{x[key]-best[key]:.0f} but needs {x['total_drive_h']}h driving (cap 9h; a 10h day is allowed twice a week, manager decision)")); break
            tempt = [x for x in res if "VEHICLE_MISMATCH" not in x["reasons"] and x["reasons"] and all(rs.startswith(("OUT_OF_HOURS", "HOME_DEADLINE")) for rs in x["reasons"]) and x[key] > best[key]]
            if tempt:
                top = max(tempt, key=lambda x: x[key]); dec["tempting_illegal"] = dict(load_id=top["load_id"], to=top["to"].title(), rate=top["rate"], reasons=top["reasons"], extra_gbp=round(top[key] - best[key], 2))
            r["st"] = best["_state_after"]; ld = board[best["load_id"]]
            r["loads"].append(dict(load_id=best["load_id"], role="chained", **{"from": ld["from_"]["town"].title(), "to": ld["to"]["town"].title()}, rate_gbp=best["rate"])); r["revenue"] += best["rate"]
            heapq.heappush(heap, (r["st"].t, idx))
        elif empty["feasible"]:
            dec.update(action="DRIVE_HOME_EMPTY")
        else:
            dec.update(action="NEEDS_HUMAN", exception_reason="NEEDS_HUMAN"); r["status"] = "ESCALATED"
            exceptions.append(dict(truck_id=r["t"]["truck_id"], free_at=dec["free_at"], reason="NEEDS_HUMAN", detail="no legal load and the driver cannot legally get home on time"))
        shown = sorted([x for x in res if x["feasible"]], key=lambda x: -x[key])[:4] + sorted([x for x in res if not x["feasible"]], key=lambda x: -x["rate"])[:4]
        dec["options"] = [dict(load_id=x["load_id"], to=x["to"].title(), rate=x["rate"], feasible=x["feasible"], reasons=x["reasons"], net_load_gbp=x["net_load_gbp"], net_to_home_gbp=x["net_to_home_gbp"], margin_pct=round(x["margin"] * 100, 1)) for x in shown]
        dec["evaluated"] = len(res); r["decisions"].append(dec)
    out = []
    for r in T:
        t, cfg, st = r["t"], r["cfg"], r["st"]; final = st.copy()
        if r["status"] != "ESCALATED": drive(final, r["home"], road_miles(st.loc, r["home"]), cfg, "drive home", r["reg"])
        drv = [e for e in final.events if e["type"] == "drive"]; cost = sum(e["miles"] * cfg["cost_per_mile_gbp"] for e in drv) + (final.t - parse(f"{day}T{t['leaves_home_at']}")).total_seconds() / 3600 * cfg["driver_cost_per_hour_gbp"]
        empty_mi = sum(e["miles"] for e in drv if e["label"].startswith(("deadhead", "home to pickup", "drive home")))
        b = r["baseline"]; bdrv = [e for e in b.events if e["type"] == "drive"]
        bcost = sum(e["miles"] * cfg["cost_per_mile_gbp"] for e in bdrv) + (b.t - parse(f"{day}T{t['leaves_home_at']}")).total_seconds() / 3600 * cfg["driver_cost_per_hour_gbp"]; bempty = sum(e["miles"] for e in bdrv if e["label"].startswith(("deadhead", "home to pickup", "drive home")))
        out.append(dict(truck_id=t["truck_id"], driver_id=t["driver_id"], dispatcher_id=t["dispatcher_id"], vehicle=t["vehicle"], hgv=r["reg"], home=t["home"], leaves_home_at=t["leaves_home_at"],
            status=r["status"], home_at=None if r["status"] == "ESCALATED" else hm(final.t),
            summary=dict(revenue_gbp=r["revenue"], cost_gbp=round(cost, 2), profit_gbp=round(r["revenue"] - cost, 2), miles=round(sum(e["miles"] for e in drv), 1), empty_miles=round(empty_mi, 1),
                         drive_h=round(final.drive_h, 2), max_continuous_h=round(final.max_continuous_h, 2), breaks=sum(1 for e in final.events if e["type"] == "break")),
            baseline=dict(profit_gbp=round(t["first_job"]["agreed_rate_gbp"] - bcost, 2), empty_miles=round(bempty, 1), home_at=hm(b.t)),
            loads=r["loads"], events=final.blocks, decisions=r["decisions"]))
    return dict(meta=dict(scenario=fleet["meta"]["scenario"], is_sample=False, synthetic=True, day=day, seed=fleet["meta"]["seed"], diesel_ppl=cfg["diesel_price_ppl"], market_source="explicit-input" if diesel_ppl is not None else "synthetic-demo", policy_label="Policy auto-booking (simulation)",
                          assumptions=["Synthetic fleet, board and economics (config/fleet.chain.demo.json). Dispatcher IDs are grouping labels only.",
                                       "Policy auto-booking simulation: a booking is a ledger entry, not a broker booking.", "Hours rules apply to vehicles over 3.5t only; 9h cap, 45 min break after 4.5h."]),
                dispatchers=dict(count=fleet["meta"]["dispatchers"]), trucks=out, exceptions=exceptions, rejection_counts=dict(rej.most_common()), kpis=kpis(out, exceptions, rej, illegal[0]))

def kpis(trucks, exceptions, rej, illegal):
    dec = [d for t in trucks for d in t["decisions"]]; esc = [d for d in dec if d.get("exception_reason")]
    opts = [o for d in dec for o in d["options"]]
    return dict(trucks=len(trucks), trucks_home_on_time=sum(1 for t in trucks if t["status"] == "HOME"), trucks_escalated=sum(1 for t in trucks if t["status"] == "ESCALATED"),
        loads_booked=sum(len(t["loads"]) for t in trucks), decisions_total=len(dec), decisions_auto=len(dec) - len(esc), decisions_escalated=len(esc),
        share_auto=round((len(dec) - len(esc)) / len(dec), 4) if dec else 0.0, illegal_options_blocked=illegal, tempting_illegal_avoided=sum(1 for d in dec if d.get("tempting_illegal")),
        empty_miles_planned=round(sum(t["summary"]["empty_miles"] for t in trucks), 1), empty_miles_baseline=round(sum(t["baseline"]["empty_miles"] for t in trucks), 1),
        profit_planned_gbp=round(sum(t["summary"]["profit_gbp"] for t in trucks), 2), profit_baseline_gbp=round(sum(t["baseline"]["profit_gbp"] for t in trucks), 2),
        avg_hgv_drive_h=round(sum(t["summary"]["drive_h"] for t in trucks if t["hgv"]) / max(1, sum(1 for t in trucks if t["hgv"])), 2),
        illustrative_dispatchers_needed=math.ceil(30 * len(esc) / len(dec)) if dec else 0,
        illustrative_caption="Illustrative: assumes human workload scales with decisions needing a human. Replace with the operator's real workload data.")

if __name__ == "__main__":
    fleet = json.load(open(Path(__file__).resolve().parents[3] / "data/fleet/fleet_100_v1.json"))
    res = run(fleet); json.dump(res, open(Path(__file__).resolve().parents[3] / "data/fleet/fleet_results.json", "w"), indent=1)
    print(json.dumps(res["kpis"], indent=1)); print("rejections:", res["rejection_counts"]); print("exceptions:", Counter(e["reason"] for e in res["exceptions"]))
