# Market Briefing Agent

**Enter a stock ticker → get a cited, structured market brief in ~60 seconds, and watch the agent reason live.**

A single LangGraph agent that doesn't just summarize a stock — it **detects anomalies in the price/volume data deterministically, then autonomously investigates each one** with date-scoped news searches before composing the brief. An independent **Claim Verifier** pass then audits every cited claim against the retrieved evidence and refines the brief. Every bullet carries a citation; the parser rejects uncited claims.

🔗 **Live demo:** https://market-briefing-agent.vercel.app  ·  **API health:** https://market-briefing-agent.onrender.com/api/health

> Note: the demo backend is on Render's free tier — the first request after idle can take ~30–60s to wake.

> ⚠️ **Not financial advice.** This is an engineering portfolio project. Briefs are AI-generated analyses of public data for informational purposes only — not investment advice, recommendations, or solicitations.

---

## Why it's not a "stock summary bot"

| | A typical AI stock tool | Market Briefing Agent |
|---|---|---|
| Numbers | LLM eyeballs/guesses them | **Pure-Python, unit-tested**; the LLM never computes |
| Anomalies | Ignored or hand-waved | **Detected deterministically** (>2.5σ moves, 3× volume, gaps), then **autonomously investigated** with date-scoped searches |
| Citations | "Sources" appended loosely | **Every bullet cited**; uncited claims rejected at parse; fabricated URLs dropped by a grounding guard |
| Trust | Take it or leave it | **Independent Claim Verifier** downgrades / drops / neutralizes unsupported claims and shows what changed |
| Transparency | Black box | **Live reasoning timeline** — every thought, tool call, and result streams to the UI |

## Architecture

```
React SPA ──POST /api/brief──▶ FastAPI (slowapi per-IP + global daily cap)
                │ SSE stream of agent events
                ▼
   LangGraph StateGraph (agent.py) — node bodies hand-written in nodes.py:
   validate_input → reason (multi-step tool-use loop) → parse_and_enrich → verify → emit
       │ llm.complete(...)                    │ tool registry
       ▼                                      ▼
   src/llm.py provider adapter            Tool layer (7 tools, Pydantic I/O)
     ├─ gemini / groq / openrouter          ├─ market_data (yfinance + 24h disk cache)
     │   (OpenAI-compatible)                ├─ indicators / detect_anomalies (pure pandas)
     └─ anthropic (native SDK, optional)    ├─ news / search (ddgs | tavily)
                                            └─ fetch_page (trafilatura, SSRF-guarded)
```

- **LangGraph** is the orchestration layer only; the LLM↔tool loop, tools, provider adapter, parser, and grounding logic are all hand-written (and interview-explainable).
- `src/llm.py` normalizes provider wire formats (OpenAI-style `tool_calls`, Anthropic `tool_use`/`tool_result`) into internal `ToolCall`/`ToolResult` types — the loop never touches raw provider JSON.
- **Stateless backend, no database.** One brief = one agent run = one SSE stream. Disk cache (`.cache/`) for yfinance only.
- Tool outputs are compact by design (weekly aggregates + notable days, never raw OHLCV); raw chart data reaches the UI via the `chart_data` SSE event, not through the LLM.

## Tech stack

**Backend** — Python 3.12, FastAPI + SSE (`sse-starlette`), LangGraph, Pydantic (typed at every boundary), yfinance, pandas, trafilatura, `ddgs`. Tooling: `uv`, ruff, mypy (strict), pytest.

**Frontend** — React 18, Vite, TypeScript (strict), Tailwind v4, Zustand, Recharts. Tooling: vitest, eslint, prettier.

**LLM providers** — pluggable via one env var: `gemini` (default, free tier), `groq`, `openrouter` (all OpenAI-compatible), or `anthropic` (native SDK). Dev + the public demo run entirely on free tiers at $0.

## Evals

Three automated gates, all run offline by replaying recorded cassettes through the **real graph** (zero network / zero LLM in CI):

| Gate | Target | Current |
|---|---|---|
| Anomaly-detector correctness (frozen fixtures) | 100% (deterministic) | **100%** |
| Citation faithfulness (cited source exists in tool results) | ≥ 95% | **100%** |
| Structure compliance (brief parses against schema) | ≥ 98% | **100%** |

Measured across a 6-ticker corpus (AAPL, MSFT, NVDA, TSLA, RELIANCE.NS) over 3mo/6mo/1y. Run it yourself with `make eval`.

## Quickstart

Prereqs: Python 3.12 + [`uv`](https://docs.astral.sh/uv/), Node 18+, and a free [Gemini API key](https://aistudio.google.com/).

```bash
git clone https://github.com/AffanDeraiya/market-briefing-agent.git
cd market-briefing-agent
cp .env.example backend/.env          # then paste your GEMINI_API_KEY
make setup                            # installs backend (uv) + frontend (npm) + git hooks
make dev-backend                      # terminal 1 → FastAPI on :8000
make dev-frontend                     # terminal 2 → Vite on :5173
```

Open http://localhost:5173 and enter a ticker. Or run the agent straight from the CLI:

```bash
make brief TICKER=AAPL PERIOD=3mo     # streams the full event log to stdout
make eval                             # offline eval gates (cassette replay)
make test                             # backend pytest + frontend vitest
make lint                             # ruff + mypy + eslint + prettier
```

## Project layout

```
backend/
  src/agents/market_brief/   # state, prompts, nodes, tools, agent (graph), run — one agent per dir
    utils/                    # market_data, indicators, anomalies, search, fetch, verify, symbols
  src/api/                    # FastAPI routes, SSE bridge, rate-limit guards
  src/llm.py                  # provider adapter (gemini/groq/openrouter/anthropic → normalized types)
  src/schemas.py              # MarketBrief Pydantic schema + strict cited-claim parser
  evals/                      # cassette replay harness + faithfulness/structure checks
frontend/src/
  components/                 # Board, chart, brief sections, verifier walkthrough/banner
  lib/                        # sse.ts, walkthrough.ts, types, format
  store/                      # Zustand run store (event reducer + state machine)
docs/                         # PRD, techspec, schema (the contract), design, rules, tracker
```

## Safety & cost guards

Designed to be left deployed unattended on a personal key:

- **Per-IP** hourly + daily rate limits and **global daily cap** (slowapi + a thread-safe counter with refund-on-error).
- **Per-run budgets:** `MAX_TOOL_CALLS=15`, `MAX_ITERATIONS=20`, max-tokens on every LLM call, 10s tool timeouts, 120s run timeout.
- **SSRF-guarded `fetch_page`:** blocks private/metadata IPs, scheme allowlist, per-hop redirect re-validation, body-size cap.
- **No secrets in the repo:** env vars only, `.env.example` with dummies, gitleaks pre-commit hook.
- **Grounding guard:** news/web citations whose URL never appeared in a tool result are dropped at finalize — so a weaker model can't smuggle in a fabricated source.

## Limitations

- **Daily granularity**, not intraday/realtime — yfinance end-of-day bars.
- **News coverage** depends on `ddgs`/Tavily; sparse-news tickers may yield "no clear public cause found" (by design — honesty over invention).
- **Single ticker** per run; no multi-ticker comparison, portfolio tracking, or accounts (v2 candidates).
- **Free-tier hosting** (Render) cold-starts; the UI shows a "waking up" state on first hit.
- Not financial advice — see the disclaimer above.

## License

MIT — see [LICENSE](LICENSE).
