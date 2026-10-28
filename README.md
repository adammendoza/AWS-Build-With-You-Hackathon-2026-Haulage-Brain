# Closed-Loop Trucking Bid Agent

An agent-assisted pricing workflow that helps small fleets evaluate incoming loads, produce evidence-backed quotes, and keep the fleet manager in control of every decision.

## The problem

Small fleet operators have only minutes to decide whether a load is feasible and profitable. The information needed to make that decision is scattered across load postings, route and fuel data, driver availability, hours-of-service constraints, equipment restrictions, and the fleet's own rate history.

That creates two bad outcomes: profitable loads are missed because research takes too long, or unprofitable loads are accepted because the true cost and compliance risk were not visible.

## The closed loop

This project proves one complete workflow:

```text
Load posting
    |
    v
Specialist agents research the load in parallel
    |-- Route and fuel cost
    |-- Driver-hours and restriction compliance
    `-- Fleet-rate and margin analysis
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
- **Fail closed.** Missing route, driver-hours, equipment, or rate data produces a review warning instead of an invented answer.
- **Show the math.** Every recommendation includes estimated operating cost, proposed quote, expected margin, assumptions, risks, and source links.
- **Use real operations safely.** The prototype may evaluate sanitized loads from a real fleet, but customer, broker, driver, and commercially sensitive details must not enter the public repository.
- **Agents advise; deterministic rules protect.** Models research and reason, while code enforces approval, minimum-margin, required-field, and compliance gates.

## Specialist agents

### Route and fuel analyst

- Estimates loaded and deadhead mileage.
- Calculates fuel consumption and cost from fleet-specific MPG and current fuel prices.
- Identifies tolls, weather, terrain, and route restrictions that could materially change cost or timing.
- Returns assumptions and cited sources, not just a total.

### Compliance analyst

- Evaluates pickup and delivery windows against available driver hours.
- Checks equipment, weight, route, and jurisdiction restrictions represented in the prototype.
- Flags unknown or conflicting facts for human review.
- Produces a feasibility verdict; it does not make legal or dispatch decisions.

### Margin analyst

- Compares the load with the fleet's rate card, operating-cost floor, and sanitized historical rates.
- Calculates break-even price, target quote, estimated profit, and margin percentage.
- Explains which inputs have the greatest effect on the recommendation.

### Bid supervisor

- Reconciles the specialist outputs.
- Rejects recommendations that lack required evidence or violate a deterministic safety rule.
- Produces one concise `APPROVE`, `PASS`, or `REVIEW` recommendation for the fleet manager.

## Hackathon stack

| Technology | Load-bearing responsibility |
|---|---|
| **CrewAI** | Orchestrates specialist agents with distinct roles, tools, and partial context. |
| **You.com** | Grounds live route conditions, fuel prices, restrictions, weather, and other current web facts with citations. |
| **Parasail** | Runs agent inference and produces structured specialist and supervisor outputs. |
| **One** | Posts the recommendation to Discord and returns the fleet manager's approve/pass decision to the workflow. |

Removing any partner breaks a visible part of the end-to-end loop rather than merely swapping out an API passthrough.

## Proposed input

The prototype accepts a normalized load record such as:

```json
{
  "load_id": "demo-1042",
  "origin": "Minneapolis, MN",
  "destination": "Chicago, IL",
  "pickup_window": "2026-10-29T08:00:00-05:00",
  "delivery_window": "2026-10-30T10:00:00-05:00",
  "equipment_type": "dry_van_53",
  "weight_lbs": 38000,
  "broker_offer_usd": 1850,
  "deadhead_miles": 42
}
```

Public demos and tests use synthetic or sanitized data only.

## Proposed output

Every evaluation produces a structured decision packet:

```json
{
  "load_id": "demo-1042",
  "recommendation": "APPROVE",
  "proposed_quote_usd": 2100,
  "estimated_cost_usd": 1580,
  "estimated_profit_usd": 520,
  "estimated_margin_pct": 24.8,
  "compliance_status": "REVIEWED",
  "confidence": 0.86,
  "assumptions": [],
  "risks": [],
  "citations": [],
  "approval_status": "PENDING"
}
```

The exact schema will be versioned once implementation begins. Approval state is stored separately from the agents' recommendation so model output can never impersonate a human decision.

## MVP scope

The hackathon prototype is intentionally narrow:

1. Accept one load posting through a form or JSON fixture.
2. Run route/fuel, compliance, and margin analysis in parallel.
3. Assemble an evidence-backed bid packet.
4. Post the recommendation to a private Discord channel through One.
5. Accept an explicit `APPROVE` or `PASS` response from the fleet manager.
6. Record the complete decision and agent evidence in an audit log.

### Not in the MVP

- Automatic booking or tender acceptance.
- Automatic broker outreach or binding quote submission.
- Full transportation-management-system replacement.
- Nationwide legal or regulatory coverage.
- Autonomous changes to fleet rates or safety rules.

## Demo flow

The target demo takes less than two minutes:

1. Submit a sanitized load from the fleet.
2. Watch the three specialist analyses complete.
3. Open the cost, compliance, and margin evidence behind the recommendation.
4. Show the recommendation arriving in Discord.
5. Select `APPROVE` or `PASS` as the fleet manager.
6. Return to the application and show the recorded human decision.

The key proof is not that agents can discuss a load. It is that a load can travel from intake to researched recommendation to an auditable human decision without any autonomous booking.

## Success criteria

- A new user can run the demo from documented setup steps.
- The same input produces a valid, schema-conforming decision packet.
- Current facts include source URLs and retrieval timestamps.
- Missing critical data produces `REVIEW`, not a fabricated value.
- A quote cannot transition from `PENDING` without a human action.
- Discord failures do not silently approve or lose a decision.
- The repository contains no credentials or private fleet data.

## Status

The product loop and safety boundary are defined. Application scaffolding, environment variables, and executable setup instructions will be added with the first implementation milestone.

