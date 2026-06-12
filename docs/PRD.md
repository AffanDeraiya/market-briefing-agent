# PRD — Market Briefing Agent

## 1. Problem Statement

Getting a quick, trustworthy read on a stock means manually juggling price charts, news sites, and screeners — and AI summaries of markets are notoriously uncited and hallucination-prone. Existing "AI stock tools" either dump unverified text or hide how they reached their conclusions.

Market Briefing Agent produces a structured, **fully cited** brief for any ticker in ~60 seconds, and shows its work: a live reasoning timeline of every step and tool call the agent takes. The agent doesn't just summarize — it **detects anomalies in the data and investigates them**, scoping news searches to the exact dates where something unusual happened.

## 2. Goals

1. Showcase a hand-rolled Claude SDK agentic loop with conditional multi-step reasoning (portfolio goal — this is the interview centerpiece).
2. Produce briefs a reasonable person finds genuinely useful and verifiably sourced.
3. Zero-friction public demo: enter ticker → watch agent think → get brief. No signup.
4. Be safe to run unattended on a personal API key (caps everywhere).

## 3. Non-Goals (v1)

- Investment advice or recommendations (explicit disclaimer; bull/bear cases are presented as sourced arguments, not advice)
- Buy/sell signals, price predictions, backtesting
- Portfolio tracking, watchlists, alerts, user accounts
- Multi-ticker comparison (v2 candidate)
- BYO API key (v2)
- Intraday/realtime data (daily granularity is fine)

## 4. Target Users

1. **Recruiters/hiring managers** (primary): run one ticker, watch the timeline, skim the brief.
2. **Engineers** evaluating the repo: read the agent loop, tools, evals.
3. **Actual users**: anyone wanting a quick sourced read on a stock — relatable to any audience.

## 5. Core Features

### F1 — Brief generation (P0)
User enters a ticker (US + major international via yfinance suffixes, e.g., `RELIANCE.NS`). Agent runs and streams a structured brief: snapshot, technical read, anomalies with explanations, news highlights, bull case, bear case, risks — every bullet citation-tagged.

### F2 — Anomaly-driven investigation (P0 — the differentiator)
Deterministic detectors flag unusual days (|daily return| > 2.5σ, volume > 3× 30-day average, gaps). For each significant anomaly, the agent runs date-scoped news/web searches to explain *why it happened*, and links the explanation to sources. If it can't find a cause, the brief says so honestly.

### F3 — Live reasoning timeline (P0)
Every agent step streams to the UI in real time: thinking snippets, each tool call with inputs, each result summary, running token/cost meter. This is the "visualize the agent" requirement and the demo wow.

### F4 — Price chart (P1)
Interactive Recharts price+volume chart of the analyzed period with anomaly markers; clicking a marker scrolls to that anomaly's explanation.

### F5 — Citations & export (P1)
Citation chips on every brief bullet link to sources. Export brief as Markdown. Recent briefs kept in sessionStorage.

### F6 — Guards (P0)
Per-IP rate limit, global daily cap, tool-call/iteration/token caps, ticker validation, timeouts on every external call. Friendly rate-limit and "server waking" states.

### F7 — Eval harness (P1)
Three automated gates (detailed in techspec §7): anomaly-detector correctness on frozen fixtures, citation faithfulness, output-structure compliance. Results table in README; smoke subset in CI.

## 6. Success Criteria

| Metric | Target |
|---|---|
| Anomaly detector precision/recall on fixture set | 100% (it's deterministic — any failure is a bug) |
| Citation faithfulness (cited source exists in tool results & supports text) | ≥ 95% |
| Structure compliance (brief parses against schema) | ≥ 98% of runs |
| End-to-end brief latency (P50) | ≤ 60s |
| Cost per brief (Haiku) | ≤ $0.03 |
| New-visitor time to first streaming step | ≤ 10s |
| Backend core test coverage (tools, detectors, loop) | ≥ 80% |
| Lighthouse performance/accessibility | ≥ 90 |

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Hallucinated market claims | Citation requirement enforced in prompt + faithfulness eval; uncited claims rejected at parse |
| yfinance breakage/rate limits | Thin adapter layer; 24h on-disk cache per ticker+period; graceful errors |
| Search returns junk/paywalled pages | fetch_page extracts with trafilatura, falls back to snippet; agent told to prefer multiple sources |
| Cost blowout | Haiku + MAX_TOOL_CALLS=15 + MAX_ITERATIONS=20 + token caps + global daily brief cap + provider spend limit |
| "Tutorial stock bot" perception | F2 depth, citations, evals, reasoning UI — differentiators are P0, not afterthoughts |
| Regulatory/advice concerns | Persistent disclaimer; no recommendations, only sourced analysis |
| Free-tier server cold starts | "Waking up" UI state + health ping |

## 8. Release Definition (v1 done)

Deployed public URL + public repo + README (GIF, architecture diagram, eval table, quickstart ≤ 5 commands, Limitations section) + CI green + all §6 gates met. Then: resume Projects section updated with live link + one metric.
