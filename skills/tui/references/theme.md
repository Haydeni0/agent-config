# TUI theme and taste

The concrete look and interaction grammar this user has accepted, plus the taste rules behind them. Grounded in three accepted TUIs (lab_tui - the origin of this look, the cwutils "cw slurm tui" - the reference build, and the slurm-llm metrics-tui), all Python + Textual + rich. Default stack: Python + Textual + rich, matching all accepted builds; deviate only when the host project's language forces it - then port the principles, not the library calls. The values are portable: the palette and the rules apply to any TUI in any language; the hexes are the user's established cross-TUI preference.

## One fixed look

A single theme module owns every colour. No literal colour string survives outside it - hold this with a grep check over views, panels, and app code. The user explicitly rejected a theme switcher, and the metrics-tui deliberately repeats the cwutils palette. Port this look; do not design a new one.

The palette is truecolor hexes. Before shipping, verify the target terminals actually render truecolor - a one-line probe, or ask the user which terminals matter. Detect depth from the environment, never from TERM alone: COLORTERM=truecolor advertises 24-bit, and a modern terminal with a stale TERM reports far less than it supports. Honor NO_COLOR when present and non-empty (an empty value does not count) by dropping added colour while keeping bold/underline. If a target is 256-color, downsample hexes to the nearest 256-color slot inside the theme module - degrade by nearest-color mapping tier by tier (24-bit -> 256 -> 16), never by dropping styles wholesale - so views and goldens never change.

### Base palette (GitHub-dark derived)

| Constant | Hex | Role |
|---|---|---|
| BG | #0d1117 | Screen background |
| BAR_BG | #161b22 | Footer bar background |
| BRIGHT | #e6edf3 | Box titles; headline numbers and table headers (bold) |
| (body) | terminal default fg | Body text - no constant owns it |
| DIM | #8b949e | Muted/secondary text, footer hints, secondary rows |
| FAINT | #484f58 | Axis furniture, n/a dashes, gutters |
| TRACK | #30363d | Empty meter run, table rules - near-invisible structure |
| SELECTION_BG | #1f2a3a | Selected row background (see open questions) |

Headline numbers render bold with DIM labels ("286 jobs" is the number bold, the unit dim). The accepted builds split the roles one way only: where the number carries a colour it is BRIGHT #e6edf3 (metrics-tui headline pairs and table headers), and cwutils panels bold it at the terminal-default foreground with no hex. There is no second headline constant - never introduce one.

### Accents (semantic)

| Constant | Hex | Meaning |
|---|---|---|
| GREEN | #3fb950 | primary view accent; success-ish/calm states |
| MINT | #7ee787 | INFO log level; meter gradient step |
| VIOLET | #d2a8ff | secondary view accent (nodes, serve) |
| BLUE | #58a6ff | tertiary view accent (usage, users) |
| ORANGE | #f0883e | history/quaternary view; hot = in-use/computed; numbers in logs |
| YELLOW | #d29922 | logs view; WARN; stale-data note |
| SKY | #79c0ff | detail views; log timestamps |
| RED | #f85149 | error borders, failures; ERROR (bold) |

The accent system is per-view: each view gets one accent that colours its summary-panel border, its hotkey digit, and the main box border while it is shown. Panel identity is colour, not position alone. Series colours are reused for the same names in tables so charts and tables read as one system - two series sharing a colour reads as noise, and the user notices and reports it.

### Distinctness is asserted, not eyeballed

Named ANSI colours collide at render time (one terminal mapped red, magenta, and bright_magenta all to #f4005f), so name-level distinctness tests passed while chart bands painted identically. Resolve every colour name to an explicit theme hex and test the resolved RGB; validate palette distinctness with CIE76 deltaE (threshold 8 for glance-separable, measured against the chart background too). Apply the monochrome test to the whole design: if stripping all colour makes the layout unreadable, colour was carrying structure alone - it must reinforce meaning, never be its only carrier.

## Meters

- Solid runs of "■" glyphs, graded cell-by-cell calm-to-hot along METER_GRADIENT = (GREEN, MINT, YELLOW, ORANGE, RED). Any nonzero fraction keeps one filled cell; empty runs sit on TRACK; a zero total shows faint "n/a" dashes.
- Meters are honest. An uncapped quantity has no fraction, so drawing any bar is fake data - render it as plain muted text with a count ("normal 0 (uncapped)"). No empty bars for absent resources: a cluster with no GPUs shows no GPU bar.
- On a usage bar the numbers win over the label: shorten a long resource name so the used/cap numbers are never cut off.

## Charts

- Hand-drawn primitives as rich Text, no chart library. In the source builds plotext cost ~614ms per build on the event loop vs ~25ms hand-rolled; plotting libraries that write to stdout fight a framework render loop.
- Solid stacked area, sub-cell stacked: half-block glyphs (U+2580/2584) doubling vertical resolution, or eighth-block glyphs with background-filled spaces (solid in every font, where stacked full blocks can leave seams). Pair a glyph in the foreground with the next series as the background. Never gap-riddled brick cells.
- Stack order = legend order, sorted by name bottom-up - deterministic and refresh-stable, so band positions never jump between refreshes. Small series fold into one "other" band ranked by window total, not current value.
- Y-axis pinned at capacity (an auto-scale bug in the prototype became a named regression test); the user cut the y-auto toggle as speculative.
- Furniture: dotted/dashed faint gridlines only in empty cells, dim axis labels, spaced x ticks with label-width + 2 cells of daylight from the pinned end tick, newest point at the right edge, peak stated in the panel title, a "now" marker, and a legend of colour swatches with latest values ("██ foundry 80 gpus").
- An uninformative chart gets redesigned, not patched: a flickery KV line was rebuilt into a stacked composition bar (in-use ORANGE / cached GREEN / free) after verifying the live invariant that the three parts sum to the total.

### Series palettes (both accepted, verbatim)

Two accepted multi-series palettes; which one a given project uses is open question 1. Slot order is fixed and cycles.

- 11-slot colourblind-friendly (cwutils history chart): #79c0ff, #f85149, #3fb950, #d2a8ff, #58a6ff, #e6edf3, #f0883e, #8b949e, then the first, second, and seventh slots blended 40% toward white as the close-out bright variants: #afd9ff, #fb9792, #f6b88b.
- 8-slot distinct-hues-first (metrics-tui): #79c0ff, #f0883e, #d2a8ff, #3fb950, #d29922, #f85149, #7ee787, #58a6ff.

## Logs (when the TUI has a logs view)

- bat-style highlighting mirroring bat's OneHalfDark theme, resolved to the same hexes as the CLI highlighter so both render identically: ERROR #f85149 bold, WARN #d29922, INFO #7ee787, numbers #f0883e, plus dates, quoted strings, IPs, URLs, paths, key=value pairs.
- Typed gutter: muted line numbers, timestamps #79c0ff, coloured level tokens, plain message body, a dim "│" column separator.
- Whether a given TUI needs a logs view at all is per-tool - ask (see open questions).

## Layout and geometry

- Fixed geometry: a fixed-width left summary column (~30 cells) of stacked clickable panels beside one main box. Panel N summarises what view N shows - the user polices this mapping.
- Rounded bordered boxes per panel (btop-style), each with one accent border colour; titles ride border_title/border_subtitle so they cost no content line.
- Hotkey digits ride the box titles as superscripts in the view's accent colour, glued to a bold bright name (¹jobs, ²nodes). Never duplicate digit hints in the footer.
- One-line footer bar on BAR_BG #161b22: contextual keybindings in DIM, changing per view/state, always present, never more than one line. Armed esc replaces the hints with "esc again to quit". Hints that do not fit drop whole from the end, never truncated mid-hint.
- Density is deliberately high: sidebar panels compress a whole subsystem into 3-5 lines, detail panes are full-bleed dense tables/charts, no padding whitespace beyond single-row separation. Every cell of the terminal earns its place - fill blank space with data (right column when wide, stacked below when narrow).
- Tables: heavy box-drawing chrome (┏━━┳┓ header frame, ┡━━╇┩ separator) in TRACK so data dominates; bold BRIGHT headers; numeric columns right-aligned; truncation with a single "…".
- Fixed-width side panels reflow, never widen or crop: widening only moves the cliff and steals main-box width; reflow degrades gracefully at any width.
- Detail views are indented key-value prose, not nested tables: an identity line, then indented facts with two-space nesting, no borders inside the body.
- Loading state: a single plain "fetching..." placeholder in the panel body - no spinner, no blank screen.
- Error state: only the failing panel's border flips to RED with an actionable one-liner; last-known data stays. No modal, no crash, no clearing of the rest of the screen.
- Filter mode is an overlay: a top box titled 'filter' (ORANGE border) with the "/ <query>" prompt and block cursor ▏, live match count in the box's bottom border, filtered table below, footer hints swapped to commit/cancel. Typing mode swallows all printable keys - q and j type letters, they never quit or move. Every match gets an ORANGE ground highlight in every cell it hits; a hit past the truncation cut slides the text window so it shows. escape clears a committed filter in one press, no / re-entry owed.
- The terminal width never reaches the data layer (see methodology.md, Architecture that worked).

## Interaction model

The grammar is lazygit-style:

- Digit keys switch views; the digit is advertised on the panel title, never in the footer.
- j/k move selection (vim-style); in views without a selection (detail, tree) they scroll the pane - the key always visibly does something. enter opens detail, enter again opens logs; r forces refresh; q quits; / opens the typed filter (live-filtering while typing, suspends all other keys until enter/esc); single letters toggle splits (s state filter, u mine/all, m panels or rows). A new split dimension reuses the same single-letter toggle pattern, and where two related actions need keys, uppercase is the stronger or more deliberate variant of the lowercase one (lazygit's r/R, d/D convention).
- esc backs out exactly one level per press (logs -> detail -> filter -> top). At top level it arms a double-esc quit (~1.5s window) and never switches views - a no-op esc reads as broken.
- No passthrough CLI arguments - the user rejected them outright. All filtering is client-side hotkeys over the cached full list: instant, never a refetch.
- Auto-refresh on a fixed-cadence tick (~5s, tuned per data source drift); every fetch runs in the background so keys stay instant even mid-fetch; dormant views fetch lazily and caches survive view switches.
- Keyboard-first is the contract: every action is reachable by keys, and no feature may depend on the mouse. Treat mouse strictly as optional enhancement. When the tool has it: clicking a panel switches to its view; clicking a row selects it; clicking the selected row again opens it; clicks on headers or empty space do nothing; wheel scrolls. Handlers translate positions to targets only and dispatch to the SAME action the keys use - never a second code path. Mouse is a per-tool decision the user makes explicitly, not a default.
- Compatibility with multiplexer panes AND bare terminals is a requirement the user checks.

## The user's taste rules

1. One fixed look; theme fidelity beats framework defaults. The user rejected a clean rebuild's default look for a throwaway prototype's theme, twice, across two projects.
2. Numbered views, digits on the titles as superscripts, not "[1]" brackets, not in the footer.
3. The TUI is an interactive view of the existing commands, not a parallel presentation: same defaults, ordering, columns, numbers. Parity holds by construction - one shared derivation consumed by both renderers, never two hand-synced renderings.
4. Never render fake data; unknowns get an explicit quiet marker (dim "…", the raw number, "(unattributed)" sorted last).
5. Every key must visibly do something.
6. Cross-view consistency is policed by the user - numbers must match between panels, and colour reuse across different things reads as noise.
7. Uniform visual language across panels; reverting a view that dropped the bars the other views have.
8. Performance is a taste dimension; plaintext is an acceptable price for speed (a measured ~10x win - 2.43s to 0.25s - traded away JSON parsing without hesitation).
9. The agent must self-review visually, from the user's seat - screenshot, play with it, critique as a human would.
10. Prototype first; iterate on reactions, not on specs.
11. Cut speculative flexibility: no passthrough args, no y-auto toggle, no theme switcher.
12. The agent is invited to exceed the brief on visuals ("nicer visuals, more modern graphics - feel free"), but bad charts get blunt verdicts and redesigns.
13. One design question at a time to the user, each with a recommendation; the user vetoes or approves tersely ("ok, looks good").
14. Verdicts arrive as verdict+nit pairs; local formatting flaws do not sink an approved whole.
15. Scope stays tight; deferrals are explicit ("leave it out for the moment"). Feature scope is per-TUI and deliberate.
16. Autonomy is granted after the agent verifies safety (read-only confirmed, isolated stack).
17. Multiplexer and bare-terminal compatibility is demanded, and the user probes test realism ("this will work in normal terminals too right?").
18. Minimal churn over config churn (manual nocache workaround over cache-busting machinery).
19. Approval is cautious and probing, not gushing: "looks great" arrives with architecture questions (how much state does it hold? how does it scale?). The accepted dashboards are read-only views with in-memory state only - no key writes to disk. Answer state and scale questions with facts and experiments, never prose (see methodology.md, The iterate loop).
20. Speculative polish is declined once the current design looks good ("fine for now") - offer redesign forks only with concrete evidence the current thing breaks at real sizes, and accept a deferral without lobbying.

## Open questions - ask the user, one at a time, with a recommendation

The evidence does not settle these. Per rule 13, present each as one question with a recommendation.

1. Series palette choice for a new multi-series chart. Both accepted tuples are recorded verbatim under Charts (Series palettes): ask which one - 11-slot colourblind-friendly or 8-slot distinct-hues-first. The settled requirement is distinct, stable, deterministic, colourblind-checkable.
2. Selected-row appearance: a subtle SELECTION_BG row lift (#1f2a3a), optionally plus a coloured "▌" bar in column 0 in the view's accent (lab_tui; the lift is applied beneath the row's own spans so a search hit keeps its ground on the selected row), vs reverse video. The settled constraint: a row-level style, never an injected ">" byte (injected bytes break parity with the command render).
3. Mouse default for a new TUI: asked-for in one tool, deliberately excluded from another. Ask per project.
4. Chart glyph scheme: half-block vs eighth-block-plus-background-fill. Both approved; settled constraints are solid fill, sub-cell stacking, deterministic band order, swatched legend, faint gridlines, pinned or nice-numbered ceilings.
5. Footer boundary: what belongs in the footer vs on the boxes - digit hints were cut as redundant, but the general rule was never stated.
6. Whether this TUI needs a logs view at all, and which grammar classes matter most.
7. Refresh cadence numbers: the principle (keys instant, background fetch, TTL per drift rate) is settled; the numbers are per data source.
8. Panel count and sidebar width per tool. Settled: panel N mirrors view N, every cell earns its place.
9. Whether the existing styling of the TUI being extended is settled or should be reworked toward this theme. Do not assume the current look of any TUI is the ceiling - the user has reworked an existing TUI toward this look before. This file is that look, distilled: port it as-is and ask only about deltas from it, never about locating an external design doc.
