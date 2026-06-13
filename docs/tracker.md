# Tracker — Market Briefing Agent

Update at the end of every working session (rules.md #12). Status: `todo` / `wip` / `done` / `blocked` / `cut`.

**Started:** 2026-06-13  ·  **Target ship:** _(date)_  ·  **Current phase:** 6 (Phases 4 & 5 code-complete) · **active branch:** `working` (master = final; merge after full testing)

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

## Phase 4 — Frontend Run view  (design finalized: Live Investigation Board)  ✅ CODE-COMPLETE
- [x] **Backend follow-up (schema-driven):** attach `snapshot.low_52w/high_52w` + structured `indicators` dict to MarketBrief deterministically from tool outputs (no prompt change; cassette hand-updated; 172 backend tests)
- [x] SSE client (`lib/sse.ts` fetch-stream) + Zustand store (state machine, event reducer, recents)
- [x] Home: input + inline validation + chips + period + recent briefs (sessionStorage)
- [x] Agent-log strip: tool/anomaly/compose steps, per-step hover cards, run-summary card, budget bar
- [x] Board: primary chart (anomaly pin + crosshair + bidirectional hover link), snapshot bar, 52-week range bar
- [x] Brief renderer (technical + indicator chips, anomaly, news, bull/bear, risks, citations + popovers) streaming in with skeleton shimmer
- [x] Status pill + disclaimer footer + export (Copy MD / download .md)
- [x] Live wiring: `startRun()` streams POST /api/brief (demo fallback offline); HTTP contract smoke-tested (health/validate/CORS, no LLM cost)
- Deferred: one paid live end-to-end SSE run for visual QA (Gemini quota); Recharts migration → Phase 5 (chart currently hand-rolled SVG, pixel-faithful to mockup). 31 frontend tests pass; build+eslint clean.

## Phase 5 — Chart + polish  ✅ CODE-COMPLETE (on `working` branch)
- [x] Price/volume chart + anomaly markers — migrated to **Recharts base + custom anomaly overlay** (techspec amended)
- [x] Marker ↔ card linking + pulse — preserved through the Recharts migration
- [x] Timeline (agent-log) auto-collapse to summary on success / re-expand
- [x] Markdown export (Copy MD + download .md) + sessionStorage recents (restore real chart)
- [x] All states: error (parse/upstream/timeout/internal), 429 rate-limited (Retry-After), budget daily-cap, server-waking (one auto-retry), stopped — webapp_flow §6 copy; prefers-reduced-motion honored
- Deferred (small follow-ups, not blocking): live `chart_data.ohlcv` is still emitted empty by the backend, so the LIVE chart has no series yet (demo fixture chart is fully wired) — populate from `get_price_history` weekly aggregates in a later pass; chart area-fill tint omitted (Recharts Line-only). 46 frontend tests pass; build+eslint clean.

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
| 2026-06-13 | 4 | **UI design finalized: Live Investigation Board.** After 3 mockup rounds (12 variants across `mockups.html` / `_v2` / `_v3`), user picked the Investigation Board (was variant I) — light warm-paper, no sidebar, chart-primary, brief assembles inline. Installed the `taste-skill` design skills project-locally (`.claude/skills/`). Built refined canonical reference `mockups/investigation_board.html` (Opus): agent-log strip with per-step hover detail cards + run-summary card + budget bar; chart anomaly pin + crosshair + bidirectional hover link; styled citation popovers. Per user vote, added indicator chips, 52-week range bar, chart crosshair, skeleton-shimmer streaming, Markdown export, recent-briefs-on-Home; light-only for v1. Rewrote `design.md` + `webapp_flow.md` to the new layout; extended `schema.md` MarketBrief with `snapshot.low_52w/high_52w` + structured `indicators` (deterministically attached). Mockup verified headless (jsdom, 0 errors). | Next session: run the phase goal to build Phase 4 against this design. Backend must add the structured snapshot/indicator fields first (logged as Phase 4 item 1). |
| 2026-06-13 | 5 | **Phase 5 code-complete + first live UI-era run (on `working` branch).** New `working` branch created off master for all ongoing commits (master reserved for final; merge after full testing). **One live AAPL 3mo run** (Gemini free tier, $0, ~22s): valid fully-cited brief, WWDC anomaly explained — re-recorded the `aapl_3mo` cassette authentically; fixed that `snapshot.low_52w/high_52w` come from `get_price_history` (not fundamentals). Phase 5 (frontend, Sonnet subagents): chart migrated to **Recharts + custom anomaly overlay** (techspec amended); agent-log auto-collapse; full lifecycle states (429/budget/server-waking/stopped/error per webapp_flow §6); export (.md + clipboard); recents restore real chart; prefers-reduced-motion. 46 FE tests + 172 BE tests pass. | Opus: live run, 52w fix, decisions, verification, commits; Sonnet 4.6: Recharts migration + states/polish. Deferred: live `chart_data.ohlcv` population (demo chart works), chart area-fill tint. |
| 2026-06-13 | 4 | **Phase 4 code-complete (Investigation Board frontend).** Backend: deterministic `indicators` + `snapshot.low_52w/high_52w` enrichment attached from tool outputs (172 tests). Frontend (React 18 + TS strict + Tailwind v4 + Zustand): full Run view — agent-log strip with hover detail + run-summary cards + budget bar, chart with anomaly pin + crosshair + bidirectional hover link, snapshot bar, 52w range bar, indicator chips, brief sections 01–06 streaming with skeleton shimmer, citation popovers, status pill, Copy-MD/Export, Home with recents. Real SSE wired (`startRun` → POST /api/brief) with offline demo fallback; HTTP contract smoke-tested (health/validate/CORS, zero LLM cost). 31 FE tests, build+eslint clean. 4 commits this session. | Coding delegated to Sonnet 4.6 subagents (chart deviated to hand-rolled SVG → Recharts deferred to Phase 5); Opus did backend enrichment + decisions + verification + commits. mockups/ + .claude/ now gitignored. |
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
| 2026-06-13 | UI = **Live Investigation Board**, light-only for v1 | User found dark themes "vibe coded" / not premium across two rounds; the warm-paper, document-style board reads as a research desk and makes the anomaly-investigation differentiator visible (log strip + chart pin + dedicated section). Dark mode explicitly deferred post-v1. |
| 2026-06-13 | Snapshot/indicators carried as **structured** brief fields, attached deterministically | Indicator chips + 52w range bar must render from numbers, not parsed prose; keeps "LLM never computes numbers" — values come from `get_fundamentals`/`compute_indicators`, backend attaches them to MarketBrief. No new SSE events needed (hover cards/crosshair/run-summary all map to existing `tool_call`/`tool_result`/`chart_data`/`usage`). |
| 2026-06-13 | Installed `leonxlnx/taste-skill` into `.claude/skills/` (project-scoped, uncommitted) | Anti-slop design guidance (design-taste-frontend / minimalist-ui / high-end-visual-design) for the frontend phase; MIT-licensed. |
