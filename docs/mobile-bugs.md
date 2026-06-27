# Mobile UI Bugs — Market Briefing Agent

**Logged:** 2026-06-27 · **Branch:** `working` · **Source:** CSS + component audit against the live build (the deployed app's mobile layout was reported as "not refined").

**Root cause (read first):** the entire app has only **one** mobile breakpoint — a single `@media (max-width: 900px)` block in `frontend/src/index.css` (~lines 1778–1798) with just 5 rules:

```
.cols              -> grid-template-columns: 1fr
.snapbar           -> grid-template-columns: repeat(3, 1fr)
.recents .rlist    -> grid-template-columns: 1fr
.pop               -> width: 240px
.home h1           -> font-size: 36px
```

There is **no phone-tier breakpoint (~430–480px)**, so almost every component keeps its desktop layout on a phone. The fixes below assume adding a phone breakpoint plus the per-component changes.

> Note: this list was produced by auditing the CSS/components at their breakpoints (the test browser couldn't be forced below ~1280px to pixel-emulate a phone). Items marked **(verify)** are high-confidence from the CSS but worth a 30-second check in real device emulation; the rest are definite from the layout rules.

Severity: **Critical** = breaks layout or blocks core value on a phone · **Moderate** = looks broken / cramped · **Minor** = polish.

---

## Critical

### 1. Run header overflows on phones
`.runhead` (index.css ~473) is a single **non-wrapping** flex row containing: back button, ticker (`.tkr`, 20px mono), period meta pill, `.spacer`, `.actions` (Copy MD + Export buttons), and the status pill (during a run, also a Stop button). With `padding: 13px 26px` and `gap: 14px`, this cannot fit ~390px — the action buttons / status pill clip or push off-screen.
**Fix:** at phone width, allow the row to wrap or restructure — shrink the ticker, make Copy MD / Export icon-only (or move into an overflow menu), reduce side padding to ~14px, and let the status pill drop onto its own line.

### 2. Hover-only content is invisible on touch devices
All the rich detail is revealed on `:hover`: agent-log tool-step cards, the budget-bar explainer card, and citation popovers. Touch devices have no hover, so on mobile a user cannot open any tool-step detail, the budget explainer, or citation sources — which guts the "watch the agent reason / every claim cited" value prop.
**Fix:** on touch, make these tap-to-open (click toggles the portal card; tap-outside / Esc closes) instead of hover-only. Detect via pointer/touch (e.g. `@media (hover: none)` or a JS pointer check).

### 3. Home action row overflows
`.home .row` (index.css ~1321) is `display:flex; justify-content:space-between` (no wrap) with the 4-button period selector (1mo/3mo/6mo/1y) on the left and the Generate button on the right. At ~390px these two groups exceed the width and squish/overflow.
**Fix:** below ~480px, stack to `flex-direction: column` with a full-width period selector and a full-width Generate button.

---

## Moderate

### 4. Chart anomaly callouts overflow / collide on mobile
The pin callout pills are a fixed **148px** wide (`frontend/src/components/PriceChart.tsx`). On a ~330px-wide mobile chart they overlap each other and clip past the left/right edges (already an issue on desktop with clustered pins; mobile makes it unusable).
**Fix:** at small widths, shrink the callout (smaller font/width), show the label only for the hovered/tapped pin, and tighten chart side padding + reduce x-axis tick density.

### 5. Snapshot bar cramped at 3 columns on a phone
`.snapbar` drops to `repeat(3,1fr)` at ≤900px; at ~390px each of the 6 mono cells (e.g. "MKT CAP / $4.38T") is ~100px and gets tight or wraps.
**Fix:** drop to `repeat(2,1fr)` below ~430px.

### 6. Fragile sticky offset
`.runhead` uses `top: 35px`, hard-coded to the agent-log strip's desktop height. If the strip or header wraps taller on mobile, they overlap.
**Fix:** make the runhead's sticky `top` match the actual strip height, or make them non-sticky (or single-sticky) on mobile.

### 7. Agent-log strip cramped on phones
The 35px sticky strip packs the "agent log" label + horizontal tool steps + the runstats cluster (`N/15 tools · tok · latency · collapse`) into one row; at ~390px the runstats + label crowd out the steps. Touch-swipe of `.steps` works (overflow-x:auto), but combined with #2 the per-step detail is unreachable.
**Fix:** simplify the strip on mobile — condense/hide the runstats inline, or move the run summary below the strip.

### 8. 52-week range bar labels may collide (verify)
The range bar shows low/high at the ends plus a "₹890.05 · 87% of range" label; on narrow widths the right-hand label can overrun.
**Fix:** stack the value label above the bar on mobile.

---

## Minor / polish

### 9. Board side padding too heavy on mobile
`.board { padding: 28px 26px 64px }` eats ~52px on a 390px screen.
**Fix:** reduce side padding to ~14–16px below ~480px.

### 10. Verification banner chips (verify)
`.verif-banner` wraps (good), but `.vb-chips { margin-left: auto }` can leave an awkward gap when wrapped on mobile; the chips also look tappable but don't navigate (carried over from desktop notes).
**Fix:** drop the `margin-left:auto` at phone width; clarify or make chips navigate.

### 11. Verifier walkthrough on mobile (verify)
The guided walkthrough (auto-scroll + char-by-char animations + floating Skip button) is likely janky on small screens / touch.
**Fix:** confirm it degrades gracefully on mobile and that `prefers-reduced-motion` still short-circuits it.

---

## Suggested priority order
1, 2, 3 first — these are what make it feel "not refined at all" on first open (header, hover→tap, home row). Then 4–7 for the Run view, then the minor polish.
