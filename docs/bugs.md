# Bug List — Market Briefing Agent

**Logged:** 2026-06-16 · **Branch:** `working` · **Source:** live testing of the deployed Vercel/Render build (AAPL 3mo, IDEAFORGE.NS 3mo with 5 anomalies, invalid-ticker run) plus source inspection.

Severity legend: **High** = broken core feature / crash · **Medium** = wrong or confusing output · **Low** = cosmetic / polish.

Each item lists the symptom, root cause (with file references), and a suggested fix. File line numbers are approximate.

---

## Reported by owner

### 1. Agent-log strip overflows with no usable horizontal scroll — Medium
- **Symptom:** When tool steps exceed the bar width, the extra steps are cut off and unreachable; there's no scrollbar or other affordance.
- **Cause:** `frontend/src/index.css` — `.strip .steps` uses `overflow-x: auto` but hides the scrollbar (`scrollbar-width: none` + `::-webkit-scrollbar { display:none }`). A vertical mouse wheel doesn't pan horizontally, so overflowed steps can't be reached on desktop.
- **Fix:** Add a wheel→horizontal handler on `.steps` in `AgentLogStrip.tsx` (translate `deltaY` to `scrollLeft`), and/or add a visible affordance (thin scrollbar or left/right fade gradients).

### 2. Hover cards are trapped inside the bar (internal scroll) instead of popping over the page — Medium
- **Symptom:** Hovering a step shows the detail card scrolling *inside* the strip rather than overlaying the page below it.
- **Cause:** Same `.steps { overflow-x: auto }`. Per CSS spec, a non-`visible` `overflow-x` forces `overflow-y` to compute to `auto`, so the scroll container clips the popover. The `.pop` card is `position:absolute; top: calc(100% + 9px)` and ~182px tall, but the strip is only ~34px tall → clipped + internal scroll. (Confirmed via DOM: `.steps` computes `overflow-y: auto`.)
- **Fix:** Render the popover outside the clipping container. Preferred: portal `.pop` to `document.body` with `position: fixed`, positioned from the hovered step's `getBoundingClientRect()` (or use floating-ui/Popper). CSS-only alternative: move `overflow` onto a separate inner wrapper so the popover lives in a non-scrolling sibling layer.

### 3. Faint green line beneath the agent log — NOT A BUG (clarification)
- **What it is:** The **budget bar** (`.budgetbar` / inner `<i>` in `AgentLogStrip.tsx`) — tool-call usage vs the cap of 15, drawn as a blue→green gradient whose width = `toolCallCount / 15`.
- **Optional polish:** Add a `title`/`aria-label` (e.g. "Tool budget: 6 / 15") so its meaning is discoverable.

### 4. Multiple anomaly cards overlap / no separation — Medium
- **Symptom:** With several anomalies, the cards stack flush against each other and read as one merged block; a hovered card's ring bleeds onto its neighbor.
- **Cause:** `frontend/src/index.css` — `.doc-sec` only spaces *sections* (`margin-bottom: 34px`); there's no spacing between sibling `.anom-panel` cards, and `AnomalySection` (`components/AnomalyCard.tsx`) renders them as direct children with no gap. The `.anom-panel.linked` ring (`box-shadow: 0 0 0 3px`) overlaps the adjacent card.
- **Fix:** Add vertical spacing — CSS `.anom-panel + .anom-panel { margin-top: 14px }`, or wrap the `.map` in `AnomalySection` in a `<div className="anom-list">` with `display:flex; flex-direction:column; gap:14px`.

### 5. Invalid ticker still runs the agent — High
- **Symptom:** Clicking **Generate brief** with a ticker that failed validation (e.g. `ZZZZZZ`) still launches a run; tools fail, budget/tokens are wasted, and it can trigger the crash in #11.
- **Cause:** `frontend/src/components/Home.tsx` — the Generate action (button, ticker chips, and Enter-to-submit) isn't gated on the validation result.
- **Fix:** Disable Generate / block submit unless the latest `/api/validate` response was `valid: true`; show the existing "Not found" hint and keep the button disabled.

### 6. Homepage validation text overflows the input box — Low
- **Symptom:** The inline success label ("✓ NVIDIA Corporation · NasdaqGS") spills to/past the right edge of the input for longer company names + exchange (seen with NVDA).
- **Cause:** `frontend/src/components/Home.tsx` + CSS — the validation label is positioned inside the input with no max-width / truncation, so long `name · exchange` strings overflow the rounded container.
- **Fix:** Constrain the label (`max-width`, `white-space: nowrap`, `text-overflow: ellipsis`) and/or reserve right-padding on the input so the text can't collide with the edge; consider truncating the company name before " · exchange".

---

## Additional bugs found

### 7. The price chart never renders anomaly pins — High
- **Symptom:** Even with multiple detected anomalies (5 on IDEAFORGE.NS), the chart shows zero anomaly pins. The anomaly pin is the product's headline feature.
- **Cause:** `backend/src/agents/market_brief/nodes.py` `_post_tool_side_effects` emits `chart_data` inside the **`get_price_history`** branch (line ~186), building `anomalies_list` from `state.anomaly_dates`. But `anomaly_dates` is only populated when **`detect_anomalies`** runs (line ~166), which happens *later* in the tool order. So at emit time the set is empty → `chart_data.anomalies` is always `[]` → no pins ever.
- **Fix:** Emit `chart_data` (or its anomaly markers) **after** `detect_anomalies` has run — e.g. emit OHLCV on price-history as now, then emit a second `chart_data` (or a dedicated anomaly-markers event) once anomalies are detected; or defer the single emit until both are available.

### 8. Chart pins only the first anomaly — Medium
- **Symptom:** Once #7 is fixed, only one anomaly would still show.
- **Cause:** `frontend/src/components/PriceChart.tsx` line ~159 `const anomaly = chartData.anomalies[0]` — a single `ReferenceDot` is rendered.
- **Fix:** Map over `chartData.anomalies` to render a pin per anomaly; stagger/offset the callout labels so clustered dates don't collide.

### 9. Market cap is unformatted — Medium
- **Symptom:** Shows raw integers like `4353626210304` / `38034706432` instead of a compact value.
- **Cause:** `fmtCap()` exists in `frontend/src/lib/format.ts` but is never called. `components/SnapshotBar.tsx` (line ~16) and `mdExport` (`format.ts` line ~83) render `snapshot.market_cap` directly.
- **Fix:** Use `fmtCap(...)` at both sites. Note `market_cap` is typed `string` in `lib/types.ts` — reconcile to `number` (or parse) so `fmtCap` works.

### 10. Currency symbol hardcoded to `$` for non-USD tickers — Medium
- **Symptom:** IDEAFORGE.NS shows `$876.75` and a `$`-style market cap, though it trades in ₹ (the LLM text correctly says "₹…crore").
- **Cause:** A literal `$` is prepended in `SnapshotBar.tsx`, `PriceChart.tsx` (`CrossTip`), `RangeBar`, and `mdExport`.
- **Fix:** Derive a currency symbol from the ticker/exchange (`.NS`/`.BO` → ₹, etc.) or have the backend return a `currency` field on the snapshot and use it everywhere a price is rendered.

### 11. No React error boundary + unguarded `.toFixed()` → whole-app white screen — High
- **Symptom:** A brief with a null numeric field crashes React to a blank page; only a reload recovers. (Reproduced via a bad-ticker run; `TypeError: Cannot read properties of null (reading 'toFixed')`.)
- **Cause:** `components/SnapshotBar.tsx` calls `snapshot.price.toFixed(2)` (plus `pe`, and `low_52w/high_52w` in `format.ts`) with no null guard, and there is no error boundary in the tree.
- **Fix:** Add a top-level React error boundary (in `App.tsx` / `main.tsx`) with a fallback UI; null-guard the numeric formatters and their call sites.

### 12. 1D / 1M / period changes are LLM-supplied and inconsistent — Medium
- **Symptom:** AAPL showed `1D 0% / 1M 0%`; IDEAFORGE showed real values — non-deterministic.
- **Cause:** `attach_market_data` in `backend/.../nodes.py` overwrites only `low_52w/high_52w` + indicators; `change_1d/change_1m/change_period` come from the model's JSON (`prompts.py` requests them). This produces the 0% values and violates the "LLM never computes numbers" rule.
- **Fix:** Compute these deterministically from the price-history series and attach them in `attach_market_data` (like the 52-week values); remove them from the LLM's required JSON.

### 13. Recents relative timestamp is wrong — Low
- **Symptom:** A just-run brief shows "8h ago".
- **Cause:** Relative-time calc in `frontend/src/store/runStore.ts` (recents) is off by a fixed offset — likely mixing a UTC date string with local "now".
- **Fix:** Store `Date.now()` (epoch ms) at save time and compute the delta against `Date.now()` at render; don't mix UTC date strings with local time.

### 14. Anomaly hover card in the agent log shows hardcoded placeholders — Low
- **Symptom:** The agent-log "anomaly" hover always reads `target: price drop · 2.5σ` and `next: ±3-day news search`, regardless of the real anomaly (IDEAFORGE's first was a +20% / 4.1σ surge).
- **Cause:** `frontend/src/components/AgentLogStrip.tsx` `AnomalyStepCard` renders static strings.
- **Fix:** Drive the card from the real `anomaly_focus` step payload (kind, magnitude, sigma, date).

### 15. Duplicate citations (intermittent) — Low
- **Symptom:** On AAPL, bullets showed both raw inline `(c4)` text and a styled `[c4]` pill; on IDEAFORGE only pills. Depends on whether the model emits inline markers.
- **Cause:** The renderer appends a citation pill but doesn't strip inline `(cN)` markers the model sometimes writes into the bullet/explanation text.
- **Fix:** Strip trailing `(c\d+)` patterns from bullet/explanation text in the brief renderer (`Citation.tsx` / section components) before appending pills.

### 16. Failed/crashed runs are saved to recents — Low
- **Symptom:** The bad `ZZZZZZ` run persisted as a recent card; reopening it would re-crash (see #11).
- **Cause:** `frontend/src/store/runStore.ts` save logic writes to recents regardless of run outcome.
- **Fix:** Only write to recents on a successful finalize with a valid brief; skip error/stopped states.

---

## Watch / verify (not confirmed bugs)

- **Chart x-axis first label clipping:** AAPL once showed `-16` (truncated) where IDEAFORGE showed `03-16` correctly — appears width/tick-density dependent. Verify `PriceChart.tsx` x-tick formatting/spacing.
- **Render cold start:** First request after idle took >45s (Render free tier spin-down). Consider a "server waking" state or a keep-warm ping for demos.
