# Tracker — Market Briefing Agent

Update at the end of every working session (rules.md #12). Status: `todo` / `wip` / `done` / `blocked` / `cut`.

**Started:** 2026-06-13  ·  **Target ship:** _(date)_  ·  **Current phase:** 1

## Phase 0 — Scaffold
- [x] Repo init, layout, license, Makefile
- [x] FastAPI hello + /api/health
- [x] Vite React TS + Tailwind placeholder
- [x] Linters/test runners (BE+FE) configured
- [x] .env.example + gitleaks pre-commit
- [x] GitHub Actions CI green

## Phase 1 — Tool layer
- [ ] yfinance adapter + 24h disk cache
- [ ] get_price_history (compact output) + get_fundamentals
- [ ] compute_indicators (pure fn)
- [ ] detect_anomalies (pure fn)
- [ ] search adapter (ddgs / tavily) + fetch_page
- [ ] Fixtures: 5 tickers + labeled anomalies
- [ ] Detector tests pass at 100%
- [ ] tools demo CLI works

## Phase 2 — Agent loop
- [ ] runner.py loop (registry, caps, finalize-now, repair)
- [ ] prompts/system.md v1 (phases + citation rules)
- [ ] MarketBrief schema + strict parse + validation rules
- [ ] Usage/cost tracking per run
- [ ] Cassette recorder (--record)
- [ ] `make brief TICKER=AAPL` end-to-end + first cassette

## Phase 3 — API + guards
- [ ] POST /api/brief SSE (all event types per schema.md §3)
- [ ] GET /api/validate/{ticker}
- [ ] Per-IP limit + global daily cap + ticker regex + run timeout
- [ ] Structured run logs
- [ ] 429 verified by test

## Phase 4 — Frontend Run view
- [ ] SSE client + Zustand store
- [ ] Home: input + inline validation + chips + period
- [ ] Timeline rail (step / tool_call / tool_result / anomaly_focus / cost meter)
- [ ] Brief renderer (snapshot, anomalies, bull/bear, citations + popovers)
- [ ] Status pill + disclaimer footer

## Phase 5 — Chart + polish
- [ ] Price/volume chart + anomaly markers
- [ ] Marker ↔ card linking + pulse
- [ ] Timeline auto-collapse / re-expand
- [ ] Markdown export + sessionStorage recents
- [ ] All states: errors, 429, budget, server-waking, stopped

## Phase 6 — Evals
- [ ] Cassette replay harness (mock client)
- [ ] 6–8 recorded runs committed
- [ ] Citation faithfulness checker ≥95% → record: ____
- [ ] Structure compliance ≥98% → record: ____
- [ ] `make eval` in CI as gate; `make eval-live` report

## Phase 7 — Ship
- [ ] Anthropic spend cap set
- [ ] Docker + Render + Vercel deployed
- [ ] README: GIF, architecture diagram, eval table, quickstart, Limitations
- [ ] Lighthouse ≥90 + full manual QA
- [ ] Resume bullet updated with live URL + metric

## Session Log
| Date | Phase | Done | Blockers / notes |
|---|---|---|---|
| 2026-06-13 | 0 | Repo pushed to GitHub; full Phase 0 scaffold: base files + gitleaks hook, backend (uv/py3.12, FastAPI /api/health, ruff+mypy strict+pytest), frontend (Vite + React 18 + Tailwind v4 + vitest), Makefile, CI green on first push | Local tooling installed via winget: make, gitleaks, uv |

## Decisions Log
| Date | Decision | Why |
|---|---|---|
| 2026-06-13 | uv for Python env management, pinned to 3.12 | System Python 3.14 too new for data libs; uv pins per-project and matches CI |
| 2026-06-13 | Tailwind v4 (via @tailwindcss/vite) instead of v3 | Current stable; docs just say "Tailwind"; CSS-first config, less boilerplate |
| 2026-06-13 | gitleaks hook via committed .githooks/ + core.hooksPath (no pre-commit framework) | Zero extra dependency; `make setup` wires it on any clone |
| 2026-06-13 | Vite 8 ships TypeScript ~6.0 | Template default; strict mode on, no issues |
