# Tracker — Market Briefing Agent

Update at the end of every working session (rules.md #12). Status: `todo` / `wip` / `done` / `blocked` / `cut`.

**Started:** 2026-06-13  ·  **Target ship:** _(date)_  ·  **Current phase:** 2

## Phase 0 — Scaffold
- [x] Repo init, layout, license, Makefile
- [x] FastAPI hello + /api/health
- [x] Vite React TS + Tailwind placeholder
- [x] Linters/test runners (BE+FE) configured
- [x] .env.example + gitleaks pre-commit
- [x] GitHub Actions CI green

## Phase 1 — Tool layer
- [x] yfinance adapter + 24h disk cache
- [x] get_price_history (compact output) + get_fundamentals
- [x] compute_indicators (pure fn)
- [x] detect_anomalies (pure fn)
- [x] search adapter (ddgs / tavily) + fetch_page
- [x] Fixtures: 5 tickers + labeled anomalies
- [x] Detector tests pass at 100%
- [x] tools demo CLI works

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
| 2026-06-13 | 1 | **Phase 1 complete.** Tool layer done: yfinance adapter + 24h disk cache, get_price_history (compact weekly aggregates + notable days) + get_fundamentals, compute_indicators + detect_anomalies (pure fns), ddgs/Tavily search + trafilatura fetch_page. 5 frozen 1y OHLCV fixtures (AAPL/MSFT/NVDA/RELIANCE.NS/TSLA) + hand-labeled `labels.json`; detector regression test asserts 100% match. `run.py` demo CLI prints every tool's output. 70 tests pass, ruff+mypy strict clean. | Opus drives decisions; Sonnet 4.6 subagent wrote run.py + labels test (Fable 5 unavailable). One ruff fixup (unused `sys` import) applied by hand. |

## Decisions Log
| Date | Decision | Why |
|---|---|---|
| 2026-06-13 | uv for Python env management, pinned to 3.12 | System Python 3.14 too new for data libs; uv pins per-project and matches CI |
| 2026-06-13 | Tailwind v4 (via @tailwindcss/vite) instead of v3 | Current stable; docs just say "Tailwind"; CSS-first config, less boilerplate |
| 2026-06-13 | gitleaks hook via committed .githooks/ + core.hooksPath (no pre-commit framework) | Zero extra dependency; `make setup` wires it on any clone |
| 2026-06-13 | Vite 8 ships TypeScript ~6.0 | Template default; strict mode on, no issues |
| 2026-06-13 | `labels.json` is a frozen regression baseline (date, kind, severity per ticker), not a separate hand-curated truth set | Detector is deterministic; high-severity events map to real market moves (e.g. MSFT 2026-01-29 −10% earnings crash w/ volume surge + gap). Snapshotting locks detector behavior; refreezing fixtures requires re-inspecting + re-labeling. |
| 2026-06-13 | Fixtures committed to git (~16KB parquet each) | CI must run the detector regression test fully offline (rules.md: CI never makes live calls). |
