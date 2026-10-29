"""Reference planner for the 'driver never idles, then goes home' feature.

One driver, one HGV, one day. Plans a chain of loads (job 1 is already booked), then
brings the driver home to London. Pure functions, no network, no LLM: the agents decide
WHAT to explain; this module decides what is LEGAL and PROFITABLE. Dev team: port or call it.

Assumptions (all in scenario["config"], all synthetic until real fleet data is wired in):
  - Hours rules apply ONLY to vehicles over 3.5t (7.5t / 18t / artic). Vans are exempt here.
  - 9h daily driving cap, 45 min break after 4.5h driving. Loading/unloading is NOT a break.
  - Road miles = straight line x 1.22. HGV average 38 mph. Legs under 8 road miles use 14 mph.
"""
import json, math
from copy import deepcopy
from datetime import datetime, timedelta

from ..pricing import quote
from .economics import DEFAULT_CONFIG, fleet_economics

ROAD_FACTOR = 1.22

def haversine_miles(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    d = 2 * 6371 * math.asin(math.sqrt(math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2))
    return d * 0.621371

def road_miles(a, b):
    return haversine_miles(a, b) * ROAD_FACTOR

def speed_mph(miles, cfg):
    return cfg["urban_speed_mph"] if miles < cfg["urban_leg_miles"] else cfg["hgv_speed_mph"]

def hours_rules_apply(vehicle, cfg):
    return any(k in vehicle.casefold() for k in ("7.5t", "18t", "artic"))

def parse(ts): return datetime.fromisoformat(ts)
def hhmm(dt): return dt.strftime("%H:%M")

class State:
    def __init__(self, t, loc, drive_h=0.0, since_break_h=0.0):
        self.t, self.loc, self.drive_h, self.since_break_h = t, loc, drive_h, since_break_h
        self.max_continuous_h = 0.0
        self.events = []   # compact audit events (unchanged shape)
        self.blocks = []   # UI-ready timeline blocks: {type,start,end,...}
    def copy(self):
        c = State(self.t, self.loc, self.drive_h, self.since_break_h)
        c.max_continuous_h = self.max_continuous_h
        c.events, c.blocks = list(self.events), list(self.blocks)
        return c

def drive(state, to, miles, cfg, label, regulated=True):
    """Advance state by driving `miles`, inserting a 45-min break whenever 4.5h of driving is reached."""
    hours = miles / speed_mph(miles, cfg)
    remaining = hours
    kind = "drive_loaded" if label.startswith("loaded") else "drive_home" if label == "drive home" else "deadhead"
    while remaining > 1e-9:
        if regulated:
            allowed = cfg["break_after_h"] - state.since_break_h
            if allowed <= 1e-9:
                b0 = state.t
                state.events.append(dict(type="break", at=hhmm(state.t), minutes=cfg["break_minutes"]))
                state.t += timedelta(minutes=cfg["break_minutes"]); state.since_break_h = 0.0
                state.blocks.append(dict(type="break", start=hhmm(b0), end=hhmm(state.t)))
                continue
            seg = min(remaining, allowed)
        else:
            seg = remaining
        s0 = state.t
        state.t += timedelta(hours=seg); state.drive_h += seg; state.since_break_h += seg
        state.blocks.append(dict(type=kind, start=hhmm(s0), end=hhmm(state.t), miles=round(miles * seg / hours, 1), label=label))
        remaining -= seg
        state.max_continuous_h = max(state.max_continuous_h, state.since_break_h)
    state.events.append(dict(type="drive", label=label, miles=round(miles, 1), arrive=hhmm(state.t)))
    state.loc = to

def add_wait(state, until, event=True):
    if until <= state.t: return
    mins = (until - state.t).total_seconds() / 60
    if event: state.events.append(dict(type="wait", minutes=round(mins)))
    state.blocks.append(dict(type="wait", start=hhmm(state.t), end=hhmm(until)))
    state.t = until

def add_service(state, kind, load_id, minutes):
    t0 = state.t; state.t += timedelta(minutes=minutes)
    state.events.append(dict(type=kind, load_id=load_id, until=hhmm(state.t)))
    state.blocks.append(dict(type=kind, start=hhmm(t0), end=hhmm(state.t), load_id=load_id))

def leg_cost(miles, cfg):
    hours = miles / speed_mph(miles, cfg)
    return miles * cfg["cost_per_mile_gbp"] + hours * cfg["driver_cost_per_hour_gbp"]

def evaluate(state, load, scn, homeward):
    """Return dict(feasible, reasons[], ...) for taking `load` next from `state`."""
    cfg, home = scn["config"], tuple(scn["driver"]["home"]["coords"])
    veh = scn["driver"]["vehicle"]; regulated = hours_rules_apply(veh, cfg)
    reasons = []
    if load["vehicle_requested"] != veh:
        reasons.append("VEHICLE_MISMATCH")
    s = state.copy()
    pick = (load["from_"]["lat"], load["from_"]["lng"]); drop = (load["to"]["lat"], load["to"]["lng"])
    dh = road_miles(s.loc, pick)
    if dh > cfg["max_deadhead_miles"]: reasons.append(f"DEADHEAD_TOO_FAR ({dh:.0f} mi, max {cfg['max_deadhead_miles']})")
    drive(s, pick, dh, cfg, "deadhead to pickup", regulated)
    w0, w1 = parse(load["pickup"]["start"]), parse(load["pickup"]["end"])
    if s.t > w1: reasons.append(f"WINDOW_MISSED (arrive {hhmm(s.t)}, window closes {hhmm(w1)})")
    elif s.t < w0:
        wait = (w0 - s.t).total_seconds() / 60
        if wait > cfg["max_wait_minutes"]: reasons.append(f"WAIT_TOO_LONG ({wait:.0f} min)")
        add_wait(s, w0)
    add_service(s, "load", load["load_id"], cfg["load_minutes"])
    loaded = road_miles(pick, drop)
    drive(s, drop, loaded, cfg, f"loaded to {load['to']['town']}", regulated)
    add_service(s, "unload", load["load_id"], cfg["unload_minutes"])
    free_t = s.t
    # cost and margin of the load leg itself
    cost_leg = (dh + loaded) * cfg["cost_per_mile_gbp"] + (s.t - state.t).total_seconds() / 3600 * cfg["driver_cost_per_hour_gbp"]
    rate = load["agreed_rate_gbp"]
    formula = quote(float(load["distance_miles"]), int(load["journey_minutes_est"]),
                    load["from_"].get("postcode", ""), load["to"].get("postcode", ""), w0)
    if formula["status"] != "ok": reasons.append("QUOTE_REQUIRES_HUMAN")
    if load.get("weight_kg") is not None and load["weight_kg"] > cfg.get("max_payload_kg", float("inf")):
        reasons.append("PAYLOAD_EXCEEDED")
    margin = (rate - cost_leg) / rate
    if margin < cfg["min_margin"]: reasons.append(f"BELOW_MARGIN_FLOOR ({margin*100:.0f}% < {cfg['min_margin']*100:.0f}%)")
    # can the driver still legally get home today?
    home_miles = road_miles(drop, home)
    h = s.copy(); drive(h, home, home_miles, cfg, "drive home", regulated)
    if regulated and h.drive_h > cfg["max_daily_driving_h"] + 1e-9:
        reasons.append(f"OUT_OF_HOURS (needs {h.drive_h:.1f}h driving to get home, cap {cfg['max_daily_driving_h']}h)")
    deadline = parse(scn["day"] + "T" + cfg["home_by"])
    if h.t > deadline: reasons.append(f"HOME_DEADLINE (home at {hhmm(h.t)}, limit {cfg['home_by']})")
    if homeward and road_miles(drop, home) > road_miles(state.loc, home) - cfg["min_progress_miles"]:
        reasons.append("MOVES_AWAY_FROM_HOME")
    return dict(load_id=load["load_id"], to=load["to"]["town"], rate=rate, feasible=not reasons, reasons=reasons, margin=round(margin, 4),
        quote=formula, net_load_gbp=round(rate - cost_leg, 2), net_to_home_gbp=round(rate - cost_leg - (home_miles * cfg["cost_per_mile_gbp"] + (h.t - s.t).total_seconds() / 3600 * cfg["driver_cost_per_hour_gbp"]), 2),
        free_at=hhmm(free_t), home_at=hhmm(h.t), total_drive_h=round(h.drive_h, 2), _state_after=s)

def plan_day(scn, *, fleet_config_path=DEFAULT_CONFIG, diesel_ppl=None):
    scn = deepcopy(scn)
    scn["config"] = fleet_economics(scn["config"], scn["driver"]["vehicle"], fleet_config_path, diesel_ppl)
    cfg, drv = scn["config"], scn["driver"]
    home = tuple(drv["home"]["coords"]); veh = drv["vehicle"]; regulated = hours_rules_apply(veh, cfg)
    day = scn["day"]; st = State(parse(f"{day}T{drv['leaves_home_at']}"), home)
    out = dict(driver=drv["driver_id"], vehicle=veh, hours_rules_apply=regulated, decisions=[], timeline=None)
    # job 1 is already booked
    j1 = scn["first_job"]; p1 = (j1["from_"]["lat"], j1["from_"]["lng"]); d1 = (j1["to"]["lat"], j1["to"]["lng"])
    drive(st, p1, road_miles(home, p1), cfg, "home to pickup", regulated)
    add_wait(st, parse(j1["pickup"]["start"]), event=False)
    add_service(st, "load", j1["load_id"], cfg["load_minutes"])
    drive(st, d1, road_miles(p1, d1), cfg, f"loaded to {j1['to']['town']}", regulated)
    add_service(st, "unload", j1["load_id"], cfg["unload_minutes"])
    chosen = [j1["load_id"]]; revenue = j1["agreed_rate_gbp"]
    cutoff = parse(f"{day}T{cfg['homeward_after']}")
    for pool_name in ("after_job_1", "after_job_2"):
        homeward = st.t >= cutoff
        results = [evaluate(st, l, scn, homeward) for l in scn["candidate_pools"][pool_name] if l["load_id"] not in chosen]
        ok = [r for r in results if r["feasible"]]
        key = "net_to_home_gbp" if homeward else "net_load_gbp"
        dec = dict(pool=pool_name, free_at=hhmm(st.t), mode="HOMEWARD" if homeward else "STANDARD", ranked_by=key,
                   options=[{k: v for k, v in r.items() if k != "_state_after"} for r in sorted(results, key=lambda r: (not r["feasible"], -r[key]))])
        home_miles = road_miles(st.loc, home); hh = st.copy(); drive(hh, home, home_miles, cfg, "drive home", regulated)
        dec["empty_return"] = dict(miles=round(home_miles, 1), home_at=hhmm(hh.t), total_drive_h=round(hh.drive_h, 2),
                                   net_gbp=round(-(home_miles * cfg["cost_per_mile_gbp"] + (hh.t - st.t).total_seconds() / 3600 * cfg["driver_cost_per_hour_gbp"]), 2), feasible=(not regulated or hh.drive_h <= cfg["max_daily_driving_h"]) and hh.t <= parse(f"{day}T{cfg['home_by']}"))
        if not ok:
            dec["chosen"] = None; dec["action"] = "NEEDS_HUMAN" if not dec["empty_return"]["feasible"] else "DRIVE_HOME_EMPTY"
            out["decisions"].append(dec); break
        best = max(ok, key=lambda r: r[key]); dec["chosen"] = best["load_id"]; dec["action"] = "AUTO_BOOK"
        dec["uplift_vs_empty_gbp"] = round(best["net_to_home_gbp"] - dec["empty_return"]["net_gbp"], 2)
        out["decisions"].append(dec)
        st = best["_state_after"]; chosen.append(best["load_id"]); revenue += best["rate"]
    final = st.copy()
    escalated = out["decisions"][-1]["action"] == "NEEDS_HUMAN"
    if not escalated:
        drive(final, home, road_miles(st.loc, home), cfg, "drive home", regulated)
    out["timeline"] = final.events
    out["blocks"] = final.blocks
    total_miles = sum(e["miles"] for e in final.events if e["type"] == "drive")
    cost = total_miles * cfg["cost_per_mile_gbp"] + (final.t - parse(f"{day}T{drv['leaves_home_at']}")).total_seconds() / 3600 * cfg["driver_cost_per_hour_gbp"]
    out["summary"] = dict(loads=chosen, revenue_gbp=revenue, cost_gbp=round(cost, 2), profit_gbp=round(revenue - cost, 2),
        total_miles=round(total_miles, 1), total_drive_h=round(final.drive_h, 2), max_continuous_driving_h=round(final.max_continuous_h, 2), home_at=None if escalated else hhmm(final.t),
        breaks=sum(1 for e in final.events if e["type"] == "break"))
    out["policy_label"] = "Policy auto-booking (simulation)"
    out["diesel_price_ppl"] = cfg["diesel_price_ppl"]
    return out

if __name__ == "__main__":
    import sys
    scn = json.load(open(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG.parent.parent / "data/chain/chain_scenario_v1.json"))
    print(json.dumps(plan_day(scn), indent=1))
