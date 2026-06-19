# Spec — Claim Verifier live transition (reason → verify → revised brief)

**Status:** proposal for implementation · **Scope:** frontend only (no backend changes) · **Author:** live-testing review, 2026-06-19

## 1. Goal (the UX we want)

Today the Claim Verifier runs and a static "Verification" panel (section 08) appears at the bottom, but there is **no dynamic transition** — the user can't tell that a second agent ran or what it changed.

We want a visible, three-phase choreography on a live run:

1. **Reason phase** — tools run and the brief streams in and renders fully, exactly as now.
2. **Verify phase** — once the (composed) brief is on screen, a clear indicator/popup appears saying the **Claim Verifier is running**, with live progress as each claim is audited.
3. **Revision phase** — when verification finishes, the brief is **updated in place with a visible transition** (dropped bullets fade/collapse out, downgraded confidence pulses), the running indicator disappears, and the Verification panel is revealed with a short animation.

The end state should make it obvious that an independent verifier audited the first agent's output and edited it.

## 2. Current state (what already exists vs. what's missing)

### Already in place — no backend work needed
The backend already streams everything required. On a **live** run (`verify_llm=True`) the event order is:

```
brief            # the COMPOSED brief (pre-verification)  ← first emit
verify_started   # { claims_total }
claim_verdict    # one per claim: { target, label, verdict, action, note }   (repeats)
verify_done      # { checked, supported, adjusted, dropped }
brief            # the REVISED brief (post-verification, with `verification` attached)  ← second emit
usage
```
(See `docs/schema.md` §SSE events and §Verification. Offline replay emits `brief` only once and skips the verify events — see Edge cases.)

The store (`frontend/src/store/runStore.ts`) already:
- has `verifying: boolean` and `verdicts: ClaimVerdict[]` in state,
- sets `verifying: true, verdicts: []` on `verify_started`,
- appends to `verdicts` on `claim_verdict`,
- sets `verifying: false` and pushes a `type: 'verify'` LogStep on `verify_done`,
- replaces the brief on each `brief` event via `case 'brief': set({ brief: ev.data })`.

The UI already has `VerificationPanel.tsx` (section 08) and `VerdictBadge.tsx` (inline per-claim badges), rendered from `brief.verification` in `Board.tsx` (~line 233).

### Missing — what this spec covers
1. **No component reads `verifying`.** It is dead state, so nothing tells the user the verifier is running.
2. **The revised brief silently replaces the composed one** (`set({ brief: ev.data })`) — no highlight or animation of what changed.
3. **No phase separation** — the status pill stays "Researching…" through verification, so reason and verify look like one blob.
4. **The `type: 'verify'` LogStep is invisible** — `AgentLogStrip.tsx` only renders `tool_call` / `anomaly_focus` / `step` and returns `null` for `verify`.

## 3. Implementation plan

### 3.1 Store: keep both briefs and compute the diff
File: `frontend/src/store/runStore.ts`

- Add state:
  - `composedBrief: MarketBrief | null` (the pre-verification brief),
  - `verifyChanges: string[]` (claim `target`s the verifier changed; empty until `verify_done`),
  - `claimsTotal: number` (from `verify_started`, for progress).
- In `case 'brief'`:
  - If `composedBrief` is null, set both `composedBrief` and `brief` to the payload (first emit).
  - Else set `brief` to the payload (second/revised emit). Leave `composedBrief` as the original.
- In `case 'verify_started'`: also store `claimsTotal: ev.data.claims_total`.
- In `case 'verify_done'`: keep existing behavior, and once the revised brief arrives, compute `verifyChanges` from `brief.verification.verdicts.filter(v => v.action !== 'kept').map(v => v.target)`. (Equivalently compute it lazily in the component from `brief.verification`.)
- Reset all three new fields in `reset()`, `startRun()`, and `loadRecent()` (set `verifying:false`, `verdicts:[]`, `composedBrief:null`, `verifyChanges:[]`). For recents, also persist/restore `verification` is already in `brief`, so the panel shows statically with no animation on reopen — that's correct (no live transition for a cached brief).

### 3.2 New "Verifier running" indicator (phase 2)
New component: `frontend/src/components/VerifyingToast.tsx`

- Renders only while `useRunStore(s => s.verifying)` is true.
- Fixed-position card (bottom-right, or a banner just under `RunHeader`), styled like the existing hover cards (reuse `--panel`, border, shadow; respect `prefers-reduced-motion`).
- Content: a small spinner + **"Claim Verifier auditing claims…"** + live progress `{verdicts.length} / {claimsTotal} checked`.
- Optional: as each `claim_verdict` arrives, show the latest claim `label` ticking past (subtle, 1 line).
- Mount it in `App.tsx` alongside the board so it overlays the already-rendered brief.

### 3.3 Animate the revision (phase 3)
- The brief is already on screen (composed). When the revised `brief` + `verify_done` arrive, use `verifyChanges` to animate the affected items in the existing section components (`BullBear.tsx`, `Risks.tsx`, `NewsList.tsx`, `AnomalyCard.tsx`, `SignalPanel.tsx`):
  - **Dropped** claims: the bullet/anomaly/signal that no longer exists in the revised brief should fade out + collapse height before being removed (CSS `transition: opacity .25s, max-height .3s`). Simplest implementation: render the composed brief's items, then on revision mark removed items with a `leaving` class for one animation frame before unmounting.
  - **confidence_downgraded** / **neutralized**: pulse the affected confidence chip / badge (a brief background/color flash) as its value changes.
- Reveal the **Verification panel** (section 08) with the existing `.tl-item` fade-in, and auto-scroll it into view once.
- On `verify_done`, dismiss `VerifyingToast` and add a small **"Verified ✓ — {dropped} dropped · {adjusted} adjusted"** stamp near the brief title / run header.

If a full diff animation is too much for v1, the acceptable minimum is: show the `VerifyingToast` during verify, then on completion flash/outline the changed sections briefly and slide in the Verification panel + the "Verified ✓" stamp.

### 3.4 Phase labelling in the status pill / agent log
- While `verifying` is true, change the run status indicator from "Researching…" to **"Verifying…"** (add a `verifying` consideration in `RunHeader` status rendering, or introduce a derived label). Return to "Done" after `verify_done` + revised brief.
- Add a `verify` branch to the step renderer in `AgentLogStrip.tsx` so the `type: 'verify'` LogStep shows as a chip (e.g. a ✓ shield icon + "verify · {dropped} dropped") with a hover card summarising `checked/supported/adjusted/dropped`. Right now that step renders nothing.

### 3.5 CSS
File: `frontend/src/index.css`
- Add styles for `.verifying-toast` (card + spinner), the `.leaving` fade/collapse for dropped items, a `.pulse-change` keyframe for downgraded chips, and the "Verified ✓" stamp.
- Gate all motion behind `@media (prefers-reduced-motion: reduce)` (the project already honors this elsewhere) — under reduced motion, skip animations and just show the final revised brief + panel.

## 4. Event / type reference
- `verify_started`: `{ claims_total: number }`
- `claim_verdict`: `{ target: string, label: string, verdict: 'supported'|'partial'|'unsupported', action: 'kept'|'confidence_downgraded'|'dropped'|'neutralized', note: string }`
- `verify_done`: `{ checked: number, supported: number, adjusted: number, dropped: number }`
- `brief` is emitted twice on live runs (composed, then revised); `brief.verification` is populated only on the revised emit.
- Types live in `frontend/src/lib/types.ts` (`ClaimVerdict`, `Verification`).

## 5. Edge cases
- **Offline / replay (`verify_llm=False`):** no verify events fire and `brief` is emitted once. `verifying` stays false → no toast, no animation; the brief renders normally. If `brief.verification` is absent, the section 08 panel and badges already no-op. Handle this (don't get stuck waiting for a verify phase that never comes).
- **Verifier makes no changes:** `verifyChanges` is empty → still show the toast during verify and the "Verified ✓ — 0 dropped" stamp + panel, but no item animations.
- **Recents:** opening a cached brief shows the Verification panel statically (from saved `brief.verification`) with no live transition — correct. Do not replay the toast.
- **Error/stop during verify:** if the stream errors after `verify_started`, clear `verifying` and fall through to the existing error/stopped handling; don't leave the toast spinning.
- **Latency:** the verifier adds noticeable time (a live AAPL run was ~107s including cold start). The toast doubles as a "still working" reassurance — keep it informative.

## 6. Acceptance criteria
- On a live run, the composed brief renders, then a visible "Claim Verifier running" indicator appears with progress, then the brief updates with a visible transition for any dropped/downgraded claims, the indicator disappears, and the Verification panel animates in.
- The status pill reads "Verifying…" during the verify phase; the agent-log strip shows a `verify` chip.
- Offline/replay and cached-recents paths show no toast and no broken waiting state.
- `prefers-reduced-motion` disables the animations but still ends in the correct final state.
- No backend changes; the eval cassettes (which skip verification) are unaffected.

## 7. Out of scope / known nit to fold in
- Minor content bug spotted live: the technical read rendered "…Volume trend is rising. **c3** [c1]" — a bare `c3` inline citation marker leaking next to the rendered `[c1]` pill. `stripInlineCites` (frontend/src/lib/format.ts) should also strip bare `cN` tokens (no parens/brackets). Not part of this feature, but cheap to fix alongside.
