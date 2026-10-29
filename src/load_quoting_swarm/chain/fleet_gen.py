"""Generates fleet_100_v1.json: 100 trucks (London homes), one pre-booked first job each, and a 903-load board.
Seeded and deterministic. All data is SYNTHETIC. Costs come from config/fleet.chain.demo.json (repo FleetConfig format)."""
import json, math, os, random, sys
from pathlib import Path
from .chain_planner import road_miles
from .economics import DEFAULT_CONFIG, fleet_economics
from ..config import load_fleet_config

SEED, DAY = 20261029, "2026-10-29"
MIX = [("7.5t Box, Tail Lift", 25), ("18t Curtain Side, Tail Lift", 25), ("Artic 44t Curtain Side", 20), ("LWB up to 4m", 15), ("Luton, Tail Lift", 15)]
_RAW = json.loads(DEFAULT_CONFIG.read_text())
_FLEET = load_fleet_config(DEFAULT_CONFIG)
DIESEL_PPL = _RAW["diesel_price_ppl_demo"]
BOARD_TO_PROFILE = _RAW["board_vehicle_map"]
DRIVER_COST_H = _FLEET.driver_cost_per_hour_gbp
PROFILES = [(p.vehicle_type, p.mpg, p.fixed_cost_per_mile_gbp, p.max_payload_kg,
             p.typical_speed_mph, p.ulez_compliant) for p in _FLEET.vehicle_profiles.values()]

def cost_per_mile(board_vehicle):
    return fleet_economics({"max_daily_driving_h": 9, "break_after_h": 4.5, "break_minutes": 45}, board_vehicle)["cost_per_mile_gbp"]

def speed(board_vehicle):
    return _FLEET.vehicle_profiles[BOARD_TO_PROFILE[board_vehicle].casefold()].typical_speed_mph

def leg_cost(miles, veh):
    return miles * cost_per_mile(veh) + miles / (14 if miles < 8 else speed(veh)) * DRIVER_COST_H

HUBS = {  # name: (lat, lng, outward postcode, weight)
 "Birmingham":(52.47,-1.88,"B9",6),"Manchester":(53.46,-2.32,"M17",5),"Leeds":(53.78,-1.53,"LS10",4),"Nottingham":(52.95,-1.15,"NG7",5),
 "Leicester":(52.64,-1.13,"LE4",5),"Bristol":(51.50,-2.70,"BS11",3),"Southampton":(50.92,-1.43,"SO15",3),"Reading":(51.45,-0.97,"RG2",4),
 "Northampton":(52.24,-0.90,"NN4",5),"Milton Keynes":(52.04,-0.76,"MK12",5),"Oxford":(51.75,-1.26,"OX4",3),"Cambridge":(52.21,0.12,"CB4",3),
 "Norwich":(52.63,1.30,"NR6",2),"Ipswich":(52.06,1.15,"IP3",2),"Cardiff":(51.48,-3.18,"CF10",2),"Luton":(51.88,-0.42,"LU5",6),
 "Coventry":(52.41,-1.51,"CV6",4),"Derby":(52.92,-1.47,"DE24",3),"Peterborough":(52.57,-0.24,"PE2",3),"Swindon":(51.56,-1.78,"SN3",2),
 "Watford":(51.66,-0.40,"WD18",4),"Slough":(51.51,-0.59,"SL1",3),"Dartford":(51.45,0.22,"DA1",4),"Chelmsford":(51.74,0.47,"CM2",3),
 "Aberdeen":(57.15,-2.09,"AB11",1),"Inverness":(57.48,-4.22,"IV1",1)}
HOMES = [("Walthamstow","E17",51.59,-0.02),("Stratford","E15",51.54,0.00),("Poplar","E14",51.51,-0.01),("Tottenham","N17",51.60,-0.07),
 ("Willesden","NW10",51.54,-0.24),("Peckham","SE15",51.47,-0.07),("Woolwich","SE18",51.49,0.06),("Streatham","SW16",51.42,-0.13),
 ("Acton","W3",51.51,-0.27),("Shepherd's Bush","W12",51.50,-0.23),("Hackney","E8",51.545,-0.06),("Battersea","SW11",51.47,-0.16)]
STREETS = ["Cannon Street","Mill Way","Wharf Street","Foundry Lane","Canal Road","Victoria Road","Dock Road","Brunel Way"]
CATS = ["Building materials","Pallets","Retail DC","Machinery","Food & drink","Furniture","Automotive"]
BROKERS = ["Northway Freight","Clearway Logistics","Brightline Transport","Kestrel Freight","Pennine Load Services","QuickDrop Couriers"]

def pc(prefix, R): return f"{prefix} {R.randint(1,9)}{R.choice('ABDEFGHJLNPQRSTUWXYZ')}{R.choice('ABDEFGHJLNPQRSTUWXYZ')}"
def site(name, lat, lng, prefix, role, R, jitter=0.02):
    la, lo = round(lat + R.uniform(-jitter, jitter), 4), round(lng + R.uniform(-jitter, jitter), 4)
    return dict(name=f"{name} {role}", address=f"Unit {R.randint(1,40)}, {R.choice(STREETS)}", town=name.upper(), area=name, postcode=pc(prefix, R), lat=la, lng=lo)
def r5(x): return int(round(x / 5) * 5)
def hhmm_to_dt(t): return f"{DAY}T{t}"
def fmt(minutes): return f"{int(minutes // 60):02d}:{int(minutes % 60):02d}"

def make_load(R, lid, frm, to, vehicle, w_start_min, w_len, factor, cat, status="Available", rate=None):
    a = site(frm[0], frm[1], frm[2], frm[3], "Depot", R); b = site(to[0], to[1], to[2], to[3], "Receiving Dock", R, 0.01)
    d = round(road_miles((a["lat"], a["lng"]), (b["lat"], b["lng"])), 1)
    if rate is None: rate = max(60, r5(leg_cost(d, vehicle) * factor))
    return dict(load_id=lid, status=status, category=cat, from_=a, to=b, distance_miles=d, vehicle_requested=vehicle, agreed_rate_gbp=rate,
        rate_per_mile=round(rate / d, 2), pickup=dict(type="window", start=hhmm_to_dt(fmt(w_start_min)), end=hhmm_to_dt(fmt(w_start_min + w_len))), deliver="ASAP",
        journey_minutes_est=int(round(d / speed(vehicle) * 60)), weight_kg=None if R.random() < .35 else R.randrange(150, 9000, 10), packaging=R.choice(["Pallets", "Boxes", "Loose", None]),
        load_notes=R.sample(["Call contact on arrival", "Hi vis & safety boots required", "Tail lift required", "Driver must upload photo of goods once delivered", "Booked slot, late arrivals refused"], 2),
        booked_by_company=R.choice(BROKERS), ulez=False)

def build():
    R = random.Random(SEED)
    hubs = [(n, v[0], v[1], v[2]) for n, v in HUBS.items()]; hub_w = [v[3] for v in HUBS.values()]
    pick_hubs = [h for h in hubs if h[0] not in ("Aberdeen", "Inverness")]; pick_w = [HUBS[h[0]][3] for h in pick_hubs]
    vehicles = [v for v, n in MIX for _ in range(n)]; R.shuffle(vehicles)
    lid = [91100000]
    def nid(): lid[0] += R.randint(3, 11); return lid[0]
    trucks = []
    for i, veh in enumerate(vehicles, 1):
        hn, hpc, hla, hlo = R.choice(HOMES); home = (round(hla + R.uniform(-.015, .015), 4), round(hlo + R.uniform(-.015, .015), 4))
        leave = 330 + 5 * R.randint(0, 24)                                       # 05:30 to 07:30
        for _ in range(60):                                                      # first job: 40-220 road miles away
            dest = R.choices(pick_pool := [h for h in pick_hubs if h[0] not in ("Watford", "Slough", "Dartford")], [HUBS[h[0]][3] for h in pick_pool])[0]
            if 40 <= road_miles(home, (dest[1], dest[2])) <= 220: break
        near = (hn, home[0], home[1], hpc)
        job = make_load(R, nid(), near, dest, veh, leave + 20, 45, R.uniform(1.15, 1.5), R.choice(CATS), status="Accepted")
        job["from_"]["lat"], job["from_"]["lng"] = round(home[0] + .01, 4), round(home[1] + .01, 4)
        job["distance_miles"] = round(road_miles((job["from_"]["lat"], job["from_"]["lng"]), (job["to"]["lat"], job["to"]["lng"])), 1)
        pj = (job["from_"]["lat"], job["from_"]["lng"]); dj = (job["to"]["lat"], job["to"]["lng"])
        full = leg_cost(road_miles(home, pj), veh) + leg_cost(job["distance_miles"], veh) + leg_cost(road_miles(dj, home), veh)   # out, loaded, empty return
        job["agreed_rate_gbp"] = max(60, r5(full * R.uniform(1.05, 1.35))); job["rate_per_mile"] = round(job["agreed_rate_gbp"] / job["distance_miles"], 2)
        job["journey_minutes_est"] = int(round(job["distance_miles"] / speed(veh) * 60))
        trucks.append(dict(truck_id=f"T-{i:03d}", driver_id=f"DRV-{i:03d}", dispatcher_id=((i - 1) % 30) + 1, vehicle=veh, hgv=any(k in veh for k in ("7.5t", "18t", "Artic")),
                           home=dict(label=f"{hn}, London {hpc}", lat=home[0], lng=home[1]), leaves_home_at=fmt(leave), first_job=job))
    board = []
    for _ in range(900):
        veh = R.choices([v for v, _ in MIX], [n for _, n in MIX])[0]
        frm = R.choices(pick_hubs, pick_w)[0]
        for _ in range(60):
            to = R.choices(hubs, hub_w)[0]
            d = road_miles((frm[1], frm[2]), (to[1], to[2]))
            if to[0] != frm[0] and 25 <= d <= (230 if veh in ("LWB up to 4m", "Luton, Tail Lift") else 300): break
        board.append(make_load(R, nid(), frm, to, veh, 600 + 15 * R.randint(0, 30), R.choice([120, 150, 180, 240]), R.uniform(0.85, 1.6), R.choice(CATS)))
    for frm_n, to_n, veh in (("Reading", "Aberdeen", "Artic 44t Curtain Side"), ("Luton", "Inverness", "Artic 44t Curtain Side"), ("Northampton", "Aberdeen", "18t Curtain Side, Tail Lift")):
        f = next(h for h in hubs if h[0] == frm_n); t = next(h for h in hubs if h[0] == to_n)
        board.append(make_load(R, nid(), f, t, veh, 600, 150, 1.4, "Building materials"))   # >450 mi: fuel tier not configured
    R.shuffle(board)
    return dict(meta=dict(scenario="fleet_100_v1", seed=SEED, day=DAY, synthetic=True, diesel_ppl=DIESEL_PPL, dispatchers=30,
        notes="Synthetic fleet and freight board. 100 trucks, 30 dispatchers (operator figures). Costs from config/fleet.chain.demo.json."), trucks=trucks, board=board)

def fleet_config(fleet):
    return dict(fixture_notice="Synthetic economics for tests only. Do not present as real fleet data.", placeholder_values=False, fleet_name="Synthetic 100-Truck Fleet",
        target_margin_pct=20, minimum_margin_pct=8, driver_cost_per_hour_gbp=DRIVER_COST_H, diesel_price_ppl_demo=DIESEL_PPL, board_vehicle_map=BOARD_TO_PROFILE,
        vehicle_profiles=[dict(vehicle_type=p[0], mpg=p[1], fixed_cost_per_mile_gbp=p[2], max_payload_kg=p[3], typical_speed_mph=p[4], ulez_compliant=p[5]) for p in PROFILES],
        vehicles=[dict(vehicle_id=t["truck_id"], vehicle_type=BOARD_TO_PROFILE[t["vehicle"]], available_from=f"{DAY}T05:00:00+00:00", available_until=f"{DAY}T21:00:00+00:00", location=t["home"]["label"]) for t in fleet["trucks"]])

if __name__ == "__main__":
    fleet = build()
    json.dump(fleet, open(DEFAULT_CONFIG.parent.parent / "data/fleet/fleet_100_v1.json", "w"), indent=1)
    json.dump(fleet_config(fleet), open(DEFAULT_CONFIG, "w"), indent=1)
    print(len(fleet["trucks"]), "trucks;", len(fleet["board"]), "board loads")
