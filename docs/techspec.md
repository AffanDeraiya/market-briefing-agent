# Tech Spec — Market Briefing Agent

## 1. Stack

| Layer | Choice | Notes |
|---|---|---|
| Agent | **LangGraph `StateGraph`** (`agent.py`) wiring hand-written nodes (`nodes.py`): validate_input → reason (multi-step tool-use loop) → parse_and_enrich → verify (Claim Verifier) → emit. See schema.md §1 | Dep: `langgraph` — used only as the orchestration layer; node bodies, the LLM↔tool loop, `llm.py` provider adapter, tools, parser and grounding stay ours. Nodes consume normalized types from `llm.py`, not provider wire formats |
| LLM adapter | `src/llm.py` — two backends behind `LLM_PROVIDER`: `anthropic` (native `anthropic` SDK, Messages API `tools`) and `gemini`/`groq` (the `openai` SDK pointed at the provider's OpenAI-compatible `base_url`) | Normalizes Anthropic `tool_use`/`tool_result` blocks and OpenAI-style `tool_calls` into internal `ToolCall`/`ToolResult` types. Deps: `anthropic` (native blocks), `openai` (OpenAI-compat clients for Gemini/Groq) |
| Model | Dev/demo: `gemini-2.5-flash` on the **free tier** (~1,500 req/day, $0). Showcase/cassette recording: `claude-haiku-4-5` | `LLM_PROVIDER` + `LLM_MODEL` env vars; zero spend until Anthropic budget exists |
| Backend | Python 3.11+, FastAPI, uvicorn | Async throughout |
| Market data | `yfinance` | No key. Wrapped in adapter (`tools/market_data.py`) with 24h disk cache |
| Indicators/anomalies | pandas + numpy, pure functions | Deterministic, unit-tested, no LLM |
| Search | `ddgs` default; Tavily optional (`SEARCH_PROVIDER`) | Pluggable provider interface |
| Page extraction | `trafilatura` | Article text from URLs |
| Streaming | SSE (`sse-starlette`) | One-way agent→UI event stream |
| Rate limiting | `slowapi` per-IP + custom global daily counter | |
| Frontend | React 18 + Vite + TypeScript + Tailwind + Zustand | |
| Charts | Recharts (base) + custom SVG anomaly overlay | Recharts draws price line / volume bars / axes / crosshair tooltip; the amber anomaly marker, its pin label, and the bidirectional hover-link to the Anomaly card are a thin custom overlay (the investigation marker is the product differentiator, kept bespoke). Phase 4 shipped a hand-rolled SVG stand-in; Phase 5 migrates the base to Recharts. |
| Testing | pytest + httpx; Vitest (FE) | Cassette-based agent tests (see §7) |
| Lint | ruff + mypy; eslint + prettier | CI-enforced |
| CI | GitHub Actions: lint → unit tests → eval smoke | No live API calls in CI |
| Container/deploy | Docker multi-stage; Render (BE) + Vercel (FE) | |

## 2. Architecture

```
Browser (React SPA)
   │ POST /api/brief  → SSE event stream
   ▼
FastAPI ── slowapi (per-IP) ── global daily cap middleware
   │
   ▼
Agent loop (hand-rolled, schema.md §1)
   │ llm.complete(tools=[...])           │ execute tool
   ▼                                     ▼
llm.py adapter                   Tool layer (typed, pure where possible)
   ├→ Gemini free tier (dev/demo)
   └→ Anthropic API (showcase)
                                   ├─ market_data (yfinance + disk cache)
                                   ├─ indicators / anomaly detector (pandas)
                                   ├─ news/search (ddgs|tavily adapter)
                                   └─ fetch_page (trafilatura)
```

- **Stateless backend**; no database. Disk cache (`.cache/`) for yfinance responses only.
- One brief request = one agent run = one SSE stream. No background jobs in v1.

## 3. The Agent Loop (implementation requirements)

Implemented in `src/agents/market_brief/agent.py` + `nodes.py` (readable — it's the showpiece). `llm.py` defines the normalized contract: internal `Turn`/`ToolCall`/`ToolSpec`/`LLMResponse` types; `AnthropicBackend` serializes history to Messages-API `tool_use`/`tool_result` blocks, `OpenAICompatBackend` (Gemini, Groq) serializes the same history to chat `tool_calls` / `role:"tool"` messages (note: OpenAI-format `arguments` arrive as a JSON string — parse defensively). Both APIs are stateless: memory = full history resent per call; tool outputs stay compact so a run fits in ~20–40K tokens.

1. Build system prompt (from `prompts.py`) + user message with ticker/period.
2. Call `llm.complete(messages, tools, max_tokens=MAX_OUTPUT_TOKENS)` — the adapter handles provider wire formats.
3. If the normalized response contains tool calls: execute each via the tool registry, append normalized tool results, emit SSE events (`tool_call`, `tool_result`), loop.
4. Stop conditions: `end_turn` with final JSON brief; or `MAX_TOOL_CALLS`/`MAX_ITERATIONS` reached → ask model to finalize with what it has; or hard error → `error` event.
5. Track usage (tokens per call, cumulative) and per-step wall time; emit in `usage` event.
6. Final text must parse as `MarketBrief` (schema.md §4); on parse failure, one repair attempt (re-ask with validation errors), then fail honestly.

Prompts live in `prompts.py` (one module per agent, owner's convention). The system prompt encodes the phase strategy (snapshot → indicators → anomalies → investigate each → fundamentals → compose) but the model chooses tools freely within caps — that freedom is what makes the timeline interesting.

## 4. Tool Layer Rules

- Every tool: Pydantic input/output models, ≤10s timeout, returns compact JSON (token-efficient summaries, not raw dumps — e.g., price history returns weekly aggregates + notable days, not 250 raw rows).
- Tool registry maps Anthropic tool schema → handler. Adding a tool = one file + registry entry.
- yfinance adapter caches `{ticker, period}` responses on disk for 24h (cuts latency, API strain, and makes local dev/demo snappy).
- Search results capped at 5/call; fetch_page output capped at ~2000 tokens.

## 5. API Contract (full event shapes in schema.md §3)

| Endpoint | Method | Notes |
|---|---|---|
| `/api/health` | GET | status, model, daily budget remaining |
| `/api/validate/{ticker}` | GET | cheap pre-check: ticker exists (cached), name/exchange |
| `/api/brief` | POST → SSE | `{ticker, period}`; streams `step`/`tool_call`/`tool_result`/`brief`/`usage`/`error` |

429 with `retry_after_s` when rate-limited (before stream starts).

## 6. Guards & Limits (env-configurable, defaults)

| Limit | Default |
|---|---|
| Briefs per IP | 5/hour |
| Global briefs | 100/day |
| Tool calls per run | 15 |
| Loop iterations | 20 |
| Output tokens per LLM call | 4096 |
| Tool execution timeout | 10s |
| Whole-run timeout | 120s |
| Ticker input | regex `^[A-Z0-9.\-]{1,12}$` + validate endpoint |

## 7. Evaluation Harness (`evals/`)

Three gates, all runnable offline:

1. **Anomaly detector correctness** — frozen OHLCV fixtures (`evals/fixtures/*.parquet`, 5 tickers incl. known events e.g. crash days) with hand-labeled expected anomalies. Pure pytest. Target: 100%.
2. **Citation faithfulness** — for recorded agent runs (cassettes), verify every citation id in the brief maps to a real tool result, and cited URLs appeared in search/fetch outputs. Target ≥95%.
3. **Structure compliance** — N recorded runs parse against `MarketBrief` schema. Target ≥98%.

**Cassettes**: live agent runs recorded to JSON (full message history + tool I/O) via a `--record` flag; replayed in CI with a mock Anthropic client. CI never spends money. A `make eval-live` target runs 3 live briefs and regenerates cassettes + a markdown report for the README.

## 8. Observability

Structured JSON log line per run: ticker, steps, tool calls by name, tokens, cost estimate, latency, outcome. `/api/health` exposes remaining daily budget.

## 9. Repo Layout (follows the owner's agent-structure convention — see rules.md §Code Structure)

```
market-briefing-agent/
├── backend/
│   ├── src/
│   │   ├── llm.py                   # provider adapter (anthropic | gemini/openai-compat), normalized ToolCall/ToolResult
│   │   ├── agents/
│   │   │   └── market_brief/
│   │   │       ├── state.py         # agent state schema (run state, history Turns, budgets)
│   │   │       ├── prompts.py       # ALL prompts for this agent in one place
│   │   │       ├── tools.py         # tool schemas + registry (handlers pull from utils.py)
│   │   │       ├── utils.py         # market data adapter, cache, indicators, anomaly detector,
│   │   │       │                    #   search/fetch helpers — reusable, pure where possible
│   │   │       ├── nodes.py         # loop steps: call_llm, execute_tools, check_budget,
│   │   │       │                    #   parse_brief, repair — each independently testable
│   │   │       ├── agent.py         # the orchestrator: wires nodes into the agent loop
│   │   │       └── run.py           # standalone CLI: test THIS agent without API/frontend
│   │   ├── api/                     # FastAPI layer: routes, SSE, guards.py, events.py
│   │   ├── schemas.py               # MarketBrief etc. (mirrors docs/schema.md)
│   │   ├── main.py                  # app entry: ties agents + API together
│   │   └── run.py                   # end-to-end script: full flow without frontend
│   ├── evals/ (fixtures/, cassettes/, run_evals.py)
│   └── tests/
├── frontend/src/ (components/, stores/, lib/sse.ts, pages/)
├── docs/ (these files)
├── docker-compose.yml
├── .env.example
├── Makefile                   # dev, test, eval, eval-live, record
└── README.md
```

Future agents (e.g., Claim Verifier) drop in as `src/agents/<name>/` with the same internal structure, reusing `llm.py` and shared utilities.

## 10. Secrets & Config

Env vars only (full list in 00_START_HERE.md). `.env` gitignored; gitleaks pre-commit; provider spend cap set in Anthropic console before public deploy. Dep: `python-dotenv` loads `backend/.env` for local CLI/dev runs (`make brief`); production reads real env vars.
