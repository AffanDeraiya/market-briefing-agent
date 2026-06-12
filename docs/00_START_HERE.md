# START HERE — Market Briefing Agent (Knowledge Transfer for Claude Code)

You (Claude Code) are picking up a fully planned project. This file is your onboarding. Read it first, then the other docs in the order below. The docs are the source of truth — follow them, and if you must deviate, say so explicitly and update the doc in the same commit.

## What this project is

**Market Briefing Agent** — a web app where a user enters a stock ticker and a single Claude-powered agent produces a cited, structured market brief. The agent's differentiator is the **anomaly-driven investigation loop**: it computes indicators deterministically, *detects* unusual events (price spikes, volume surges), and then *autonomously decides* to investigate each one with date-scoped news/web searches before composing the brief. A React UI visualizes the agent's reasoning live: every thought, tool call, and result streams to a timeline while the brief assembles alongside it.

## Why it exists (context you need)

This is a portfolio project for Affan Deraiya, a GenAI Developer (~2 yrs exp at Fractal) targeting AI Engineer roles. It must demonstrate, in a way that survives technical interviews:
1. A hand-rolled agentic loop on the **Anthropic Claude SDK** (Messages API tool use — deliberately NOT a framework, so he can explain every line)
2. Multi-step reasoning with conditional tool use (the anomaly→investigate behavior)
3. Production thinking: citations for every claim, eval harness, cost guards, clean deploy

Quality bar: a recruiter clicks the live demo and is impressed in 30 seconds; an engineer reads the repo and respects it. A shallow "fetch news and summarize" stock bot is explicitly what we are NOT building.

## Critical constraints (do not violate)

- **No secrets in the repo, ever.** Env vars only. `.env.example` with dummies. gitleaks pre-commit.
- **Cost-capped by design**: Claude Haiku by default, hard caps on tool calls/iterations/tokens, per-IP and global rate limits. The app must be safe to leave deployed unattended on a personal API key.
- **Not financial advice**: disclaimer in UI footer, README, and brief output.
- **Every narrative claim in a brief carries a citation** to a tool result or source URL.
- **Deterministic logic stays out of the LLM**: indicators and anomaly detection are pure Python with unit tests; the LLM interprets and investigates, it does not compute.

## Reading order

1. `PRD.md` — what we're building and why; success criteria
2. `techspec.md` — stack, architecture, guards, repo layout
3. `schema.md` — agent loop, tool contracts, event protocol, brief output schema (the most important file; code must match it)
4. `webapp_flow.md` — every screen, state, and interaction
5. `design.md` — visual system, tokens, components
6. `implementation_plan.md` — phased build order; start at Phase 0
7. `tracker.md` — update it every session (checkboxes + session log)
8. `rules.md` — non-negotiable working rules

## Key decisions already made (don't relitigate without flagging)

| Decision | Choice | Why |
|---|---|---|
| Agent framework | None — hand-rolled tool-use loop over a provider adapter (`src/llm.py`) | Interview explainability; showcases understanding of the agentic loop itself |
| LLM providers | `llm.py` adapter with two backends: `anthropic` (native Anthropic SDK) and `gemini` (OpenAI-compatible; covers Groq too). Normalized internal ToolCall/ToolResult types | Anthropic has no free tier; Gemini free tier (~1,500 req/day) funds all dev + the public demo at $0 |
| Model strategy | Dev/demo: `gemini-2.5-flash` (free). Cassette recording + showcase runs: `claude-haiku-4-5` once budget exists (~$0.50 total) | Zero spend now; Claude path fully implemented and one env var away |
| Code structure | Owner's agent convention: `src/agents/<name>/{state.py, prompts.py, utils.py, nodes.py, tools.py, agent.py, run.py}` — see rules.md §Code Structure | Mandatory, reused for future agents |
| Market data | yfinance (no key needed) | Free, reliable enough, no signup friction |
| News/web search | `ddgs` (DuckDuckGo) default; Tavily optional via env | Zero-key default; pluggable |
| Backend | FastAPI + SSE streaming | Async, standard, one-way stream fits |
| Frontend | React 18 + Vite + TS + Tailwind + Recharts + Zustand | Standard hiring stack |
| Evals | Recorded fixtures + cassettes; no live API in CI | Deterministic, free CI |
| Hosting | Vercel (FE) + Render free (BE) | $0 |
| Out of scope v1 | BYO key, portfolio tracking, multi-ticker compare, auth | Scope control |

## Environment variables (complete list)

```
LLM_PROVIDER=gemini       # gemini | anthropic | groq
LLM_MODEL=gemini-2.5-flash
GEMINI_API_KEY=           # free at aistudio.google.com (default dev/demo provider)
ANTHROPIC_API_KEY=        # optional until showcase runs
GROQ_API_KEY=             # optional fallback
SEARCH_PROVIDER=ddgs      # ddgs | tavily
TAVILY_API_KEY=           # only if SEARCH_PROVIDER=tavily
MAX_TOOL_CALLS=15
MAX_ITERATIONS=20
MAX_OUTPUT_TOKENS=4096
RATE_LIMIT_BRIEFS_PER_HOUR=5
GLOBAL_DAILY_BRIEFS=100
CORS_ORIGINS=http://localhost:5173
```

## How to start

Phase 0 in `implementation_plan.md`. First commit = scaffold + CI green. Work phase by phase; each phase ends runnable. Update `tracker.md` before stopping any session.

## Definition of done (v1)

Public URL + public GitHub repo + README with demo GIF, architecture diagram, eval results table, ≤5-command quickstart, and Limitations section + CI green + eval gates passing (see PRD §6).
