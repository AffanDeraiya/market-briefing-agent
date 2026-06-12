# Webapp Flow — Market Briefing Agent

SPA with two views: **Home** (ticker entry) and **Run** (live agent + brief). No auth.

## 1. Page Map

```
/            Home — ticker input, examples, recent briefs
/run         Run — reasoning timeline + assembling brief (state-driven, not URL-persisted in v1)
```

## 2. Flow A — First-time visitor (30-second path)

1. Home: one-line value prop ("Watch an AI agent research a stock — every step cited"), big ticker input, example chips: `AAPL` `TSLA` `RELIANCE.NS` `MSFT`.
2. Clicks a chip → ticker validated (`/api/validate`) → Run view opens.
3. Left panel: timeline starts streaming — "Fetching price history…", tool call cards appearing with live durations.
4. `chart_data` arrives → price chart renders top-right with anomaly markers.
5. Agent hits an anomaly → `anomaly_focus` event → corresponding chart marker pulses while the agent investigates it (this moment is the demo).
6. `brief` arrives → brief sections render below the chart; timeline collapses to a summary bar ("14 tool calls · 41s · $0.02 · expand").
7. Visitor clicks citation chips, toggles timeline back open, exports Markdown.

## 3. Flow B — Manual ticker entry

1. Types in input → debounced validate call → ✓ name/exchange shown inline, or ✗ "Ticker not found — try the Yahoo Finance symbol (e.g. RELIANCE.NS)".
2. Period selector: 1mo / 3mo (default) / 6mo / 1y.
3. Generate → Flow A from step 3.

## 4. Run View Layout

```
┌────────────────────────────────────────────────────────┐
│ header: ‹ back · TICKER Company Name · period · status │
├──────────────────┬─────────────────────────────────────┤
│ Agent Timeline   │  Price chart (+ anomaly markers)    │
│ (live, scrolls)  │─────────────────────────────────────│
│  ● step          │  Brief (assembles after `brief`):   │
│  ▸ tool_call     │   Snapshot strip                    │
│  ✓ tool_result   │   Technical summary                 │
│  ● step…         │   Anomalies (cards w/ explanation)  │
│ cost meter ▓▓░   │   News · Bull · Bear · Risks        │
│                  │   Citations list                    │
├──────────────────┴─────────────────────────────────────┤
│ disclaimer footer (persistent)                          │
└─────────────────────────────────────────────────────────┘
```
Timeline panel: 360px left rail on desktop; on completion auto-collapses to summary bar (re-expandable).

## 5. Timeline Item Anatomy

- **step**: dot + italic thinking snippet.
- **tool_call**: card with tool icon, name, key inputs (e.g., `get_company_news · "TSLA recall" · Mar 1–7`), spinner.
- **tool_result**: same card resolves — ✓/✗, summary line, duration badge. Click expands input JSON (results stay summarized).
- **anomaly_focus**: amber highlight card "Investigating −8.2% drop on Mar 3" + chart marker pulse.
- Cost meter: running token count and est. $ at the rail bottom.

## 6. Query Lifecycle States

| State | UI |
|---|---|
| validating | input spinner |
| streaming | timeline live, status pill "Researching…", Stop button (closes stream) |
| success | brief rendered, timeline collapsed, status "Done in 41s" |
| error:parse / upstream / timeout | timeline preserved + error card with honest message and "Try again" |
| error:budget (global cap) | "Daily demo budget exhausted — the repo is on GitHub →" |
| rate-limited (429) | "Limit: 5 briefs/hour per visitor. Try again in Xm." |
| server-waking | "Demo server waking (~30s)" + auto-retry |
| stopped | partial timeline kept, "Run stopped" |

## 7. Brief Interactions

- Citation chip `[c3]` → popover (title, source, link) ; click-through opens in new tab.
- Anomaly card ↔ chart marker: hover either highlights both.
- Export: "Copy as Markdown" + download `.md`.
- Recent briefs (sessionStorage, last 5) listed on Home; reopening renders stored brief instantly (no re-run).

## 8. Empty/Edge States

- Anomaly list empty: "No unusual trading days detected in this period" (positive framing, still rendered).
- Anomaly with no found cause: card shows "No clear public cause found" + low-confidence badge — honesty styled as a feature, not a failure.
- Very new ticker (little history): brief renders with what exists + note.
- SSE drop mid-run: auto-reconnect once; else error state with preserved timeline.

## 9. Responsive & Accessibility

- <1024px: single column — chart, then collapsible timeline accordion, then brief.
- Keyboard: input → chips → generate all tabbable; timeline is `aria-live="polite"` region announcing stage changes.
- Charts always paired with the textual brief (never sole representation). Contrast per design.md ≥ AA.
- `prefers-reduced-motion`: no marker pulse/slide animations.
