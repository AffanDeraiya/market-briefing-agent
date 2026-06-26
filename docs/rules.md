# Rules — Market Briefing Agent

Non-negotiable for the project's lifetime. Applies to human and AI-assisted contributions equally (including Claude Code).

## Security & Cost
1. **No secrets in the repo, ever.** Env vars only; `.env` gitignored; gitleaks pre-commit stays on. Leaked key → rotate immediately, don't just rewrite history.
2. **Every external call is bounded**: LLM calls have max_tokens + the run has iteration/tool-call caps; tools have 10s timeouts; the whole run has a 120s timeout. No "temporary" unbounded debug code.
3. **Caps before public deploy**: per-IP + global daily limits must exist before the URL is shared anywhere. (Dev/demo runs on free-tier provider keys, so there is no paid-spend exposure.)
4. **The LLM never computes numbers.** Prices, returns, indicators, anomalies come from deterministic tested Python. The LLM interprets, investigates, and writes.

## Truthfulness (this project's soul)
5. **Every claim is cited.** Brief bullets carry citation ids that resolve to real tool results/URLs. The parser rejects uncited bullets; don't weaken the parser.
6. **Honest uncertainty is a feature.** "No clear public cause found" with low confidence beats an invented explanation. Never prompt-engineer this away.
7. **Disclaimer is immutable**: rendered in UI footer, brief output, and README. This is an educational project, not financial advice.

## Code Structure & Style (owner's convention — mandatory)
A. **Agent directory structure.** Every agent lives in `src/agents/<agent_name>/` with exactly this internal layout:
   - `state.py` — the agent's state schema (TypedDict/Pydantic) and any enums/constants of the contract. First file a reader opens; nodes read/write ONLY fields defined here.
   - `prompts.py` — ALL prompts for the agent in one module (constants/templates). Never inline prompts in logic files.
   - `utils.py` — all utility/helper functions together, pure where possible, written for reuse across agents.
   - `nodes.py` — every loop step / processing node in one file; nodes pull logic from `utils.py`, never duplicate it.
   - `tools.py` — all tool schemas + the registry; handlers delegate to `utils.py`.
   - `agent.py` — the orchestrator that wires nodes into the agent loop. Orchestration only — no business logic. (For LangGraph agents, expose the compiled `graph` at module level for `langgraph dev` compatibility.)
   - `run.py` — standalone CLI script to run/test THIS agent in isolation (no API server, no frontend).
   Files may be added per need (e.g., `events.py`), but this skeleton is always present and named exactly this way.
   **Growth rule:** when any of these files exceeds ~300 lines, promote it to a package with domain-named modules (`utils/` → `utils/indicators.py`, `nodes/` → one file per phase). Start flat; split on growth — never pre-build deep hierarchies.
B. **Top level:** `src/llm.py` (shared provider adapter), `src/main.py` (ties agents + API together), `src/run.py` (end-to-end test script for the whole flow).
C. **Modularity is the default.** Anything plausibly reusable by a future agent goes in `utils.py`/shared modules, not buried in a node. A second agent (Claim Verifier is planned) must be addable without touching the first.
D. **Every agent must be testable alone** via its `run.py` — this is non-negotiable for debugging.

## Code Quality
8. **Docs are source of truth.** Behavior change → update schema.md/techspec.md in the same commit. Code/doc disagreement = bug.
9. **Typed everywhere.** Pydantic at all boundaries; mypy passes; TS strict, no bare `any`.
10. **Tests ship with the feature.** Detector/tools/guards/parser changes include tests in the same PR. Backend core coverage ≥80%.
11. **Prompts are code**: they live only in the agent's `prompts.py`; every prompt change re-runs `make eval` and the commit message includes the before/after gate numbers.
12. **No new dependencies casually** — one sentence in techspec.md saying why.

## Process
13. **Conventional commits**; small logical commits; main always deployable; CI green to merge.
14. **Update tracker.md every session** — checkboxes, session log line, decisions log. Five minutes, never skipped.
15. **Descope, don't half-build.** Cut in the order listed in implementation_plan.md; what ships stays polished.
16. **For Claude Code specifically:** follow the phase order; don't start a later phase early; if a doc seems wrong or ambiguous, flag it and propose the doc change rather than silently diverging; record any deviation in the tracker's decisions log.

## Honesty
17. **Every public claim must be demo-able.** README metrics come from committed eval runner output, not estimates.
18. **Limitations are documented publicly** (data delays, model, caps, single-ticker scope). Stated limits read as seniority, not weakness.
