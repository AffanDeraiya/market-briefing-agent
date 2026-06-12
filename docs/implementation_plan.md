# Implementation Plan — Market Briefing Agent

Phased; every phase ends runnable and committed. Estimates assume evenings/weekends; total ≈ 4–5 weekends. Backend-first: the agent loop is the product.

## Phase 0 — Scaffold (half day)
- Repo init per techspec §9, MIT license, Makefile (`dev`, `test`, `lint`).
- FastAPI hello + `/api/health`; Vite React TS + Tailwind placeholder.
- ruff/mypy/pytest + eslint/prettier/vitest configured; `.env.example`; gitleaks pre-commit.
- GitHub Actions: lint + tests.
- **Exit:** CI green on first push.

## Phase 1 — Tool layer, no LLM (1–1.5 days)
- yfinance adapter + 24h disk cache; `get_price_history`, `get_fundamentals` (compact outputs per schema.md §2).
- `compute_indicators`, `detect_anomalies` as pure functions.
- Search adapter (ddgs default, Tavily behind env) + `fetch_page` (trafilatura).
- **Tests are the point of this phase:** fixtures for 5 tickers (incl. known-event windows), hand-labeled anomalies, detector at 100%; cache behavior; adapter error paths.
- **Exit:** `python -m app.tools.demo AAPL` prints every tool's output.

## Phase 2 — Agent loop (1–1.5 days) ← the showpiece
- `agent/runner.py`: hand-rolled Messages-API tool-use loop per schema.md §1 (tool registry, caps, finalize-now injection, usage tracking, repair round-trip).
- `prompts/system.md` v1 with phase strategy + citation rules + disclaimer rule.
- `MarketBrief` Pydantic schema + strict parse.
- Cassette recorder (`--record`) wrapping the Anthropic client and tool I/O.
- **Exit:** `make brief TICKER=AAPL` streams events to stdout and writes a valid brief JSON; one cassette recorded.

## Phase 3 — API + guards (1 day)
- `POST /api/brief` SSE per schema.md §3; `GET /api/validate/{ticker}`.
- slowapi per-IP, global daily counter, ticker regex, run timeout, CORS.
- Structured JSON run logs.
- **Exit:** curl SSE shows full event stream; 6th brief in an hour → 429.

## Phase 4 — Frontend: Run view (1.5–2 days)
- SSE client, Zustand run store, Home (input + validation + chips + period).
- Timeline rail (all item types incl. anomaly_focus), status pill, cost meter.
- Brief renderer: snapshot strip, anomaly cards, bull/bear, citation chips + popovers.
- **Exit:** Flow A end-to-end in browser.

## Phase 5 — Chart + polish (1 day)
- Recharts price/volume from `chart_data`, anomaly markers, marker↔card linking, pulse on `anomaly_focus`.
- Timeline auto-collapse, Markdown export, sessionStorage recents, all error/429/budget/waking states from webapp_flow §6.
- **Exit:** demo path feels recordable.

## Phase 6 — Evals (1 day)
- Cassette replay harness (mock Anthropic client); 6–8 recorded runs across tickers/periods.
- Gates: detector 100% (already), citation faithfulness ≥95%, structure ≥98%.
- `make eval` (offline) in CI; `make eval-live` regenerates cassettes + markdown report.
- Iterate `prompts/system.md` if faithfulness misses — prompt changes require re-running evals (rules.md).
- **Exit:** eval report table exists; CI gate active.

## Phase 7 — Ship (1 day)
- Dockerfile multi-stage + compose; deploy Render (BE) + Vercel (FE); env vars + **Anthropic spend cap set first**.
- README: demo GIF, architecture diagram (loop + tools), eval table, quickstart ≤5 commands, Limitations.
- Lighthouse ≥90; manual QA all flows incl. rate-limit and stopped states.
- **Exit:** PRD §8 satisfied; resume Projects bullet updated with URL + a real metric (e.g., citation faithfulness %).

## Dependencies & parallelism
0→1→2→3 strictly sequential. 4–5 can start once §3 event shapes are frozen (after Phase 3). 6 needs Phase 2 cassettes. 7 last.

## Scope-cut order (time pressure)
Markdown export → recents list → marker pulse linking → period selector (fix at 3mo) → `fetch_page` tool (snippets only). Never cut: anomaly investigation, citations, evals, guards, timeline.

## Post-v1 backlog (do not start before ship)
Multi-ticker compare · BYO key · brief permalinks · sector context tool · project #2 (Claim Verifier, reusing this scaffold).
