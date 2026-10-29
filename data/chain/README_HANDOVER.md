# Haulage Brain: chain + fleet handover (mock data, reference planner, tests)

All data is SYNTHETIC. Fleet size (100 trucks) and staffing ratio (30 dispatchers) are operator figures; the board, loads and cost numbers are test data.

## Layout
```
handover/
  chain/   chain_scenario_v1.json      one driver, one day (golden case). Loads now carry journey_minutes_est so the repo parser accepts them
           chain_planner.py            reference rules engine (hours, breaks, margin, homeward mode). Pure Python, no network
           test_chain_planner.py       15 tests. Golden: DRV-001 profit 391.48, home 20:10, 8.6h driving, 1 break
           expected_chain_plan.json    golden output incl. UI timeline "blocks"
  fleet/   fleet_gen.py                seeded generator -> fleet_100_v1.json and config/fleet.chain.demo.json
           fleet_100_v1.json           100 trucks, 903 board loads (incl. 2 loads over 450 miles)
           fleet_planner.py            event-driven allocation, claims loads (no double booking), writes fleet_results.json
           fleet_results.json          output the fleet UI reads (contract: trucks[], kpis, exceptions[], rejection_counts)
           test_fleet_planner.py       17 invariant tests + 2 repo-compat tests
  config/  fleet.chain.demo.json       repo FleetConfig format (6 vehicle profiles, 100 vehicles) + board_vehicle_map
```

## Run
```
cd handover/chain && python -m pytest -q          # 15 pass
cd ../fleet && python -m pytest -q                # 17 pass (~7s). Install the repo package first (pip install -e .) so the 2 compat tests run
python fleet_gen.py && python fleet_planner.py    # regenerate data + results (deterministic, ~3s)
```

## Where things go in the repo (additive only; do not edit existing modules, tests or data)
- chain_planner.py, fleet_planner.py, fleet_gen.py -> `src/load_quoting_swarm/chain/` (change the `from chain_planner import` lines to package-relative imports)
- tests -> `tests/chain/`; data -> `data/chain/`, `data/fleet/`; config -> `config/fleet.chain.demo.json` (do NOT edit `config/fleet.demo.json`)
- Do not copy any standalone `pricing.py` into the repo. The repo's `pricing.py` is the quote-formula source of truth.
- Auto-booking must be opt-in and labelled "Policy auto-booking (simulation)". Use the existing ledger API: `record_quote_summary(...)` then `decide(quote_id, decision="APPROVE", manager="policy:auto-book-v1")`. Leave the existing "human approval" strings and tests untouched.

## Cost model (fleet_gen.py / fleet_planner.py)
cost per mile = 4.54609 / mpg x diesel_ppl / 100 + fixed_cost_per_mile (same fuel maths as the repo), plus driver cost per hour (GBP 18.5). Diesel = 199.22p (UK week of 26 Oct 2026, from the recorded You.com run). Per-truck speed and mpg come from the vehicle profile. In production, read these from the repo's FleetConfig and live You.com market inputs.
Rules (config): 9h daily driving cap, 45 min break after 4.5h, HGV rules only for 7.5t / 18t / Artic, load and unload 45 min (repo default is 60: configurable), min margin 8% (on price), homeward mode when free at or after 15:00, home by 21:00, 2 chained loads after the first job.

## Metric definitions (so nobody overclaims)
- **decisions**: next-load booking decisions only (2 per truck per day at most). It is NOT all dispatcher work (calls, pricing, customer service).
- **escalated decisions**: NEEDS_HUMAN (no legal option and driver cannot legally get home), THIN_MARGIN (chosen margin under 12%), OVER_HOURS_OPPORTUNITY (manager may authorise a 10h day).
- **tempting_illegal_avoided**: decisions where a more profitable option existed but was rejected only for OUT_OF_HOURS / HOME_DEADLINE, and the best legal load was booked instead.
- **illegal_options_blocked**: vehicle-matched option evaluations rejected for hours or deadline (an evaluation count, not a count of distinct loads). Prefer tempting_illegal_avoided in the pitch.
- **baseline**: each truck does its first job, then drives home empty. 8 trucks have first jobs too far for an HGV to return legally the same day; their baseline is itself non-compliant and they appear as NEEDS_HUMAN.
- **illustrative_dispatchers_needed**: ceil(30 x escalated / total decisions). Illustrative only; never present as a measured headcount.
