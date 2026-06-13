# Design — Market Briefing Agent

> **Finalized direction: the Live Investigation Board.** Visual reference: `mockups/investigation_board.html` (open the Run view, hover the dark agent-log strip). Earlier explorations are kept in `mockups/mockups.html`, `mockups_v2.html`, `mockups_v3.html` for reference only — this doc is the contract.

## 1. Direction

**"Live Investigation Board."** Light, warm-paper, document-style — a research desk, not a SaaS dashboard. The interface has one spine: a single centered column where the **price chart is the primary object** and the **brief assembles inline beneath it, section by section, as the agent works**. Two centers of gravity:

- The **agent-log strip** across the very top = the *process* (motion, tool calls, the moment it finds an anomaly and goes digging).
- The **growing document** below = the *conclusions* (stillness, cited prose).

No left sidebar. Reference feel: a well-set financial research note (FT/ledger restraint) crossed with Linear's calm. The differentiator — deterministic anomaly detection then autonomous investigation — is made visible: the anomaly is pinned to the chart and traced into its own section, with the log showing the agent pausing to investigate it.

## 2. Color Tokens (light)

The user moved away from dark deliberately; v1 ships **light only** (a dark mode is explicitly post-v1).

| Token | Value | Usage |
|---|---|---|
| `bg-base` | `#f3f2ee` | App canvas (warm paper) |
| `bg-panel` | `#ffffff` | Cards, chart box, inputs |
| `bg-raised` | `#eeede9` | Hovers, skeleton fills, anomaly panel |
| `border` | `#d6d4ce` | 1px hairline borders/dividers |
| `text-primary` | `#1c1b18` | Headings, figures, brief body emphasis |
| `text-secondary` | `#6b6860` | Brief prose, labels, meta |
| `text-tertiary` | `#a09d96` | Axis ticks, captions, muted keys |
| `accent` | `#1e3a5f` (deep navy) | Links, primary button, focus ring, section index, crosshair, price marker |
| `up` | `#1a6b3a` | Positive change, price-up, success ✓ |
| `down` | `#a02020` | Negative change, price-drop anomalies, errors |
| `anomaly` | `#8a5a00` | Anomaly markers, pin, investigation highlights |
| `chart-line` | `#2a2926` | Price line |
| `chart-volume` | `border` token | Volume bars (faint, below price) |

**Agent-log strip (dark inset):** bg `#1e2d42`, borders `#2d3f55`, base text `#7a8fa0`, active text `#e8eaec`, green tick/done `#6ab88a`, amber anomaly `#e0a040`, budget bar gradient `#4a7fb0 → #6ab88a`.

Finance semantics are non-negotiable: **green = up, red = down, everywhere and only that.** Amber is reserved exclusively for anomalies. Navy accent is the only non-semantic color and is used for one job: interaction/emphasis.

## 3. Typography

| Role | Font | Spec |
|---|---|---|
| Section & display headings | **Space Grotesk** | h1 52/600 (home), section h2 18/600, tracking −0.01 to −0.025em |
| UI & brief prose | **Inter** | 14–15px; line-height 1.6–1.72. Deliberately the neutral/standard body — voice comes from the Grotesk headings + mono numerals, not the body face |
| Numbers, tickers, tool names, labels, metadata | **JetBrains Mono** | 11–20px; `tabular-nums`. **Every** price/percent/σ/duration/token figure is mono |

Ticker symbol always mono + uppercase (`AAPL`); company name in Inter beside it. Eyebrows and section indices (`01`–`06`) are mono, uppercase, tracked.

## 4. Spacing & Shape

4px scale. **Single centered board, max-width 1100px**, generous vertical rhythm (~28–34px between sections). Radius: 14px chart box, 12px panels/cards/range bar, 10px popovers/small cards, 8px buttons/inputs, 99px pills/chips. Flat and border-defined — **no shadows except** floating overlays (hover detail cards, citation popovers, crosshair tip). The agent-log strip and run header are **sticky** to the top so run context never scrolls away.

## 5. Key Components

### Agent-log strip (sticky, top — the signature element)
Dark navy inset bar. Left: `● agent log` label. Center: the run as an ordered row of steps, each hoverable:
- **tool_call** → `✓ tool_name 344ms`. Hover card: one-line description of what the tool does, its exact **input**, a **result summary**, and **duration**.
- **anomaly_focus** → amber `◆ anomaly`. Hover card: the target (`−3.6% · 2.5σ`), date, and what it did next (`±3-day news search`). This is the investigation moment, made first-class.
- **compose** (final step) → `✎ compose`. Hover card: the closing rationale + output.

Right cluster: live run-stats `6/15 tools · 13.9k tok · 27s`; hover → **run-summary card** (model, iterations N/max, tool calls N/max, tokens in/out, est. cost, latency). A 3px **budget bar** under the strip fills toward `MAX_TOOL_CALLS`. Hover cards are built entirely from `tool_call` (input) + `tool_result` (summary, duration, ok) + `usage` SSE events — no new contract.

### Run header (sticky)
`TICKER` (mono) · company (Inter) · `exchange · period` meta pill · **actions** (`⧉ Copy MD`, `↓ Export`) · **status pill**.

### Status pill
`● Researching…` navy pulse → `✓ Done in 41s` green → `✗ Failed` red → `■ Stopped` neutral.

### Price chart (primary object)
Large white card. Price line (`chart-line`), faint volume bars below, anomaly as an amber **dot + floating pin callout** (`−3.6% · 2.5σ · Jun 9`) connected by a dashed leader. **Crosshair tooltip** on hover (that week's close + volume, mono). **Bidirectional link:** hovering the pin/dot highlights the Anomaly card (`02`) and vice-versa. Investigated marker pulses 1.2s ×2. Minimal gridlines (dashed `border`, 3 ticks).

### Snapshot bar
Six mono cells in a hairline grid: Price · 1D · 1M · period · Mkt Cap · P/E. Change values colored up/down.

### 52-week range bar
Track with a faint `down→anomaly→up` gradient, an accent marker at the current price's position, low/high endpoints labeled in mono, and `$291.13 · 80% of range`.

### Indicator chips
Row beneath Technical read surfacing `compute_indicators` output: `RSI-14 44.5 neutral`, `Volatility 23.1% annualized`, `Max DD −8% (down)`, `vs SMA-20 −4.2%`, `vs SMA-50 +2.0%`, `Volume flat`. Pill-shaped, mono, semantic coloring on signed values.

### Brief sections (01–06), assembling inline
Technical read (+ indicator chips) · Anomaly investigated · What the news says · Bull & bear (two columns; bull head `up`, bear head `down`) · Key risks · Sources. Each section **streams in with a skeleton shimmer that resolves** when its data arrives. Anomaly card: left flag (date / `magnitude` in down-red / `σ` badge) + explanation prose + confidence row (high `up` / medium `anomaly` / low `text-secondary`) + citation chips.

### Citation chip
`[c3]` mono pill; hover → popover with `kind · id`, title, and domain. The parser rejects uncited bullets — never weakened.

### Export & recents
**Export:** "Copy as Markdown" + download `.md` of the finished brief. **Recent briefs:** last 5 in `sessionStorage`, shown as cards on Home (ticker, change · period, name · time); reopening renders the stored brief instantly with no re-run.

### Disclaimer footer
Persistent, `text-tertiary` 12px, with the `▴▾` wordmark: "Educational project. Not financial advice. Data via Yahoo Finance; may be delayed or inaccurate." + GitHub link.

## 6. Motion

- **Streaming:** each brief section shows a skeleton shimmer, then resolves to content on its triggering SSE event (`chart_data` → chart; `brief` → sections stagger in 80ms apart).
- **Agent log:** steps fade in on arrival; the active step's tick blinks; budget bar eases on each tool call.
- **Anomaly:** dot/pin pulse 1.2s ×2 when the investigation step lands or the card is hovered.
- **Sticky collapse:** on success the log may condense to a one-line run summary (re-expandable).
- `prefers-reduced-motion`: shimmer, pulse, and slides off; instant renders.

## 7. Voice & Microcopy

Honest, precise, no hype. "No clear public cause found" not "Unable to process". Errors = what happened + one action. No exclamation marks. Numbers always signed and united: `−3.6%`, `2.5σ`, `4.2× avg vol`.

## 8. Branding

Wordmark: `Market Briefing Agent` in Space Grotesk 600 with a `▴▾` up/down glyph pair (up/down colors) as the mark + favicon. Footer credit: "Hand-rolled agent loop on the Claude SDK · FastAPI · React".
