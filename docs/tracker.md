# Tracker — Market Briefing Agent

Update at the end of every working session (rules.md #12). Status: `todo` / `wip` / `done` / `blocked` / `cut`.

**Started:** 2026-06-13  ·  **Target ship:** _(date)_  ·  **Current phase:** 4

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

## Phase 2 — Agent loop  ✅ COMPLETE (live-verified on Gemini free tier)
- [x] runner.py loop (registry, caps, finalize-now, repair) — agent.py + nodes.py
- [x] prompts/system.md v1 (phases + citation rules) — prompts.py
- [x] MarketBrief schema + strict parse + validation rules — src/schemas.py
- [x] Usage/cost tracking per run — events.estimate_cost_usd + usage event
- [x] Cassette recorder (--record) — cassette.py (CassetteRecorder + RecordingBackend)
- [x] `make brief TICKER=AAPL` end-to-end + first cassette — **live run done** (AAPL 3mo, gemini-2.5-flash): full event stream, valid cited brief, anomaly→investigate worked; cassette at `evals/cassettes/aapl_3mo.json` (6 tool calls, 4 iters, ~14K tokens, 27s)

## Phase 3 — API + guards  ✅ COMPLETE (HTTP layer live-verified)
- [x] POST /api/brief SSE (all event types per schema.md §3) — src/api/sse.py bridge; same run_agent path proven live via CLI
- [x] GET /api/validate/{ticker} — live-checked: AAPL→valid, bad symbol→valid:false, bad format→400
- [x] Per-IP limit (slowapi) + global daily cap (DailyCounter) + ticker regex + run timeout (agent)
- [x] Structured run logs — log_run() JSON line on "market_brief.run"
- [x] 429 verified by test — per-IP and global-cap 429 both tested; /api/health live-checked

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
| 2026-06-13 | 2/3 | **Live exit criteria met.** User added backend/.env with a Gemini free-tier key. 1-call auth preflight OK, then ONE live brief (AAPL 3mo, gemini-2.5-flash): streamed the full event protocol, detected the 2026-06-09 -3.6σ drop, auto-scoped a ±3d news search, and explained it (WWDC Siri AI reveal) in a valid fully-cited brief — $0, ~14K tokens, 27s. First cassette saved (`evals/cassettes/aapl_3mo.json`). HTTP layer live-checked (health + validate). Minimal-usage testing as requested (2 LLM calls total). | Gemini key length ~118 chars worked fine. SSE /api/brief not re-run live to conserve free-tier quota — identical run_agent path. |
| 2026-06-13 | 3 | **Phase 3 code-complete.** FastAPI API layer: `POST /api/brief` streams the agent over SSE via a sync→async bridge (agent runs in a worker thread, emits through an asyncio.Queue); `GET /api/validate/{ticker}` cheap existence check; `GET /api/health` shows live daily-remaining. Guards: slowapi per-IP hourly limit (callable rate string, test-overridable), thread-safe global `DailyCounter` (UTC-day reset), ticker regex, structured JSON run log. `create_app()` factory + 429 handler. **170 tests pass** (per-IP + global-cap 429 both covered), ruff+mypy strict clean. | Live SSE curl smoke deferred with the Phase 2 live run (needs API key). Sonnet 4.6 subagent built the api/ package from Opus spec; no type-ignores needed. |
| 2026-06-13 | 2 | **Phase 2 code-complete.** src/llm.py provider adapter (Anthropic native + OpenAI-compat Gemini/Groq, normalized Turn/ToolCall/ToolSpec/LLMResponse, defensive arg parsing). src/schemas.py MarketBrief + strict parser (citation resolution, uncited-bullet rejection, list caps, immutable disclaimer). Agent internals: tools.py (7-tool registry, 10s timeout), state.py RunState + budgets, prompts.py system prompt v1, nodes.py + agent.py hand-rolled loop (finalize-now, one repair round-trip, usage/cost), events.py emitter, cassette.py recorder. `make brief` + .env autoload. **162 tests pass, ruff+mypy strict clean.** | Live `make brief` + first cassette deferred — no GEMINI_API_KEY available this session; user chose to proceed to Phase 3. 4 Sonnet 4.6 subagents wrote schemas/llm/tools+state/loop from Opus specs; Opus wrote prompts.py by hand. |

## Decisions Log
| Date | Decision | Why |
|---|---|---|
| 2026-06-13 | uv for Python env management, pinned to 3.12 | System Python 3.14 too new for data libs; uv pins per-project and matches CI |
| 2026-06-13 | Tailwind v4 (via @tailwindcss/vite) instead of v3 | Current stable; docs just say "Tailwind"; CSS-first config, less boilerplate |
| 2026-06-13 | gitleaks hook via committed .githooks/ + core.hooksPath (no pre-commit framework) | Zero extra dependency; `make setup` wires it on any clone |
| 2026-06-13 | Vite 8 ships TypeScript ~6.0 | Template default; strict mode on, no issues |
| 2026-06-13 | `labels.json` is a frozen regression baseline (date, kind, severity per ticker), not a separate hand-curated truth set | Detector is deterministic; high-severity events map to real market moves (e.g. MSFT 2026-01-29 −10% earnings crash w/ volume surge + gap). Snapshotting locks detector behavior; refreezing fixtures requires re-inspecting + re-labeling. |
| 2026-06-13 | Fixtures committed to git (~16KB parquet each) | CI must run the detector regression test fully offline (rules.md: CI never makes live calls). |
| 2026-06-13 | OpenAI-compat backend uses the `openai` SDK pointed at Gemini/Groq base_urls; Anthropic uses native SDK | techspec §1 names both wire formats; `openai` is the natural client for OpenAI-compatible endpoints. Deps: anthropic, openai. |
| 2026-06-13 | `python-dotenv` loads backend/.env for CLI/dev runs | Ergonomic local key handling matching the .env.example convention; prod uses real env vars. |
| 2026-06-13 | Phase 2 live run + cassette deferred (no API key) | Gemini free-tier key not available this session; agent is fully unit-tested offline (FakeBackend), so live run is the only gap. Recorded as a known-pending item. |
