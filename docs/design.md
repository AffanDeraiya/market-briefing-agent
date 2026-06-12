# Design — Market Briefing Agent

## 1. Direction

"Trading-desk calm." Dark, dense-but-breathable, data-first. Two visual centers of gravity: the **live timeline** (motion, process) and the **brief** (stillness, conclusions). Everything else recedes. Reference feel: Linear's restraint + a Bloomberg-terminal hint via mono numerals — without the clutter.

## 2. Color Tokens

| Token | Value | Usage |
|---|---|---|
| `bg-base` | `#09090b` (zinc-950) | App background |
| `bg-panel` | `#18181b` (zinc-900) | Cards, rails, inputs |
| `bg-raised` | `#27272a` (zinc-800) | Hovers, expanded rows |
| `border` | `#3f3f46` (zinc-700) | 1px borders |
| `text-primary` | `#fafafa` (zinc-50) | Headings, brief body |
| `text-secondary` | `#a1a1aa` (zinc-400) | Labels, meta, thinking text |
| `accent` | `#22d3ee` (cyan-400) | Active tool calls, links, primary button, focus |
| `up` | `#34d399` (emerald-400) | Positive change, price-up, success ✓ |
| `down` | `#f87171` (red-400) | Negative change, price-drop anomalies, errors |
| `anomaly` | `#fbbf24` (amber-400) | Anomaly markers, investigation highlights |
| `chart-line` | `#e4e4e7` (zinc-200) | Price line |
| `chart-volume` | `#3f3f46` at 60% | Volume bars |

Finance semantics are non-negotiable: green = up, red = down, everywhere and only that.

## 3. Typography

| Role | Font | Spec |
|---|---|---|
| UI & brief prose | Inter | 14px base; h1 22/600; section heads 13/600 uppercase tracked +0.04em |
| Numbers, tickers, tool names, SQL-ish payloads | JetBrains Mono | 13px; tabular-nums; all price/percent figures use mono |
| Thinking snippets in timeline | Inter italic | 13px, `text-secondary` |

Ticker symbol always mono + uppercase (e.g., `AAPL`), company name regular Inter beside it.

## 4. Spacing & Shape

4px scale. Radius: 10px cards, 6px buttons/inputs, 999px pills/chips. Flat (border-defined, no shadows) except the sticky run header (bottom border + 8% black blur). Desktop grid: 360px timeline rail / fluid main, max 1440px.

## 5. Key Components

### Ticker input (Home hero)
Large (56px) centered input, mono text, cyan focus ring; inline validation state right-aligned inside the field (✓ Apple Inc · NASDAQ / ✗ not found). Example chips below as pills.

### Timeline rail
Vertical line connecting items. Items per webapp_flow §5:
- step → 6px dot on the line + italic snippet
- tool_call/result → card: mono tool name, key inputs as muted text, right-aligned duration badge; left edge 2px `accent` while running → `up` on ✓ / `down` on ✗
- anomaly_focus → amber left edge + amber dot on the line
- Cost meter pinned at rail bottom: `1.2k tok · ~$0.014` mono, thin progress bar vs budget.

### Price chart
Recharts ComposedChart: price line (`chart-line`), volume bars muted below, anomaly markers as amber dots sized by severity. Hover crosshair w/ mono tooltip. Investigated marker pulses (1.2s, twice). No gridline clutter — dashed `border` at 30%, 4 ticks max.

### Brief sections
- Snapshot strip: 5–6 stat blocks (mono value + label), change values colored up/down.
- Anomaly card: date + kind badge (amber), magnitude in mono, explanation prose, confidence badge (high `up` / medium `anomaly` / low `text-secondary`), citation chips.
- Bull/Bear: two-column on desktop — bull column heading `up`, bear `down`; bullets with citation chips.
- Citation chip: `[c3]` mono superscript pill; hover popover (title/source/link).

### Status pill (run header)
`● Researching…` cyan pulse → `✓ Done in 41s` green → `✗ Failed` red → `■ Stopped` neutral.

### Disclaimer footer
Persistent, `text-secondary` 12px: "Educational project. Not financial advice. Data via Yahoo Finance; may be delayed/inaccurate." + GitHub link.

## 6. Motion

- Timeline items: 150ms fade + 6px slide-up on mount; auto-scroll follows newest unless user scrolled up (then "↓ live" button).
- Tool card running state: subtle left-edge shimmer, no spinners spam.
- Brief sections: stagger in 80ms apart on `brief` event.
- Timeline collapse on success: 250ms height ease to summary bar.
- `prefers-reduced-motion`: all of the above off; instant renders.

## 7. Voice & Microcopy

Honest, precise, no hype. "No clear public cause found" not "Unable to process". Errors = what happened + one action. No exclamation marks. Numbers always with sign and unit: `−8.2%`, `4.2× avg vol`.

## 8. Branding

Wordmark: `Briefcase` ... no — wordmark is `Market Briefing Agent` in Inter 600 with a `▴▾` glyph pair in up/down colors as the mark + favicon. Footer credit: "Hand-rolled agent loop on the Claude SDK · FastAPI · React".
