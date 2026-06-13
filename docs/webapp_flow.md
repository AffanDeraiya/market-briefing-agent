# Webapp Flow — Market Briefing Agent

SPA with two views: **Home** (ticker entry) and **Run** (live agent + brief). No auth. Finalized layout is the **Live Investigation Board** (see `docs/design.md`; visual reference `mockups/investigation_board.html`).

## 1. Page Map

```
/            Home — ticker input, examples, recent briefs
/run         Run — agent-log strip + chart + brief assembling inline (state-driven, not URL-persisted in v1)
```

## 2. Flow A — First-time visitor (30-second path)

1. Home: one-line value prop ("Watch an AI agent build the brief live — every claim cited"), big ticker input, example chips: `AAPL` `TSLA` `RELIANCE.NS` `MSFT`, period selector, and recent briefs below.
2. Clicks a chip → ticker validated (`/api/validate`) → Run view opens.
3. The **agent-log strip** (sticky, top) begins filling left-to-right with tool steps showing live durations; the **budget bar** under it advances toward the tool cap.
4. `chart_data` arrives → the large price chart resolves from its skeleton at the top of the board with anomaly markers.
5. Agent hits an anomaly → `anomaly_focus` event → an amber `◆ anomaly` step appears in the log **and** the matching chart pin pulses while the agent investigates it (this moment is the demo).
6. `brief` arrives → sections resolve from skeleton shimmers **inline beneath the chart**, one after another (Technical → Anomaly → News → Bull/Bear → Risks → Sources); the log condenses to a one-line run summary.
7. Visitor hovers log steps for tool detail cards, hovers the right cluster for the run summary, hovers citation chips, then exports Markdown.

## 3. Flow B — Manual ticker entry

1. Types in input → debounced validate call → ✓ name/exchange shown inline, or ✗ "Ticker not found — try the Yahoo Finance symbol (e.g. RELIANCE.NS)".
2. Period selector: 1mo / 3mo (default) / 6mo / 1y.
3. Generate → Flow A from step 3.

## 4. Run View Layout

Single centered board (max 1100px), **no sidebar**. Vertical spine: log → header → chart → snapshot → 52w range → brief.

```
┌──────────────────────────────────────────────────────────────┐
│ ● agent log │ ✓get_price ✓fund ✓indic ✓detect ◆anomaly …│ 6/15 · 13.9k · 27s │  ← sticky strip
│────────────────────────────────────────────────────────────── │  ← budget bar
│ AAPL  Apple Inc.  · NasdaqGS · 3mo ·    ⧉Copy MD ↓Export  ●Done│  ← sticky header
├──────────────────────────────────────────────────────────────┤
│  ┌── Price chart (primary) ── anomaly pin + crosshair ──────┐ │
│  └──────────────────────────────────────────────────────────┘ │
│  [ Price · 1D · 1M · 3mo · Mkt Cap · P/E ]   (snapshot bar)    │
│  [ 52-week range bar ─────────●──── ]                          │
│  01 Technical read           + indicator chips                │
│  02 Anomaly investigated     (flag + explanation + confidence)│
│  03 What the news says                                        │
│  04 Bull & bear                                               │
│  05 Key risks                                                 │
│  06 Sources                                                   │
│  disclaimer footer (persistent)                               │
└──────────────────────────────────────────────────────────────┘
```
The agent-log strip and run header are sticky; the board scrolls beneath them. On completion the log may collapse to a one-line summary (re-expandable). <1024px: the strip becomes horizontally scrollable, snapshot drops to 3 columns, bull/bear stacks.

## 5. Agent-Log Strip — Step Anatomy

The strip is the live process view (replaces the old left-rail timeline). Each entry is hoverable and built from SSE events:

- **tool_call / tool_result** → `✓ tool_name 344ms`. Hover detail card: one-line tool description, the exact **input**, a **result summary** (from `tool_result`), and **duration**. Left tick is the status (✓ ok / ✗ error).
- **anomaly_focus** → amber `◆ anomaly`. Hover card: target (`−3.6% · 2.5σ`), date, and next action (`±3-day news search`). Pulses the matching chart pin.
- **step** (thinking / final) → `✎ compose`. Hover card: the agent's snippet/rationale.
- **Right cluster (run-stats):** `N/MAX tools · tokens · latency`; hover → run-summary card (model, iterations N/max, tool calls N/max, tokens in/out, est. cost, latency). Backed by the `usage` event.
- **Budget bar:** thin bar under the strip, fills `tool_calls / MAX_TOOL_CALLS`.

## 6. Query Lifecycle States

| State | UI |
|---|---|
| validating | input spinner |
| streaming | strip live, status pill "Researching…", sections show skeleton shimmer, Stop button (closes stream) |
| success | brief resolved, log collapsed to summary, status "Done in 41s" |
| error:parse / upstream / timeout | strip + partial brief preserved + error card with honest message and "Try again" |
| error:budget (global cap) | "Daily demo budget exhausted — the repo is on GitHub →" |
| rate-limited (429) | "Limit: 5 briefs/hour per visitor. Try again in Xm." |
| server-waking | "Demo server waking (~30s)" + auto-retry |
| stopped | partial board kept, "Run stopped" |

## 7. Brief Interactions

- **Streaming reveal:** each section is a skeleton shimmer until its data arrives, then resolves in place (stagger 80ms).
- **Citation chip** `[c3]` → popover (kind · id, title, domain); click-through opens source in new tab.
- **Anomaly ↔ chart:** hovering the chart pin/dot highlights the Anomaly card and vice-versa.
- **Chart crosshair:** hovering the price line shows a mono tooltip (that week's close + volume).
- **Indicator chips & 52-week range bar** make `compute_indicators` / fundamentals legible at a glance; signed values carry semantic color.
- **Export:** "Copy as Markdown" + download `.md`.
- **Recent briefs** (sessionStorage, last 5) listed on Home; reopening renders the stored brief instantly (no re-run).

## 8. Empty/Edge States

- Anomaly list empty: "No unusual trading days detected in this period" (positive framing, still rendered); the chart shows no pin.
- Anomaly with no found cause: card shows "No clear public cause found" + low-confidence badge — honesty styled as a feature, not a failure.
- Very new ticker (little history): brief renders with what exists + note; 52-week range bar omitted if insufficient data.
- SSE drop mid-run: auto-reconnect once; else error state with the partial board preserved.

## 9. Responsive & Accessibility

- <1024px: single column — chart, then the strip becomes a horizontally scrollable log, then snapshot (3-col) and stacked brief.
- Keyboard: input → chips → period → generate all tabbable; the agent log is an `aria-live="polite"` region announcing stage changes; hover cards are also reachable on focus.
- Charts always paired with the textual brief (never sole representation). Contrast per design.md ≥ AA on the light palette.
- `prefers-reduced-motion`: no skeleton shimmer, marker pulse, or slide animations — sections render instantly.
