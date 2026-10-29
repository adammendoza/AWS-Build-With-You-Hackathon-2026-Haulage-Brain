# Haulage Brain

Haulage Brain is an Open Haunt agent swarm that evaluates UK freight loads, produces evidence-backed quotes, and keeps the fleet manager in control of every booking decision.

## The problem

Small fleet operators have only minutes to decide whether a load is feasible and profitable. The information needed to make that decision is scattered across load postings, route and fuel data, driver availability, hours-of-service constraints, equipment restrictions, and the fleet's own rate history.

That creates two bad outcomes: profitable loads are missed because research takes too long, or unprofitable loads are accepted because the true cost and compliance risk were not visible.

## The closed loop

This project proves one complete workflow:

```text
Load posting
    |
    v
Specialist stages research the load in parallel
    |-- Pricing and margin
    |-- Compliance and restrictions
    `-- Fleet availability and vehicle fit
    |
    v
Quote + recommendation + cited evidence
    |
    v
Fleet manager chooses APPROVE or PASS in Discord
    |
    v
Decision is recorded; no load is booked automatically
```

The agents compress the research and pricing work. The fleet manager remains the decision-maker.

## Product principles

- **Human approval is mandatory.** The system never books a load or sends a binding quote without an explicit approval.
- **Fail closed.** Missing route, timing, equipment, weight, or rate data stops that load's evaluation instead of producing an invented quote.
- **Show the math.** Every recommendation includes estimated operating cost, proposed quote, expected margin, assumptions, risks, and source links.
- **Use real operations safely.** The prototype may evaluate sanitized loads from a real fleet, but customer, broker, driver, and commercially sensitive details must not enter the public repository.
- **Agents advise; deterministic rules protect.** Models research and reason, while code enforces approval, minimum-margin, required-field, and compliance gates.

## Specialist agents

### Pricing specialist

- Calculates fuel consumption from route miles and the fleet vehicle's MPG.
- Consumes the current UK diesel price and relevant restriction charge grounded by You.com.
- Adds fixed vehicle and driver-time costs, then calculates break-even, minimum viable, and target prices.
- Compares the load's offered rate with the fleet's minimum margin.

### Compliance analyst

- Evaluates pickup and delivery windows against estimated travel, loading, and waiting time.
- Checks payload, requested vehicle type, and ULEZ cost coverage represented in the prototype.
- Flags unknown or conflicting facts for human review.
- Produces a feasibility verdict; it does not make legal or dispatch decisions.

### Fleet-fit specialist

- Finds fleet vehicles of the requested type that cover the full pickup-to-delivery window.
- Selects a candidate vehicle and flags likely deadhead for manager review.
- Passes only role-scoped vehicle availability into its inference context.

### Bid supervisor

- Reconciles the specialist outputs.
- Rejects recommendations that lack required evidence or violate a deterministic safety rule.
- Produces one concise `APPROVE`, `PASS`, or `REVIEW` recommendation for the fleet manager.

## Hackathon stack

| Technology | Load-bearing responsibility |
|---|---|
| **CrewAI** | Owns ingest, vehicle/category routing, the quote Flow, and scoped specialist Memory. |
| **You.com** | Grounds the live UK diesel price plus route/restriction information with citations. |
| **Parasail** | Runs agent inference and produces structured specialist and supervisor outputs. |
| **One** | Posts the recommendation to Discord; the manager's explicit approve/pass decision is then written to the booking ledger. |

Removing any partner breaks a visible part of the end-to-end loop rather than merely swapping out an API passthrough.

## Input

The normalizer accepts the supplied fixture's likely snake_case or camelCase fields. Its internal load shape is:

```json
{
  "load_id": "UK-1042",
  "status": "Available",
  "origin": "London, UK",
  "destination": "Birmingham, UK",
  "pickup_at": "2026-10-29T09:00:00+00:00",
  "delivery_at": "2026-10-29T15:00:00+00:00",
  "vehicle_type": "Luton Van",
  "category": "General Freight",
  "distance_miles": 126,
  "weight_kg": 850,
  "offered_rate_gbp": 180,
  "loading_minutes": 45,
  "expected_waiting_minutes": 60,
  "notes": ["Pickup is inside the London ULEZ"]
}
```

Public demos and tests use synthetic or sanitized data only.

## Output

Every evaluation produces a structured decision packet:

```json
{
  "quote_id": "Q-UK-1042",
  "load_id": "UK-1042",
  "recommendation": "PASS",
  "proposed_quote_gbp": 228.85,
  "pricing": {
    "estimated_total_cost_gbp": 183.08,
    "offered_margin_pct": -1.71,
    "restriction_cost_gbp": 12.50
  },
  "market_inputs": {
    "diesel_price_ppl": 145.0,
    "citations": []
  },
  "approval_status": "PENDING"
}
```

Approval state is stored separately from the agents' recommendation so model output can never impersonate a human decision.

## MVP scope

The hackathon prototype is intentionally narrow:

1. Read the supplied `loads.json`, select `Available` loads, and route them by vehicle/category.
2. Run pricing, compliance, and fleet-fit analysis with scoped Memory.
3. Use live You.com facts inside the price calculation and Parasail for structured inference.
4. Process all 89 Available fixtures with bounded parallelism and report time, throughput, tokens, and estimated cost.
5. Post each quote to Discord through One and require an explicit manager `APPROVE` or `PASS`.
6. Append the human decision to the booking ledger.

### Not in the MVP

- Broker/TMS booking or tender acceptance; `BOOKED` means booked in the prototype ledger.
- Automatic broker outreach or binding quote submission.
- Full transportation-management-system replacement.
- Comprehensive UK legal, route, or driver-hours compliance advice.
- Autonomous changes to fleet rates or safety rules.

## Demo flow

The target demo takes less than two minutes:

1. Show an underpriced load being passed with its negative margin.
2. Show a ULEZ-marked load gaining a grounded restriction charge and a higher quote.
3. Show the 89-load Parasail run's elapsed time, throughput, token usage, and estimated cost.
4. Show a recommendation arriving in Discord through One.
5. Record the manager's explicit `APPROVE`, then show `BOOKED` in the ledger.

The key proof is not that agents can discuss a load. It is that a load can travel from intake to researched recommendation to an auditable human decision without any autonomous booking.

## Success criteria

- A new user can run the demo from documented setup steps.
- The same input produces a valid, schema-conforming decision packet.
- Current facts include source URLs and retrieval timestamps.
- Missing critical route or price data stops evaluation; optional missing weight or delivery windows are preserved as visible compliance warnings.
- A quote cannot transition from `PENDING` without a human action.
- Discord failures do not silently approve or lose a decision.
- The repository contains no credentials or private fleet data.

## Quick start

Use Python 3.12. The project pins CrewAI 1.9.3 because later releases require LanceDB wheels that are not published for this Intel macOS environment.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Start the browser loadboard and open <http://127.0.0.1:8765>:

```bash
haulage-brain-ui --open
```

The UI loads all 89 simulated records, filters by status and vehicle, shows the supplied PRD quote breakdown, and writes explicit Approve/Pass actions to `var/booking-ledger.jsonl`.

Verify the first milestone—ingest Available loads and route the first three by vehicle/category:

```bash
haulage-brain ingest --loads data/loads_v2.json --limit 3 --crewai
```

Run the complete offline safety test. Its market data, inference, fleet, and loads are explicitly synthetic and do not count as live partner usage:

```bash
haulage-brain run \
  --loads data/loads_v2.json \
  --fleet config/fleet.demo.json \
  --limit 3 \
  --parallel 3 \
  --record-ledger
```

Approve one pending quote as the human fleet manager, then inspect the ledger:

```bash
haulage-brain decide Q-90857138 APPROVE --manager "fleet-manager"
haulage-brain ledger
```

The original `load-swarm` and `load-swarm-ui` commands remain as compatibility aliases.

## GitHub Pages

Every push to `main` runs `.github/workflows/pages.yml`. The workflow validates all
89 calculated prices against `data/expected_quotes_v2.json`, builds the loadboard,
and deploys it to GitHub Pages. The Pages build needs no API keys because it displays
the checked fixture and deterministic quote results.

GitHub Pages is static hosting, so its Approve/Pass controls are explicitly a browser
demo and persist only in that browser's local storage. Run the Python server locally
or deploy it to an application host when decisions must write to the append-only
booking ledger.

To reproduce the Pages artifact locally:

```bash
PYTHONPATH=src python scripts/build_pages.py --output _site
python -m http.server 8000 --directory _site
```

Then open <http://127.0.0.1:8000>.

## Lambda deployment

Pushes to `main` also run the full Python and browser test suite, build the
container for `linux/amd64`, push an immutable commit-tagged image to ECR, and
update the `haulage-brain` Lambda. GitHub Actions authenticates with AWS OIDC;
the repository variable `AWS_LAMBDA_DEPLOY_ROLE_ARN` identifies the scoped
deployment role, so no long-lived AWS access keys are stored in GitHub.

The Lambda container starts the chain-capable server in deterministic offline
fleet-planning mode. Set `HB_ENABLE_CHAIN=1` on the function to expose
`/fleet.html`; the existing per-load analysis remains available from the main
loadboard.

### Visual API trace

Each Available load has a **Watch live APIs** action when the Python backend is
running. It starts a non-booking analysis for that load and visualizes real events:

1. CrewAI ingest and vehicle/category routing.
2. You.com diesel and restriction grounding with citations.
3. Deterministic quote math, including the difference from a 145p/L demo baseline.
4. Three parallel Parasail specialists and the Parasail supervisor.
5. The deterministic safety gate and pending One/Discord human handoff.

The trace shows real timing, model name, token usage, citations, and quote impact.
It uses the explicitly synthetic `config/fleet.demo.json` economics unless a real
fleet file is passed with `haulage-brain-ui --fleet config/fleet.local.json`.
Nothing is booked or posted to Discord by this visualization.

GitHub Pages cannot safely hold provider keys, so it offers one clearly labelled
**Recorded live** replay on load `90857138`. Other loads require the local backend
for live analysis. The sanitized replay is stored in `data/demo_run.json`.

## When API keys are required

| Service | Credential/setup | Needed when |
|---|---|---|
| You.com | `YDC_API_KEY` | Running `haulage-brain run --live`; it grounds diesel and restriction inputs that change the price. |
| Parasail | `PARASAIL_API_KEY` and `PARASAIL_MODEL` | Running `haulage-brain run --live`; specialists and the supervisor use it for inference. |
| One | `ONE_DISCORD_CONNECTION_KEY`, `ONE_DISCORD_CHANNEL_ID`, authenticated One CLI | Adding `--discord` to publish the recommendation to Discord. |
| CrewAI | No service key in the current local Flow | Ingest/routing and scoped memory run in-process; a key is only needed if CrewAI is later configured to call a hosted model directly. |

Put local credentials in an uncommitted `.env`; the CLI loads it automatically. GitHub
Pages must never receive these keys: any secret shipped to browser JavaScript is
public. A future hosted backend should receive them through its secret manager.

## Run with the scored partners

1. Use the supplied `data/loads_v2.json` fixture: all 89 loads are Available for swarm evaluation.
2. Copy `config/fleet.example.json` to `config/fleet.local.json`, replace every placeholder with real fleet economics, and set `placeholder_values` to `false`.
3. Export the values documented in `.env.example`. Never commit the resulting `.env`.
4. Initialize One and connect the Discord account that has access to the event channel:

   ```bash
   npm i -g @withone/cli
   one init
   one add discord
   ```

5. Confirm the Open Haunt Discord channel ID with the organizers. Do not assume Track 1's `#loft-incident` channel is the Open Haunt submission channel.
6. Run all 89 Available loads with bounded concurrency:

   ```bash
   haulage-brain run \
     --live \
     --loads data/loads_v2.json \
     --fleet config/fleet.local.json \
     --limit 89 \
     --parallel 8 \
     --record-ledger \
     --discord \
     --output var/run-41.json
   ```

`--live` fails closed if You.com or Parasail credentials are absent. The One publisher resolves the Discord send action and its documentation at runtime; no action ID or platform credential is committed.

## Why You.com changes the answer

The pricing calculation does not merely cite You.com. It consumes the grounded UK diesel price directly:

```text
fuel litres = route miles / vehicle MPG * 4.54609
fuel cost   = fuel litres * live diesel pence-per-litre / 100
total cost  = fuel + fixed vehicle cost + driver time + grounded restriction charges
quote       = total cost / (1 - target margin)
```

For a non-compliant vehicle on a ULEZ-marked load, the grounded current charge is also added to cost. Tests prove that changing the diesel input changes fuel cost, margin, and proposed quote.

The supplied DispatchIQ PRD formula is also deterministic: journey time always rounds up to 30 minutes, distance selects a fixed fuel tier, both endpoints must be London for the city surcharge, and journeys beyond 450 miles require human review. The final swarm target is the higher of that formula quote and the fleet-cost target, so neither the partner grounding nor the fleet economics can be bypassed.

## Repository map

```text
config/                       Fleet economics and vehicle availability
data/                         Updated 89-load simulated UK fixture
src/load_quoting_swarm/
  flow.py                     CrewAI ingest/router and swarm Flow
  grounding.py                You.com search and fail-closed fact extraction
  specialists.py              Pricing, compliance, and fleet-fit calculations
  inference.py                Parallel Parasail structured inference
  memory.py                   Enforced specialist Memory scopes
  pipeline.py                 Concurrent specialist and supervisor loop
  one_discord.py              One discover-then-execute Discord publisher
  ledger.py                   Append-only human approval and booking ledger
  pricing.py                  Supplied deterministic PRD quote formula
  web.py + web_assets/        Local interactive loadboard and decision API
tests/                        Pricing, routing, ULEZ, parallelism, and approval gates
```

## Current build status

| Step | Status | Evidence |
|---|---|---|
| Ingest and vehicle/category router | Working | The updated fixture loads and routes all 89 Available records. |
| Three scoped specialists | Working | Pricing, compliance, and fleet-fit assessments run concurrently. |
| You.com in margin math | Implemented; credentials required for live proof | Diesel and ULEZ values directly alter calculated cost. |
| Parasail parallel inference | Implemented; credentials required for live proof | Bounded concurrent specialist calls and token usage reporting. |
| One to Discord | Implemented; channel and connection required | Action is discovered at runtime before execution. |
| Human approval ledger | Working | Only `APPROVE` transitions `PENDING` to `BOOKED`; duplicate decisions fail. |
| One-tap Discord callback | Open | Requires confirmation of the event channel and supported inbound interaction path. |
| Loadboard/ledger UI | Working | Search, filters, PRD quote breakdown, raw JSON, and manager Approve/Pass actions. |

## Tests

```bash
pytest
node --test tests/test_web_ui.mjs tests/atmosphere.test.cjs tests/easter-eggs.test.cjs
```

The JavaScript UI checks use Node.js 20+ and cover manager name saving, reloads, decision attribution, and unavailable browser storage.

The Python suite covers the 89-load fixture, status filtering, vehicle/category routing, the supplied pricing formula, live-price sensitivity, ULEZ repricing, parallel execution, UI decisions, and the human approval invariant.

## Status and honesty boundary

The offline end-to-end loop and browser UI work against 89 synthetic records, all marked Available for evaluation. They must not be presented as a live You.com, Parasail, One, or fleet run. A scored demo still requires real fleet economics, live partner API logs, the confirmed Discord channel, and an actual manager approval. No load is booked with a broker; `BOOKED` means an approved entry in this prototype's append-only booking ledger.


## Opt-in chain and fleet simulation

The additive planner lives in `src/load_quoting_swarm/chain/`. It plans the next
load for each synthetic truck against one shared board. HGVs have a 9-hour driving
cap and a 45-minute break after 4.5 hours; vans are exempt in this simplified
simulation. When free at or after 15:00, trucks only take loads that move toward
home. A truck without a legal way home stops at `NEEDS_HUMAN`; no illegal return
leg is drawn or booked. These are simulation rules, not a comprehensive legal
compliance engine (weekly hours, rest history and live road routing are absent).

Existing modules, tests, `data/loads_v2.json` and `config/fleet.demo.json` are
unchanged. The new server composes the existing loadboard handler and adds the
fleet navigation link at response time. The incoming standalone `fleet.html` was
not supplied; an interim page consumes the same `fleet_results.json` contract.

Use the existing Python environment, or install `pip install -e '.[dev]' cryptography`.
For a local, explicitly offline test:

```bash
HB_ENABLE_CHAIN=1 PYTHONPATH=src python -m load_quoting_swarm.chain.web --offline
# Open http://127.0.0.1:8765/fleet.html
```

Omit `--offline` to fetch live You.com market inputs; supply `--env-file` pointing
to an uncommitted credential file. Never copy that file into the repository.
`HB_CHAIN_ROOT` can point to the repository data/config root in an installed deployment.

- `GET /api/chain` previews the golden single-driver scenario.
- `GET /api/fleet` and `GET /fleet_results.json` expose the shared-board plan and exception resolutions.
- `POST /api/fleet` with `{"commit":true}` records eligible simulation bookings.
- `POST /api/chain/decision` takes `exception_id`, `action` (`APPROVE` or `ESCALATE`), and an explicit `manager` identity.
- `POST /api/chain/discord/interactions` receives signed Discord button interactions.

All new routes return 404 unless `HB_ENABLE_CHAIN=1`. Reads do not book anything.
The UI labels this **Policy auto-booking (simulation)**. Policy bookings call the
existing `record_quote_summary(...)` and `decide(..., manager="policy:auto-book-v1")`
APIs. Exception legs and their dependent legs wait for human review. Approving
`OVER_HOURS_OPPORTUNITY` acknowledges the selected **legal** load, never the
rejected 10-hour alternative. Approving `NEEDS_HUMAN` only acknowledges the need
for manual dispatch. No broker or TMS is contacted.

`--storage var/chain` holds a pinned day/scenario snapshot, SQLite decisions and
claims, and an append-only booking ledger. Repeated requests and restarts use the
same snapshot; input repricing does not silently rewrite approved plans. Use a
fresh storage directory for a separate test scenario. SQLite serializes all
workers sharing that directory. For production, configure authentication with
`DEMO_USERNAME`/`DEMO_PASSWORD`, HTTPS and durable storage. This has only been
prepared and tested locally: it is **not** deployed. The existing Lambda `/tmp`
storage is not durable or shared; do not enable this implementation across
independent Lambda instances without a shared transactional persistence adapter.

### Discord approval setup and test status

The approval callback is `/api/chain/discord/interactions` in
`chain/web.py`. Configure an application Interactions Endpoint URL at that HTTPS
path, set `DISCORD_PUBLIC_KEY`, `ONE_DISCORD_CHANNEL_ID`, and a comma-separated
`HB_DISCORD_MANAGER_IDS` allowlist. Ed25519 signatures and timestamps are verified;
only allowlisted managers in the configured channel can resolve exceptions.
Repeated callbacks cannot duplicate bookings. See the
[Discord interaction protocol](https://docs.discord.com/developers/interactions/receiving-and-responding).

The exception publisher tries One twice (one retry) before considering
`DISCORD_WEBHOOK_URL`. Webhook failures are logged by type only. A webhook message
links to the authenticated fleet review page because incoming webhooks alone do
not provide the application interaction callback. Never put the webhook URL in
client code, evidence or Git. Configure `HB_PUBLIC_URL` for that review link.

**Live Discord is pending:** the supplied credential file has empty One secret,
connection and channel fields; no webhook is configured. One CLI preflight failed
twice. `execute_one_action` has **not** succeeded. The user deferred channel/bot
setup and requested test preparation only. The signed callback-to-ledger path is
covered by HTTP tests, including approve, escalation, unauthorized managers,
invalid signatures and replay/duplicate rejection. No real Discord approval is claimed.

### Live provider evidence and re-baseline

Run a few synthetic trucks with actual provider calls:

```bash
PYTHONPATH=src python -m load_quoting_swarm.chain.live \
  --env-file /path/to/uncommitted/.env.local --limit 3 \
  --output var/chain-evidence/live
# Add --discord only after the channel and app are configured.
```

The verified three-truck run fetched **198.8p/L** from You.com and completed **nine
Parasail specialist explanations**. The first JSON-object-mode attempt returned
empty objects; the chain-specific client now requests a strict JSON schema and
rejects empty explanations. Model narratives are advisory and cannot change the
plan. Sanitized logs are in `data/chain/evidence/`; full local run artifacts and
the backup video are in `var/chain-evidence/`. This is real provider usage on
synthetic trucks and economics, not a live transport operation.

Golden fixtures were re-baselined once against the checked-in **199.22p/L offline
snapshot**. Costs now read the supplied FleetConfig profiles, including the 18t
profile's 40mph speed, and include driver time during loading, unloading, waiting
and breaks. The quote formula comes from the existing `pricing.py`. Overweight
loads and quotes requiring manual review are blocked from policy selection.

| Golden result | Handover | Integrated |
|---|---:|---:|
| Single driver profit | £391.48 | £244.23 |
| Single driver home | 20:10 | 20:47 |
| Single driver driving | 8.60h | 8.97h |
| Final chained load | 91000170 (Luton) | 91000205 (Dartford) |
| Fleet projected profit | £20,116.07 | £9,971.96 |
| Fleet planned loads, including first jobs | 187 | 124 |

The final single-driver option is now legal at the FleetConfig speed. The low-rate
Northampton option no longer meets the margin floor after paid service time is
counted. The integrated fleet has 92 projected home on time and 8 escalated.
The empty-return baseline itself is non-compliant for those 8 trucks; comparisons
are synthetic and are not proof of compliant operating savings.

`dispatcher_id` (1–30) is only a UI grouping key. There is no staffing, capacity or
headcount planner. `illustrative_dispatchers_needed` stays display-only and is
labelled illustrative. Decision counts cover next-load choices only.

Checks before every push:

```bash
pytest
node --test tests/test_web_ui.mjs tests/atmosphere.test.cjs tests/chain/test_fleet_ui.mjs
PYTHONPATH=src python scripts/build_pages.py --output _site
```

The additive `.github/workflows/chain-tests.yml` runs these checks on pull requests
and pushes to `main` or `feature/chain-fleet`. Existing Pages output stays unchanged;
the fleet page is served by the flagged Python entry point.
