# TUI methodology

The full iterate loop, testing harness patterns, performance rules, and pitfalls, mined from three converged TUI builds (lab_tui, cwutils "cw slurm tui", and slurm-llm metrics-tui). Commands and library names are the actual ones from those builds (Python + Textual + rich); the principles are portable, and the framework-specific traps say so.

## The iterate loop

The two large builds converged on this shape independently; the single-file build (see Scaling the loop to the build) is the scaled-down version of the same loop.

**Step 0 - Investigate before designing.** Screenshot the current state of the thing being extended (or the closest existing UI), enumerate the actual data values the views will group by (status codes, user agents, models, users), and read any reference design record - including copying its screenshot method. Mine existing taste verdicts before inventing anything.

**Step 1 - Prototype first, throwaway, human reacts.** Look and feel is human judgement: settle it on a throwaway single-file artifact against live data before any spec. Nothing graduates from the prototype - only recorded taste verdicts do. A clean rebuild that said only "TUI-idiomatic palette/chrome" in its spec lost the prototype's look entirely: the visual contract (palette hexes, box borders, bars, meters, selection treatment) must be pinned explicitly in the spec or it never carries over.

**Step 2 - Code-facts inventory before planning.** Extract module seams, gotchas, missing error handlers, and library hazards from the existing codebase before the plan is authored (e.g. "plotext writes to sys.stdout + global state - the history chart cannot drop into a Textual app without a chart_stream seam"). Settle strict layering upfront: fetch+parse at the bottom, pure math above, pure renderers above that, the app as a thin shell.

**Step 3 - Decisions and scenarios as law.** Before implementation: a decisions record - design-log D entries in the `.agents/work/<slug>/` package, per the work-package skill's format - where every settled choice gets a stable ID (never re-litigate), and numbered acceptance scenarios with a coverage map (scenario -> task -> named test). Every user-visible behavior gets a requirement with a verification pointer; work is not done until the cited verification actually runs.

**Step 4 - Plan, reviewed by running it.** A fresh subagent (clean context) writes the plan; separate reviewer subagents rebuild and RUN the plan's embedded code in a sandbox before implementation - in the source builds the spec's two review rounds caught one escalated HIGH finding plus eight smaller issues, and the plan review ran to its round cap with the final round finding only lint errors, all before any production code existed. Task shape that worked: exact files touched, interfaces with exact signatures, blocked-by deps, steps each naming the command, expected output, and expected failure mode; deviations recorded inline, never silent. The user is a plan-approval gate before any code.

**Step 5 - Prefactors with byte-identity proof.** Where the TUI mirrors an existing command, promote the command's render builders to public names (pure renames) first so views build on the command's own builders. Safety proof: existing goldens stay byte-identical - a golden diff during a rename is a bug.

**Step 6 - Implementation in dependency-ordered waves, red-first TDD.** Waves ordered by a task dependency graph (prefactors+deps, first view, remaining views, details+panels, app shell, interactions, final gates). Every unit: write failing tests, run to verify failure with the named error (the expected import error for new modules; the pre-fix symptom bytes for behavior changes), implement, verify pass. Bug fixes invert the bug-encoding test to prove it catches the bug, and ship as commit pairs (red test + fix) so regressions cannot return silently.

**Step 7 - Human-in-the-loop taste checkpoints.** Three mechanisms:
- *Live preview worktree*: a detached snapshot worktree at final HEAD, advanced after every fix wave, so the human runs the real TUI live between passes while half-finished edits cannot break their session. Every user-reported bug in one build came from using this preview.
- *Screenshot passes*: after each wave, capture a full set (PNG+SVG+TXT per shot) at fixed sizes (160x45 and 120x40), including narrow twins and error states; the human's visual verdict gates the next phase. Code review is HELD until visual passes settle.
- *Role split*: the implementer never judges look and feel; the visual gate belongs to an overseer or the human, judging against the settled prototype reference.

**Step 8 - Live-behavior verification with a real throwaway workload.** Verify dynamics the way a user experiences them: a dummy job writing stdout/stderr every 2 seconds to confirm log following against `tail -f`; a held job released to watch a state transition; an exactly-once delivery check. Always on isolated/throwaway infrastructure, never prod.

**Scaling questions get experiments, not prose.** When the user asks "how does this expand if we serve/track N times more?", simulate the bigger world with fixture data (e.g. 5 models x 2 replicas, no network), screenshot at the target sizes, and report the concrete breakages: which panel clips, which legend truncates, where palette colours start repeating, what the row order does at N rows. The user then decides with evidence whether any of it matters now - often the verdict is "fine for now", and that deferral ends the fork (see theme.md, taste rule 20).

**Step 9 - Measure-first perf phases.** Any perf work starts read-only measurement; numbers are reported before choosing a fix, and the ruling goes to the human with data in hand.

**Step 10 - Bounded bug hunts.** A bug that resists reproduction gets a bounded budget (two attempts: an exhaustive deterministic input matrix, then one live E2E at higher capture density), then closure with the negative evidence recorded - no keeper tests pinning a frame that cannot be produced, no blind fix.

**Step 11 - Release smoke in a real pty.** A release requires a live run of every view against the real system, each view's frame dumped from a real pty, one number per view spot-checked against the raw underlying source. Any failure stops the release.

## Testing a TUI

Five layers, each catching a bug class the layer above cannot. The most repeated lesson in the evidence: simulated-input tests pass while the real terminal is broken, so the top layers are mandatory, not optional.

**Layer 1 - Pure-render golden tests (the core oracle).** Views and panels are pure functions: typed models + view state (+ width) -> rich Text. Pin `.plain` bytes byte-exact against golden .txt files; assert colours separately via `.spans` so a theme change is span-only and byte-identity proves no layout regression. Positional style claims (a meter's per-cell gradient, a hit ground surviving on the selected row) are verified at cell level via `Text.get_style_at_offset`. Regenerate deliberately (e.g. GOLDEN_UPDATE=1) and review the diff like code. Every change requires pre-existing goldens stay byte-identical. Determinism seams from the start: injectable clock, a `now=` parameter on view functions, a pinned clock for display-layer `time.time()` so elapsed columns never flake. Capture goldens from real live payloads. Where a TUI mirrors a CLI command, a render-parity contract holds the TUI byte-identical to the command output users know.

The same purity covers the readers under the views: one small reader per source file, returning parsed frozen dataclasses, an explicit Absent marker, or raising a named shape error. A reader refuses a shape-changed source (raise naming the file and the expected shape) instead of rendering blank or wrong cells; pin every shape break - missing file, renamed header, dropped cell, bad date, unknown enum value - with a `pytest.raises` match test. Error containment is per-scope: a broken screen-level source replaces only its own box with the error view, a broken row-level source replaces only its own row or section, and nothing else on screen clears.

**Layer 2 - Headless Pilot for flows only.** Textual's `app.run_test(size=(160,45))` drives key chains, view switches, quit, fault handling - flow scenarios only, never rendering assertions. Assert on a public `app.rendered` dict (box id -> last-rendered Text) rather than widget internals. Gotchas: stub discovery so the first tick cannot block on a real subprocess call; plain-text assertions cannot see background-filled cells; a test pinning relayout to a fixed number of `pilot.pause()`s is itself a race - wait for the observable condition in a bounded loop. Crucially, Pilot synthesizes keys differently from a real terminal (`Pilot.press("enter")` sends character None where a real terminal sends `\r`), so Pilot-green does not prove the keyboard works. One rendering assertion earns its place at this layer: a full-screen pin - read the compositor's rendered strips (no public text export, so the framework version is pinned) and pin the whole screen line-for-line at one size, masking environment-dependent cells - which catches shell and layout wiring the per-panel goldens cannot. It supplements Layer 1, never replaces it.

**Layer 3 - Real-parser tests with raw bytes.** Feed raw byte sequences through the terminal driver's real parser (Textual's XTermParser): pin the real parser's event mapping, then drive dispatch with actual bytes including split-delivery shapes. A lone ESC only flushes on a follow-up empty `feed("")` - the harness must feed the flush or ESC never arrives. Mouse: raw SGR byte sequences through the parser, plus inertness guards asserting chrome/footer clicks do nothing. Feed control-byte sequences to text input handlers to prove non-printables cannot enter a filter query.

**Layer 4 - Real-pty keeper tests - the layer that catches what nothing else can.** Three proven harness shapes:
- *tmux*: `tmux new-session -d -x 160 -y 45`, drive with `tmux send-keys` (or `-H` for raw hex bytes, e.g. SGR mouse), assert with `tmux capture-pane -p` (`-e` to see escape/selection bytes), `tmux pipe-pane` for byte-stream capture, capture loops at 0.25s intervals to watch transitions frame by frame.
- *bare pty*: `pty.openpty()`, `TIOCSWINSZ` to the test size, TERM=xterm-256color, `start_new_session`; a child script records received key/click events to JSONL; the parent drains the master fd while polling the record file with bounded timeouts, writes raw bytes deliberately split at a gap constant (so the test re-pins itself when the constant changes), asserts event order. `setwinsize` mid-session is how this harness delivers the resize/SIGWINCH path.
- *pexpect + pyte*: spawn on a pty (pin the size via `dimensions=`), drive with send/expect, and feed the raw output stream into the pyte screen model for position- and cell-level assertions when tmux is not available or capture-pane's text-only view is not enough. Prefer `expect_exact` for fixed strings; avoid trailing-wildcard patterns (pexpect matches minimally against the stream).

Pty traps: an undrained master fills the kernel buffer and `proc.wait()` hangs forever - drain while polling; a non-tty child detects width 80 and renders a smaller frame - set COLUMNS/LINES or verify width per run; subclassing the app and overriding `on_mount` makes the framework's MRO dispatch run the handler twice; a raw pty ANSI strip cannot recover the framework's cursor-addressed repaints, so use that mode for key-flow evidence only, never content verification.

**Layer 5 - E2E against the real system.** Drive the real TUI headless against a real scrape of a throwaway stack and press the key; check the rendered output concretely. Use negative controls: remove the one config line, replay, watch the label degrade - proving the setting is load-bearing. Fault-injection doubles pin the failure contract: per-source fault injection (method names validated so typos fail loudly) asserting one broken source renders an in-place error note while every other box keeps last-known data. Every unwired method on a test double can silently shell out to the LIVE system - wire every method the code under test calls. Test doubles replay real captured payloads, never synthetic shapes.

### Screenshot/SVG capture pipeline

1. Headless pilot drives the real app; wait until every source key has landed values (poll the fetch cache, bounded) so no shot contains a "fetching" placeholder frame; grep all TXT dumps for zero fetching/loading strings.
2. Export SVG via `app.export_screenshot()` / `save_screenshot()`; a plain-text compositor render for TXT; `cairosvg.svg2png` for PNG (e.g. `uv run --with cairosvg==2.9.1`). Save all three formats per shot so content is verifiable without vision.
3. Force the font before rasterizing: a FONTCONFIG_FILE fonts.conf remapping every family to a known monospace font (DejaVu Sans Mono). Without this, the default fontconfig falls to a ~1.37x-cell fallback and misrepresents layout. The lighter alternative when rasterizing via cairosvg: rewrite the SVG's font-family to plain monospace first (cairo falls back to a proportional face and breaks the column grid).
4. Run a font probe first: verify meter/block glyphs (■/█/░, half-blocks, dotted gridlines) advance 1:1 with 'M' and ink exactly the expected cells.
5. Shoot every view at the primary size plus narrow twins and toggle variants; stage true degraded states deliberately (a failing subclass where only one source raises) but never fabricate data.
6. Verify below the PNG: grep SVG fills for exact per-view hex colours and bold flags; run a PNG colour census against expected hexes when there is no vision backend; keep TXT dumps as byte-truth.
7. Before a whole-screen capture over a pty, wait for output to go idle (rendering is asynchronous) and disable cursor blink and other animations in captures. Known capture artifacts are not bugs to chase: thin dark lines across chart areas come from the PNG rasterizer's font, not from real terminals.
8. The capture can live in the app itself: a `--screenshot file.svg|png [--keys j,enter] [--size CxR]` flag that runs the app headless (`run_test` + `export_screenshot`) makes every shot a one-liner with no external harness. Off-the-shelf alternatives: pytest-textual-snapshot (`snap_compare` with `terminal_size`, HTML side-by-side review, `--snapshot-update` only after inspecting the report) for stored SVG snapshots; `freeze --execute "my-tui ..."` renders any command's ANSI output to PNG/SVG when the app cannot export its own.

**Vision review when available:** a vision-capable agent reads the PNGs, critiques them as a human would, compares side-by-side with the prototype, sends concrete fixes, reshoots. Without vision, the programmatic mode (SVG fills, colour census, TXT dumps) also produced accepted results. Screenshots must be taken and reviewed either way.

**Test-sensitivity discipline.** Prove a new test pins its bug: mutation-check by temporarily breaking the code (restore naive math, disable the guard, inject a sleep into the render path) and watch the test go red, then revert. Derive expectations by reading state off the mounted widget (the row the user SAW), never by recomputing indices from the same state. A red test that pins nothing distinct gets removed rather than kept as theater. Red evidence must be real, not asserted.

## Performance

**Performance is a gate, not a hope.** Budgets are pinned as tests in a perf module run as part of the suite - a regression fails CI rather than being noticed by the user. The budget set that converged (a starting point, not a law - re-measure on your box):

| Budget | Threshold |
|---|---|
| Navigation keypress render | <= 5ms |
| Mouse click / wheel | <= 5ms |
| View switch / data-refresh render | <= 50ms |
| Logs drain+render per tick (full 10k scrollback) | <= 10ms |
| Logs open-to-first-paint | <= 150ms |
| Import chain | <= 600ms |
| Mount + first paint | <= 250ms |

**Frame and idle discipline:** redraw on events and ticks, never a spin loop (a draw call in an unconditional loop pins a core). Data cadence and frame cadence are independent knobs - data polls at its own per-source TTL while frames render only when something changed. An idle dashboard must cost ~0 CPU; anything higher is a redraw loop, an animation or cursor-blink timer keeping the frame timer hot, or a poll re-rendering unchanged data - treat it as a leak, pin it, and disable animations in long-lived dashboards (e.g. TEXTUAL_ANIMATIONS=NONE).

**Measurement methodology that made the numbers trustworthy:**
- Measure in a real pty (or real headless app) at the primary size against live-shaped fixtures - 240 jobs, 42 nodes, 10k-row scrollback - never synthetic shapes. A synthetic full-canvas spike reported 577ms for a chart that renders in 45ms at the real shape.
- Real command, real pty, n>=6 per batch, medians reported; unmodified and instrumented runs must agree (~20ms) before numbers are trusted.
- Assert the MEDIAN of 9 samples, never max - async ops interleave with the refresh tick so max is noise. Discard the first 2 samples; retry once on overage, both levers centralized in one assert helper.
- Hardware calibration: CI runners were 3-4x slower. Fix is a measured hw_factor - a deterministic pure reference workload measured per session, median / pinned constant, clamped >= 1.0 - multiplied into every budget. Never loosen constants, never skip.
- Prove the harness works by injecting a synthetic regression (a sleep in the render path) and watching budget tests go red; after hardening, re-run the injection - the fix must survive its own discovery method. A retry that re-samples warm render memos can let an injected cold-build regression pass attempt 2 - evict memo entries at the top of every attempt.
- A perf test must assert the action actually changed state: a click budget that clicked already-selected rows no-op'd, measured ~0.00ms, and passed while measuring nothing.
- Measure on a quiet box; a load spike contaminated readings ~2x - hold runs behind a load watcher and discard contaminated readings.
- Prefer structural shape-guards over wall-clock where possible: assert builder call-counts via a wrapping patch at the public seam - deterministic and immune to machine speed.
- Measure interactivity as burst-settle: send 60 j presses, measure wall time until the pane shows the scrolled window with the selection.

**What actually made it fast (each fix followed a measurement naming the dominant phase):**
- Measure before optimizing, every time. Three separate profile-first phases overturned the proposed fix: a history wall was 78% backend fetch and render only 1.7%, so a chart rewrite was closed won't-fix-per-measurement.
- Render cache keyed on data revision. A selection move rebuilt the full 200-row table per keypress (~63ms, felt directly). Fix: memoize the flattened render keyed on each box's own source revisions; a selection move re-aims a window over cached lines and applies highlight as a style-only pass (~1.75ms). Bound the LRU (~3x the largest working set).
- Fixed-width columns. The table library skips per-cell width measurement only when column width is set; `min_width=max_width` columns pay a full measure over every cell. Switching was byte-identical and cut a 240-row rebuild ~40%.
- Paint expensive content at ingest, never per render: log lines are tokenized once when they enter the scrollback; every render only windows pre-painted rows.
- Progressive paint: render immediately when each fetch lands instead of waiting for the tick's gather; never-landed data renders dim placeholder cells rather than gating the view; an error keeps an explicit note, never a silent fallback.
- No blocking I/O on the event loop: all fetches and file parsing via a thread-offload helper with singleflight (in-flight keys skipped); TTL per source tuned to real change rates; a failed fetch keeps last-known data and retries at its own TTL; an r key busts all TTLs on demand. A ~1.7MB parse (0.2s or more per tick) made ticks run late - fix with off-loop parsing plus fixed-cadence `sleep(max(0, interval - elapsed))` so the time axis holds.
- Zero-call caching where the data permits it: cache keyed on quantities that change only at restart; a query-shape change validated by a live parity probe before coding.
- Startup as its own UX feature: measure import time decomposition (`python -X importtime -c "import yourapp"` names the dominant imports to defer), progressive paint, opening view first, deferred slow fetches, lazy imports - each change measured against the import/mount budgets. Never block first paint on data: mount the shell, render placeholders, fire the fetches after.
- Split first paint from backfill: logs open does one shallow read (40 lines) and paints immediately; the deep scrollback backfill runs as an off-loop task.

## Pitfalls

**The simulated-input trap (the most expensive recurring bug class).** Pilot's press sends character None; a real terminal sends `\r`. An app dispatching on `event.character` was Enter-dead in every real terminal while all Pilot tests passed - the human caught it in the preview. Fix pattern: dispatch on key names, test with real parser byte sequences, and keep real-pty verification sweeps per key. The same shape hit mouse: every click test started after a click had already reached the app, so broken mouse-reporting setup was invisible to all tests.

**Escape-sequence and ESCDELAY handling.** Multiplexers can deliver the two halves of an SGR mouse sequence in separate writes >100ms apart; a default 100ms ESC delay then parses it as Esc plus coordinate digits, which hit digit hotkeys and snapped views. Fix: raise the escape delay (e.g. `os.environ.setdefault("ESCDELAY", "1000")`, measured worst-case x1.5-2 with a 500ms floor) - and set it in the package `__init__` before the framework reads it, so the launcher import order cannot defeat it. Traps: the raise trades lone-ESC latency (back-outs feel delayed up to 1s) and must stay below the double-esc quit-arm window (~1.5s) - pin that with a keeper test. Keep SGR mouse reporting (mode 1006) paired with the minimal tracking mode you actually use - 1000 press+release, 1002 button-drag, 1003 all-motion only for real hover since it floods the input stream - and never the legacy X10, UTF-8 (1005), or urxvt (1015) encodings. SGR preserves the shift-drag bypass: Shift is the user's escape hatch to native terminal selection, so never bind shift-modified clicks. Disable every mouse mode you enabled on every exit path, including crash handlers - a leaked mode leaves the shell eating clicks after the app dies. Where the framework exposes it, the Kitty keyboard protocol's disambiguate flag removes the lone-ESC ambiguity entirely (note ctrl+c stops raising SIGINT in that mode - keep an explicit quit binding); ESCDELAY remains the insurance on legacy input, and slow links need the higher end of it. Enable bracketed paste and treat everything between the markers as literal text - a pasted control byte must never dispatch as a key binding. Hardcoded click coordinates are a dead end - panel heights vary with live data; derive targets from the live frame. Whether the ESCDELAY insurance is universally required or was multiplexer-specific is unsettled - it is cheap either way.

**Label-derived strings are data, not markup.** A background security review flagged rich markup injection: User-Agents and node names reaching a Text were parsed as markup. Render every label-derived cell (client names, node names, job titles, anything a user or remote system chose) as literal text, never through a markup parser. Treat a reported injection like any bug: reproduce first - the first repro can pass by accident (a name cut at "/" hid the marker), so retry with a clean payload - then prove it red-green before fixing.

**Test hardening can silently create holes.** Retry-with-warm-memos masked injected regressions; warmup discard tightened a budget to max-of-2. Both were caught by adversarial review of the hardening change itself and verified by re-injection.

**Colour tests must test the colours actually drawn.** Named colours collided at render time (see theme.md); resolve names to hexes and test resolved RGB.

**Framework/library semantics that bit - probe both directions, do not trust review reading:**
- rich's `Text.truncate` and `rstrip` return None and mutate in place - a trailing-newline crop looked redundant and the review mis-read it; the golden proved the crop was load-bearing.
- rich's `Text.split` drops the trailing blank line, breaking row-count arithmetic.
- An auto-sized Static's content_size feeds the previous render's line count back into layout - a body grew one line every frame. Fix: CSS `height: 1fr` and re-render from the resize event (fires after relayout), not synchronously from a key handler; `call_after_refresh` also races relayout.
- A mid-flight render after shutdown can crash: guard at the top of render on the running flag; a bare async fetch task (not a framework worker) resumes after shutdown.
- The framework may dispatch message handlers from every MRO class - an override calling `super().on_mount()` runs the base handler twice, cancelling the first worker and leaving the app permanently empty.
- Make the TUI framework a CORE dependency, never an optional extra - optional extras split environments silently: green locally, red in CI.

**Unicode width.** Compute cell width over whole grapheme clusters, never per-codepoint wcwidth sums: heart+VS16 occupies 2 cells while its codepoints sum to 1, and when your count and the terminal's disagree by one cell, every border after it smears. Keep fresh emoji and ambiguous-width glyphs out of drawn chrome and label-derived strings; stick to the well-supported sets (box drawing, block elements, geometric shapes like ● ○, Braille).

**Hand-rolled rendering - the terminal rules a framework normally owns.** Only when there is no framework (raw curses or bespoke ANSI):
- Restore the terminal on every exit path - normal, SIGINT/SIGTERM/SIGHUP, and crash: leave the alt screen, show the cursor, disable every mouse mode and bracketed paste, reset attributes, restore cooked mode. Install the handlers before entering raw mode.
- Reserve the alternate screen for genuinely full-screen, scroll-free UIs - it has no scrollback.
- On SIGWINCH, invalidate all frame geometry and do a full repaint; never diff against stale pre-resize frames.
- Never erase a frame by rewinding a remembered line count (ESC[2K + ESC[1A loops): cursor-up saturates at row 1 and every redraw pushes another copy into scrollback. Repaint from an absolute anchor.
- Render the full frame into an off-screen buffer and flush only the cell diff, wrapped in synchronized output (CSI ? 2026 h ... l) where supported. In curses: erase() not clear() (clear() forces a full flicker repaint), wnoutrefresh each window then one doupdate, never wrefresh per window.

**State-drift classes:**
- Stale positions: flat positions (selection, scroll anchor, search accent) drift when the buffer reshapes. Resolve positions to (label, row) content before the reshape, recompute after, clear when unmappable.
- Paused-view drift: an offset counted lines-from-the-bottom shifts on every append. Anchor to absolute positions; bound the scrollback (10k rows) to bound memory and every render/search pass.
- Async fetch races: a fetch outliving its registration can record over a fresher snapshot. Generation guard - a per-key counter captured at launch, bumped (never popped) at unregister; drop any record whose generation is stale.
- Clamp the selection wherever the shown list is rebuilt (one choke point in render), never modulo-wrap on Enter - a refresh shrinking the list left selection past the end and the wrap opened the wrong item.
- Mouse hit-testing breaks at scroll edges: extract one shared window-start so the renderer and the hit test cannot drift.
- Unbounded caches are a recurring trap; one LRU bound covers every dimension.
- Unguarded awaits in key handlers crash the whole app: per-label containment plus an app-level guard and a post-await state re-check.
- Bytes, not characters: a read with byte counts must count bytes - a text-layer walk over multibyte content miscounted lines; read the binary buffer (a newline byte never sits inside a UTF-8 sequence).

**Environmental traps (from live E2E):**
- The multiplexer, not the outer terminal, defines capabilities: inside tmux the app sees TERM=tmux-256color, and truecolor reaches it only when the outer terminal is configured for RGB passthrough. Test inside tmux as a first-class environment, never as an afterthought.
- NFS: held-fd reads at EOF serve attribute-cached data in ~3s bursts; a bare open+close probe before each held-fd read forces revalidation. NFS can also publish a file's SIZE before its DATA - reads at the append edge return NUL zero-fill; hold any NUL-carrying chunk, roll back the offset, re-read once real bytes land.
- Data-failure UX: never fabricate zeros. Unfetched shows a fetching note; failure without last-known shows the error alone; failure with data shows last-known plus a stale note; every consuming panel is keyed to its sources (a history panel once rendered fabricated "now 0" under an outage). Error notes render on their own line - notes glued onto data bodies are invisible.
- Verify derived-value premises against live payloads before building - one design rested on a false "no source exists" finding; a live probe found the real source and forced a rework.
- Dead ends are implemented, measured, and reverted with the numbers kept, not hidden.

**Process anti-patterns:** accepting a spike's prose at face value (judge claims conjunct-by-conjunct against evidence); keeping a test that pins an unobservable ordering; fixing blind without a repro; averaging in contaminated perf readings; trusting an implementer's live-probe report without re-running it.

## Stack and frameworks

Default: Python + Textual + rich (all accepted builds). When the host project's language forces a different stack, pick the framework whose model matches this skill's architecture - the screen as a function of state, not a mutated widget tree - and port the principles, not the library calls:

- Go: Bubble Tea (Elm model/update/view - state object, message dispatch, pure render; Bubbles components, Lip Gloss styling; log to files, the TUI owns stdout). Rust: Ratatui (immediate mode - your code owns the loop, renders the full frame into a buffer each pass, the library diffs and flushes).
- Prompts and REPLs (completion, history, vi/emacs modes): prompt_toolkit. A one-line-updating status or a periodically refreshing panel with no Python deps: rich Live + Layout is the ceiling - move to a real framework the moment you need focus, scrolling state, or modals. Refresh no faster than the data actually changes.
- Raw curses only for tiny, dependency-free tools; it has no widget concepts. If forced: use `curses.wrapper()`, remember coordinates are (y, x), and ncurses screen state is not thread-safe - serialize the calls.
- Before a from-scratch design, scan a curated TUI catalog (rothgar/awesome-tuis) for a same-stack precedent - the pattern usually already exists.

Whatever the stack, the layers here transfer: pure views + goldens (Layer 1), real-byte parser tests (Layer 3), at least one real-pty layer (Layer 4), perf budgets, measure-before-optimizing.

## Architecture that worked

**Views are pure functions.** View/panel renderers are pure functions of typed models + view state (+ width) -> rich Text, never console printing. Goldens pin bytes and spans; the app mounts results and owns no data logic. This makes most of the TUI testable without the framework running at all.

**Layering:** fetch+parse at the bottom, pure math above, pure renderers above that, the app as a thin shell (layout, keys, refresh loop).

**Width handling - two converged variants, one principle:** either flatten-then-crop (lay out any renderable at measured natural width, crop each line at the box width - trailing columns drop, surviving columns never rescale, and every narrow line is a byte-prefix of its wide counterpart, held by test), or width-adaptive fit (pick the first table variant whose natural width fits, dropping columns by a named drop-order). Both keep terminal width out of the data layer. Panels never crop - every line is built to fit with a final word-wrap pass.

**Refresh/poll model.** One fixed-cadence tick collects the current screen's sources, fetches only stale keys concurrently with singleflight, captures errors per key (one broken source never kills the tick), and each landing renders immediately. Logs poll on a separate faster timer. Ring-buffered history: keep the last N readings for windowed rates; one trend function owns every chart series key so the append loop and the renderers cannot drift apart.

**Input handling.** Dispatch on the printable character when there is one, else the key name - never `event.character`. One keymap dict. Mouse hit tests map y through the same window arithmetic the renderer sliced with, indexing the same shown list; the dispatch rule itself (clicks ride the same actions the keys use) lives in theme.md (Interaction model).

**Charts: hand-rolled** (see theme.md). Plotting libraries designed for direct stdout fight a framework render loop; settle library choices by measured spike, not docs, and re-test recorded rationales.

**Theme as a single module.** A central theme module replacing scattered style strings; theme ports are span-only changes so every golden stays byte-identical, with palette-pin tests holding the exact colours.

**Module split along real seams only.** Split only where a real seam exists (screen state, chart renderer, shared view machinery); imports stay public-name only. A near-1000-line app.py was kept whole because its dispatch tables feed render paths as much as keys - extraction would have been a mixin tangle. Reuse the existing data layers instead of parallel hand-rolled tables: the TUI is a new shell over the same seams.

## Scaling the loop to the build

The evidence comes from two large builds (multi-week, subagent waves, plan-review rounds). A single-view TUI may not justify the full machinery - treat the loop as the ceiling and scale down. The non-negotiable minimum for any TUI: prototype-first taste settling, red-first TDD, pure-render goldens, at least one real-pty test layer, perf budgets with measured baselines, and measure-before-optimizing. The specific budget thresholds and the byte-parity contract are starting points: re-measure import time on your dependency set before committing to the numbers, and hold byte-parity to a mirrored command only where a command exists to mirror.

A small read-only dashboard can also stay a single file: the origin build was one ~1800-line PEP 723 uv script with pinned inline deps (`uv run --script`), a fixture-tree test suite with `importorskip` so it skips where the deps are absent, and reader tests, box pins, and Pilot flow tests all inside that shape. Single-file is an accepted delivery form, not an excuse to drop the minimum.
