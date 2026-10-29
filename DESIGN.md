# Haulage Brain — look, feel, and interaction design

## Direction

**A haunted dispatch desk, in daylight.** Haulage Brain helps a fleet manager understand a route, compare a posted rate with a calculated quote, and make an explicit decision. The interface should feel like a working product within the first ten seconds of a demo.

The Halloween edition uses ivory paper, aubergine ink, burnt-orange accents, an editorial serif masthead, and a real foggy forest-road photograph with a hand-built torch-and-apparition interaction. There are no generated images in the rendered interface. The operational queue and inspector retain clear sans-serif type, opaque surfaces, and semantic pricing colors. Seasonal personality belongs around the work; route, quote, and approval remain literal and easy to read.

## Research and interpretation

Research reviewed on 28 October 2026. The [official Halloween hackathon page](https://youdotcom-oss.github.io/halloween-hack-2026/) pairs orange with deep violet and makes operability a priority. Its Open Haunt category lets teams define their own problem. Our treatment borrows that seasonal palette and sense of atmosphere without turning freight controls into a Halloween game. The page was inspected in the browser because direct web extraction was unavailable. These references informed the design; they do not prove that any particular color palette causes a hackathon win.

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
| Canvas     | `#faf7f1` | Main workspace                           |
| Paper      | `#ffffff` | Queue, metrics, quote card               |
| Ink        | `#302630` | Primary text                             |
| Muted      | `#756d68` | Supporting text                          |
| Line       | `#e7dfd6` | Quiet structure                          |
| Dark       | `#261f29` | Sidebar and primary actions              |
| Lantern    | `#efb48c` | Brand and navigation accents             |
| Pumpkin    | `#ad4e27` | Masthead and review-next action          |
| Green      | `#316b43` | At/above formula quote; approved outcome |
| Green tint | `#eff6e9` | Positive context                         |
| Amber      | `#8c5a19` | Reprice and unknown information          |
| Amber tint | `#fbf1df` | Warning context                          |
| Red        | `#a44137` | Below-quote gap and passed outcome       |
| Red tint   | `#fcf0ed` | Negative context                         |

Use color with a written status. Reserve gradients and translucent glow for the decorative masthead. Keep every data panel opaque; do not place fog, grain, webs, glow, or moving objects over controls or financial values. Avoid strobing, surprise animations, and full-screen effects. The small pricing strip represents the actual distribution of formula signals; it is not a live activity graphic.

### Type and spacing

- System sans stack with Inter if already installed for operational text; Georgia for the seasonal masthead only. No remote font dependency.
- Masthead: approximately 52px desktop / 42–46px mobile, Georgia roman and italic. Operational headings retain the existing sans-serif hierarchy.
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
- The credited photograph is committed as a local JPEG. No runtime image APIs, external fonts, mapping services, or new dependencies are required. `atmosphere.js` and the image are served through the local asset allowlist and copied into the Pages artifact.

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

Source: `src/load_quoting_swarm/web_assets/index.html`, `app.css`, and `app.js`. Design tokens live in CSS `:root`; data and interaction state stay in the existing dependency-free JavaScript client. `atmosphere.js` owns only decorative state and never reads freight data or calls a provider. Both local serving and the Pages builder consume these files.

Before shipping a visual change: inspect the rendered screen, check responsive overflow, exercise filters and selection, verify dialog cancellation and submission states, run quote/ledger tests, and build the static artifact. Test decisions with an isolated ledger, rather than adding QA decisions to the manager’s working ledger.

## Legacy photographic interaction: the graveyard shift

The earlier photographic treatment below is retained for the optional background effects. The newer light zombie-brain masthead and sponsor characters supersede its hero treatment. The legacy scene is a small ghost story embedded in the workspace background. The road photograph, imperfect light, and slow reveal should feel photographic and uncanny. Avoid toy-like 3D props, emoji decoration, visual polish that looks like a generated product render, and random particles.

### Inspiration and acclaim

- [Lusion — Awwwards Site of the Day, 20 May 2019](https://www.awwwards.com/sites/lusion): an awarded reference for direct, real-time interaction. Borrow the principle of a scene responding to a person; the implementation here is original and uses Canvas 2D.
- [The Sleepers, by Thibaut Foussard, documented on Codrops](https://tympanus.net/codrops/2026/07/10/the-sleepers-creating-an-atmospheric-webgl-experience-with-lightweight-techniques/): a useful technical reference for depth, moving noise, and economical atmospheric effects. This is a technique reference, not a claim that our interface or that project won a hackathon.

### The actual interaction

- The hero contains a real monochrome forest-road photograph with two depths of irregular mist. Moving a pointer over the trees carries a soft pool of light and a diffuse light shaft through the fog. A short clearing trail fills back in as the pointer moves away. A distant, indistinct cloaked silhouette appears only as the beam approaches it.
- **Sweep the fog** performs an approximately three-second torch sweep, ending at the apparition. **Look again** repeats the scan. This is a decorative scene, with no API calls and no connection to load recommendations or approval.
- On touch screens, narrow viewports, and reduced-motion settings, the button reveals/resets a still scene immediately. It never forces a moving sequence.
- The same photograph appears very faintly in the outer workspace background. Data panels remain opaque. All canvas decoration has `pointer-events: none`; interactions belong to the explicit scene button, moon, footer clue, and a keyboard Easter egg. The default pointer and all freight controls retain their normal behavior.
- **Atmospheric effects** remains a persistent On / Off / Still control. Turning it off stops both renderers, disables the sweep and Easter-egg buttons, and removes the photographic wash around the workspace. Easter eggs never override this preference. The legacy hero photograph is hidden in the light zombie-brain edition.
- The header renderer pauses when the hero leaves the viewport. The separate page-wide renderer works at every scroll position, wakes only for pointer movement, scrolling, or deliberate summons, and sleeps after its short activity window. Both pause for hidden tabs and dialogs. Each owns one loop capped at 24 frames per second; pixel ratio is capped at 1.5x for the header and 1.25x for page-wide effects. No sound, flashing, strobing, sudden full-screen changes, scroll hijacking, or click interception.
- Missing canvas support or blocked storage must not affect the loadboard. A missing canvas disables the decorative scan. Browser-demo and synthetic-data labels stay visible at narrow breakpoints.

### Photograph and license

Asset: `src/load_quoting_swarm/web_assets/haunted-road.jpg`, 1800 × 1800, approximately 578 KiB. **A road through a foggy forest with tall trees**, by **JOHN TOWNER**, published 2 August 2016, photographed on a Sony ILCE-7M2.

- [Original photo and photographer credit](https://unsplash.com/photos/a-road-through-a-foggy-forest-with-tall-trees-d7y2-B0_TRU)
- [Unsplash License](https://unsplash.com/license): permits downloading and using the photo, including in commercial projects. It is included here as a local project asset, not fetched from a third-party service at runtime.
- Display treatment: CSS monochrome and contrast, responsive crop, plus original procedural fog, light, and silhouette overlays. The photograph itself is preserved as downloaded.
- The legacy forest scene imagery is photographic. The silhouette, fog, light shaft, and short clearing trail are original procedural overlays.

Atmosphere lifecycle checks: `node --test tests/atmosphere.test.cjs`. These verify a single owned animation loop, pause/resume boundaries, an explicit reveal, static touch/reduced-motion behavior, persistence, and unavailable browser capabilities without calling providers.

### Page-wide Easter eggs

`easter-eggs.js` adds small discoveries throughout the workspace:

- Pointer-controlled light moves through the photographic background around opaque work surfaces. A distant figure peeks around the loadboard’s outer edge when the light approaches it.
- Scrolling leaves a few fading boot prints in the outside gutter. They never cross rows, values, or buttons.
- Hovering the brand can wake a spider that descends into empty navigation space. Its thread and legs remain outside the navigation items and sidebar copy.
- The sidebar moon and **Still here?** footer clue deliberately wake the visitors. Typing **BOO** outside editable fields is an additional shortcut. Modified key chords, text fields, contenteditable regions, and open dialogs are excluded.
- With reduced motion, touch, or narrow screens, explicit summons render a still composition. There is no automatic chase or moving drop on these devices.
- The background canvas is below the main content; the spider’s foreground canvas draws only in measured navigation whitespace. Both ignore pointer events. Light mode, native scrolling, search, manager entry, and approval flow stay operational.


## Closed-loop, AI-native workspace (28 October update)

Spooky Brain is the main identity: a realistic, tactile zombie-brain cutout leads a compact light masthead and the large chat header. A sage/ivory conversation panel sits beside the loop schematic on desktop and above it on mobile. The left rail is light, filled with section links, current fleet totals, an interactive avatar and a link to the haunted lay-by. Lower work areas have direct anchors; six-row loadboard pagination lets the page scroll naturally instead of trapping the user in an 89-row list.

Conversation now calls Parasail for structured intent and for an explanation of the solver’s result. The bounded route solver remains the authority for routes, timings, costs and limits. Applied extra constraints appear as removable chips. Clarifications and provider failures keep the last valid plan, with editable requests available for retry. Static Pages deployments explicitly require a backend for AI chat and retain only labelled precomputed route previews.

Five dimensional creature cutouts on pastel cards replace the repeated dark forest: AWS pumpkin/cloud station, CrewAI web-weaving spider, You.com ghost with a searching magnifying glass, Parasail thinking zombie, and One skeleton hand above an approval letter. Actual service events set written working/completed/failed states. Hover/focus wakes the local illustration without changing its service state. The model-thinking avatar and activity text show AI requests in progress. The mathematical tools and safety gate have their own spellbook and lock illustrations in the trace dialog.

The lower haunted lay-by provides a local three-character stowaway hunt, with shared progress shown in the sidebar. Brain pokes and the hunt never call a service or change any freight state. Preserve reduced-motion, offscreen and hidden-tab animation handling. Synthetic data, schematic routing, estimates, replay labels and human-review requirements remain explicit.


### Realistic creature pass

The zombie portrait and five provider presentations use alpha-preserving, locally served WebP cutouts with practical-effects material detail: wrinkled silicone, fine spider hairs and silk, frayed gauze, aged pumpkin skin, scratched brass and weathered bone. The zombie asset is shared by the avatar and Parasail. Keep provider names and status labels on a clear layer above and outside the art. Never darken the work surfaces to make the creatures visible.

Pointer input moves only the creature layers through a bounded, shared smoothing loop. Web sway/weaving, ghost drift/wisps, brain breathing/neural rings, warm candle glow and a deliberate stamping gesture remain distinct. Keyboard focus and taps have a local decorative response. Working states still follow the real service trace; hovering or inspecting a character never starts a provider call. Reduce motion, effects-off, hidden tabs, offscreen scenes and dialog occlusion all stop the appropriate motion. Prompts and asset destinations are recorded in `docs/creature-assets.md`.


### Reply readability and avatar alignment

The assistant’s answer is structured as a short overview, a three-column totals strip and one compact card per vehicle. Each card shows its loop, UK home time, loaded/empty miles and estimated surplus, sourced from the checked solver payload. Longer reasoning and cost/load-ID details use native disclosures. AI text is escaped before the limited Markdown formatting is applied. The conversation opens at the start of a new answer instead of scrolling directly to its last line.

The masthead uses two explicit grid columns, with the portrait sized to its column at every breakpoint. The chat header similarly reserves a fixed avatar slot and centers the image and two-line title block. This removes the former 175px image overflowing a 130px medium-width container.
