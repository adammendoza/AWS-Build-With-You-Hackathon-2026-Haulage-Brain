# Haulage Brain — look, feel, and interaction design

## Direction

**A calm dispatch desk with a decisive edge.** Haulage Brain helps a fleet manager understand a route, compare a posted rate with a calculated quote, and make an explicit decision. The interface should feel like a working product within the first ten seconds of a demo.

The signature is a warm off-white canvas, an ink-green navigation rail, lime brand accents, precise type, and an inspectable two-column queue. Give the route and its economics the strongest visual hierarchy. Use restrained structure rather than decorative AI graphics.

## Research and interpretation

Research reviewed on 28 October 2026. These references informed the design; they do not prove that any particular color palette causes a hackathon win.

- [You.com’s official winner directory](https://github.com/youdotcom-oss/awesome-you#2026-bay-area-edition) identifies BOM Guardian, TruthPanel, Career Mission Control, and Covenant Sentinel as winners at the July 2026 AWS Builder Loft event in San Francisco. Their product descriptions emphasize concrete verdicts, evidence, and useful actions. **Our interpretation:** put the decision and its basis on the same screen.
- [You.com’s published judging criteria](https://you.com/resources/the-winners-of-the-you-com-agentic-hackathon-2025) include user experience and presentation/documentation alongside technical implementation, innovation, and impact. **Application:** a clear demo narrative, working controls, understandable states, and reproducible setup matter alongside visual polish.
- [BOM Guardian’s design source](https://github.com/jules-jo/bom-guardian/blob/main/DESIGN.md) explores a warm canvas and contrasting dark surfaces. **Application:** warm neutrals make an operational tool approachable. Haulage Brain uses its own palette, typography, and mark.
- [Covenant Sentinel’s implementation and demo narrative](https://github.com/jymiller/hack-you) expose the changed calculation, research provenance, and human approval boundary. **Application:** show the quote math and label the demo’s evidence boundaries near the decision.
- [Linear’s account of its interface refresh](https://linear.app/now/behind-the-latest-design-refresh) describes reducing competing visual weight and making actions consistent. **Application:** quiet navigation, predictable filters, compact route rows, and progressive disclosure.

## Information hierarchy

1. **Orient:** workspace, manager identity, and a visible synthetic-data label.
2. **Understand:** feed count, formula signals, pending decisions, average posted rate.
3. **Triage:** pricing-signal buttons, route/company search, vehicle/status filters, and sort.
4. **Inspect:** route timeline, schedule, vehicle, distance, missing information, and quote math.
5. **Decide:** explicit Approve or Pass, a review dialog, then a persistent ledger outcome.

The top pricing summary is computed from the complete fixture. It stays stable as the queue is filtered. Tab counts describe the complete feed; the queue count describes the combined active filters. The sidebar decision ledger shows only BOOKED and PASSED records. PENDING is still actionable.

## Visual tokens

| Token      | Value     | Purpose                                  |
| ---------- | --------- | ---------------------------------------- |
| Canvas     | `#f6f7f2` | Main workspace                           |
| Paper      | `#ffffff` | Queue, metrics, quote card               |
| Ink        | `#202820` | Primary text                             |
| Muted      | `#6a736b` | Supporting text                          |
| Line       | `#e2e6dd` | Quiet structure                          |
| Dark       | `#191e1b` | Sidebar and primary actions              |
| Lime       | `#dcf795` | Brand mark and primary-action text       |
| Green      | `#316b43` | At/above formula quote; approved outcome |
| Green tint | `#eff6e9` | Positive context                         |
| Amber      | `#8c5a19` | Reprice and unknown information          |
| Amber tint | `#fbf1df` | Warning context                          |
| Red        | `#a44137` | Below-quote gap and passed outcome       |
| Red tint   | `#fcf0ed` | Negative context                         |

Use color with a written status. Avoid gradients, noisy background patterns, glowing borders, and full-screen green success states. The small pricing strip represents the actual distribution of formula signals; it is not a live activity graphic.

### Type and spacing

- System sans stack with Inter if already installed; no remote font dependency.
- Display heading: approximately 44px desktop / 32px mobile, medium weight, tight tracking.
- Route names: 14–17px in the queue, 21–23px in the inspector.
- Financial values: 30–36px in key summaries; tabular numerals.
- Supporting desktop metadata: 9–12px; important decisions retain clear button labels.
- Spacing rhythm: 4, 8, 12, 16, 24, 32px. Panels use 12px corners; controls use 6–7px.
- Use a thin border for grouping. Reserve shadows for dialogs and prominent controls.

## Components and behavior

### Navigation and summary

Two real views: Loadboard and Decision ledger. Do not add navigation items for unimplemented capabilities. The manager name remains editable and is remembered when browser storage is available. The summary distinguishes above-quote pricing from operational profitability.

### Decision queue

Each route is one accessible button with an explicit selected state. Show load ID, status, pricing signal, endpoints, posted rate, requested vehicle, distance, quote gap, and pickup time. The queue scrolls independently on desktop. A selected row has a left accent and a pale background.

Search, vehicle, status, and pricing signal combine. Sorting operates on the filtered results. Rate/mile changes the queue’s rate display only. The `/` shortcut focuses search outside editable fields and dialogs. Empty results offer a way back. “Review next load” selects another undecided load in the current results; it never submits a decision.

### Quote inspector

Use a two-stop route timeline, small factual chips, and a quote card. Keep posted rate and formula quote visually separate. Show base time, distance fuel tier, city surcharge, minimum application when applicable, and total. Expand load instructions by default; put cargo, contact, payment, and tracking details in disclosures.

A pricing signal of APPROVE is displayed as **Above quote**. That is a formula comparison, not an agent approval or an assertion of profit. REVIEW retains its warning even if the posted rate is high. Display missing weight and ULEZ flags without inventing a clearance result.

### Manager decisions

Approve and Pass open a dialog naming the route, rate, quote, manager, and storage effect. Confirm sends the existing decision request. Disable submission while saving; prevent duplicate clicks; keep failure recoverable with an error message. The result replaces the controls with the saved manager and timestamp.

The existing backend remains the authority for legal state transitions. BOOKED means approved in the prototype ledger; it does not mean a broker booking or binding quote. A recommendation never changes approval state on its own.

### Deployment modes

- Local server: reads the fixture and appends explicit decisions to `var/booking-ledger.jsonl`.
- GitHub Pages: uses the same UI with a conspicuous browser-demo label; decisions persist in that browser’s localStorage only.
- Source-data dialog exposes the original fixture without enrichment fields.
- No external fonts, image APIs, mapping services, or new runtime dependencies are required by the redesign.

## Responsive and accessible behavior

- Wide screens: 224px navigation rail and queue/inspector split.
- Medium screens: narrower rail, then icon navigation; controls reflow.
- At 740px and below: top navigation, two-by-two summary metrics, a bounded route list, and the inspector below it. All details and decision actions remain available.
- Keep visible focus outlines, native select controls, semantic headings, labeled search/manager fields, and a skip link.
- Use pressed-state semantics on selected filters and routes. Announce result counts and toast messages without reading the entire queue after every search.
- Support reduced motion. No animation suggests agents are running when they are not.
- UK fixture times without offsets are displayed literally; timestamps with explicit offsets are converted to Europe/London. Do not silently use the viewer’s local timezone for freight schedules.

## Demo narrative

Start on the full feed. Open **Reprice**, select a route, and explain the posted-rate shortfall using the visible calculation. Open **Needs review** to show the long-distance exception. Return to the full queue, inspect requirements, then make a manager decision. Open the ledger to show the recorded outcome.

The loadboard summary uses deterministic fixture quotes. Live You.com grounding, Parasail inference, and fleet-fit checks run separately through the inspector’s API analysis action. Preserve the upstream live trace and the static demo’s recorded-run replay, including citation links, timestamps, provider errors, and LIVE versus RECORDED LIVE labels. Opening a replay must never imply a new provider call. A trace result does not approve or book a load.

## Implementation and verification

Source: `src/load_quoting_swarm/web_assets/index.html`, `app.css`, and `app.js`. Design tokens live in CSS `:root`; data and interaction state stay in the existing dependency-free JavaScript client. Both local serving and the Pages builder consume these files.

Before shipping a visual change: inspect the rendered screen, check responsive overflow, exercise filters and selection, verify dialog cancellation and submission states, run quote/ledger tests, and build the static artifact. Test decisions with an isolated ledger, rather than adding QA decisions to the manager’s working ledger.
