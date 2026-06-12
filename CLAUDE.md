# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project State

**Market Briefing Agent** — a web app where a user enters a stock ticker and a single hand-rolled LLM agent produces a cited, structured market brief, streaming its reasoning live to a React timeline. The differentiator: deterministic anomaly detection (price spikes, volume surges, gaps) followed by autonomous, date-scoped investigation of each anomaly.

The project is **fully planned but not yet built**. `docs/` is the complete spec and the **source of truth** — read `docs/00_START_HERE.md` first, then follow its reading order. Build proceeds phase-by-phase per `docs/implementation_plan.md` (currently: Phase 0, scaffold). Do not start later phases early. If a doc seems wrong, flag it and propose a doc change rather than silently diverging; behavior changes update `schema.md`/`techspec.md` in the same commit.

**Update `docs/tracker.md` at the end of every session** (checkboxes + session log + decisions log). This is mandatory per `docs/rules.md`.

## Commands (planned — Makefile targets per techspec)

- `make dev` / `make test` / `make lint` — created in Phase 0
- `make brief TICKER=AAPL` — run the agent end-to-end from CLI (Phase 2)
- `make eval` — offline eval gates via cassette replay, runs in CI; `make eval-live` — 3 live runs, regenerates cassettes + README report (Phase 6)
- Backend: pytest + httpx, ruff, mypy. Frontend: vitest, eslint, prettier. CI (GitHub Actions) runs lint → unit tests → eval smoke; **CI never makes live API calls** — agent tests replay recorded cassettes with a mock client.
- Each agent is independently runnable via its `run.py` (e.g., `python -m src.agents.market_brief.run`) — no API server or frontend needed.

## Architecture

```
React SPA ──POST /api/brief──▶ FastAPI (slowapi per-IP + global daily cap)
                │ SSE stream of agent events
                ▼
   Agent loop (hand-rolled, NO framework — interview explainability is the point)
       │ llm.complete(...)                    │ tool registry
       ▼                                      ▼
   src/llm.py provider adapter            Tool layer (7 tools, Pydantic I/O)
     ├─ anthropic (native SDK)              ├─ market_data (yfinance + 24h disk cache)
     └─ gemini/groq (OpenAI-compat)         ├─ indicators / detect_anomalies (pure pandas)
                                            ├─ news/search (ddgs | tavily)
                                            └─ fetch_page (trafilatura)
```

- **`docs/schema.md` is the contract**: agent loop state machine, all 7 tool I/O shapes, the SSE event protocol, and the `MarketBrief` output schema. Code must mirror it; change the doc first.
- `src/llm.py` normalizes Anthropic `tool_use`/`tool_result` blocks and OpenAI-style `tool_calls` into internal `ToolCall`/`ToolResult` types; the loop never touches provider wire formats. Dev/demo runs on Gemini free tier (`gemini-2.5-flash`); showcase/cassettes on `claude-haiku-4-5`. OpenAI-format tool `arguments` arrive as a JSON string — parse defensively.
- Stateless backend, no database; disk cache (`.cache/`) for yfinance only. One brief = one agent run = one SSE stream.
- Tool outputs are compact by design (summaries, not raw dumps — e.g., weekly aggregates + notable days, never 250 OHLCV rows); raw data goes to the UI via the `chart_data` SSE event, not through the LLM.
- Stop conditions: final JSON brief, or budget caps reached → inject "finalize now", or error. Parse failure gets exactly one repair round-trip, then fails honestly.
- Frontend: React 18 + Vite + TS + Tailwind + Zustand + Recharts, consuming the SSE stream (`frontend/src/lib/sse.ts`).

## Mandatory Code Structure (owner's convention, rules.md §A–D)

Every agent lives in `src/agents/<name>/` with exactly: `state.py`, `prompts.py`, `utils.py`, `nodes.py`, `tools.py`, `agent.py`, `run.py`. Prompts ONLY in `prompts.py` (never inline); nodes pull logic from `utils.py`; `agent.py` is orchestration only. When a file exceeds ~300 lines, promote it to a package with domain-named modules — start flat, split on growth. A second agent (Claim Verifier, post-v1) must be addable without touching the first.

## Non-Negotiable Rules (full list: docs/rules.md)

- **The LLM never computes numbers.** Prices, returns, indicators, anomalies come from deterministic, unit-tested pure Python. The LLM interprets, investigates, and writes.
- **Every claim is cited.** Brief bullets carry citation ids resolving to real tool results/URLs; the parser rejects uncited bullets — never weaken it. "No clear public cause found" with low confidence beats an invented explanation.
- **Every external call is bounded**: 10s tool timeouts, 120s run timeout, `MAX_TOOL_CALLS=15`, `MAX_ITERATIONS=20`, max_tokens on every LLM call. No "temporary" unbounded debug code.
- **No secrets in the repo**: env vars only (full list in `docs/00_START_HERE.md`), gitleaks pre-commit.
- **Typed everywhere**: Pydantic at all boundaries, mypy passes, TS strict with no bare `any`.
- **Prompts are code**: any prompt change re-runs `make eval`, and the commit message includes before/after gate numbers.
- New dependencies require a one-sentence justification in `techspec.md`. Conventional commits; tests ship in the same PR as the feature (backend core coverage ≥80%).
- The disclaimer (not financial advice) is immutable: UI footer, brief output, README.
- **Descope, don't half-build** — cut features in the order listed in `implementation_plan.md`; never cut anomaly investigation, citations, evals, guards, or the timeline.
