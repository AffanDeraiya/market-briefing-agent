# LangGraph Backend Rework — Plan & Progress

**Branch:** `feat/backend-langgraph-rework` (off `working`)
**Status:** Phase 1 in progress (see checklist at bottom).
**Goal:** Convert the hand-rolled outer loop into a **LangGraph `StateGraph`** with explicit, interconnected nodes, and add a **Claim Verifier** node. The multi-step reasoning + tools are preserved verbatim — only the *orchestration* becomes a graph.

This doc is the source of truth for the rework so any session can resume from here.

## Confirmed decisions (locked with the user)
1. **Real LangGraph** — add the `langgraph` dependency; build a `StateGraph` in `agent.py`. (Knowingly reverses the previous "no framework" differentiator; `CLAUDE.md` updated to match.)
2. **Hybrid verifier** — deterministic checks always run (incl. CI/replay); an LLM semantic claim-support pass runs **live only** and is skipped in eval-replay (via a config flag) so the 6 cassettes need no re-recording and the gate stays 100%/100%. LLM-layer logic is unit-tested with a `FakeBackend`.
3. **Verifier may mutate** the brief — downgrade confidence, drop a claim with no real support, neutralize the signal if weak — same philosophy as the existing finalize-time grounding guard. Honest output over a pretty one.

## Non-negotiables preserved
- **SSE event protocol unchanged** (`run_started/step/tool_call/tool_result/chart_data/anomaly_focus/brief/usage/error`) → **frontend untouched**. Nodes call the existing `events.py` emitter, passed via LangGraph `config["configurable"]["emit"]`.
- **Public entrypoint unchanged:** `run_agent(...)` still returns `RunResult(brief, error, usage)`, so `api/sse.py`, `run.py`, and `evals/replay.py` barely change.
- **Budgets** (`MAX_TOOL_CALLS=15`, `MAX_ITERATIONS=20`, `RUN_TIMEOUT_S=120`) stay inside the `reason` node. Only graph cycle is `repair→reason`, bounded to 1.
- **LLM never computes numbers · every claim cited · immutable disclaimer** — all unchanged.
- Reasoning loop, `tools.py` registry, tool-calling, cassette recording — **identical**, just invoked as a node body.

## Target graph
```
START → validate_input → reason → parse_and_enrich → verify → emit_final → END
                │                        │
                └→ emit_error            ├→ repair (≤1) → reason
                                         └→ emit_error
reason → emit_error            (provider 429 / internal / timeout / budget)
```

### State (`state.py`)
A thin `GraphState` TypedDict carrying the existing `RunState` plus staged artifacts:
```python
class GraphState(TypedDict):
    run: RunState              # existing workhorse: history, budgets, tool outputs, seen_urls
    raw_final_text: str | None # the LLM's final composed text (set by reason)
    brief: MarketBrief | None  # parsed + enriched (set by parse_and_enrich, mutated by verify)
    error: tuple[str, str] | None   # (kind, message)
    verification: dict | None  # Phase 2 verifier summary
```
- `RunState` is mutated in place across nodes; nodes return partial dict updates (default overwrite reducers — no custom reducers needed for Phase 1).
- The **emitter** and **recorder** travel in `config["configurable"]`, not in serializable state (we don't use checkpointing).

### Nodes (`nodes.py`) — bodies are mostly existing code
- **`validate_input`** — `normalize_ticker` + period check. Minimal/normalizing (the API already validates) to stay behavior-identical. Bad input → `error=("validation", …)` → `emit_error`.
- **`reason`** — the current `while True` loop (agent.py:144-209): hard stops → error; `call_llm`; emit `step`; on `is_final` → **stop and return `raw_final_text`** (parse happens in the next node); else `run_tool_calls`; on budget/timeout → `inject_finalize` (once) or `error=("budget",…)`. Provider `RateLimitError` → `error=("budget", friendly msg)`; other exc → `error=("internal",…)`.
- **`parse_and_enrich`** — `parse_final(raw_final_text, run.seen_urls)` + `attach_market_data(run, brief)`. Success → `verify`. `ValidationError/ValueError` → `repair` if `not run.repair_attempted` else `error=("parse",…)`.
- **`repair`** — `inject_repair(run, error_text)` → back to `reason` (loop continues with repair turn; identical to today's inline repair).
- **`verify`** — Phase 1: **pass-through no-op** (keeps final graph shape, behavior-identical). Phase 2: hybrid Claim Verifier with mutate authority (see below).
- **`emit_final`** — compute usage dict, `emit(brief)` + `emit(usage)`, recorder `set_final`. END.
- **`emit_error`** — client-safe message mapping (existing `CLIENT_SAFE_KINDS`), `emit(error)` + `emit(usage)`, recorder `set_final(None,…)`. END.

`run_started` is emitted by the `run_agent` wrapper before `graph.invoke` (exactly as today, once at start).

### Graph build (`agent.py`)
`StateGraph(GraphState)` with `add_node`/`add_edge`/`add_conditional_edges`; `compile()` once at module load. `run_agent(...)` builds the initial `GraphState` + `RunState`, emits `run_started`, invokes the compiled graph with `config={"configurable": {"emit": …, "recorder": …}, "recursion_limit": 25}`, then reads `brief/error` out of the final state and returns `RunResult` with the usage dict.

## Verifier UX decision (locked): L2 — live before→after revision
- **Backend events now, frontend after** (frontend animation is a follow-on sub-phase).
- New SSE events (additive; current frontend ignores unknown events safely): `verify_started {claims_total}`, `claim_verdict {target, label, verdict: supported|partial|unsupported, action: kept|confidence_downgraded|dropped|neutralized, note}`, `verify_done {checked, supported, adjusted, dropped}`.
- **Double `brief` emission on LIVE runs only:** `reason`/`parse_and_enrich` produce the composed brief → on the live path the `verify` node emits the **composed** brief, then `verify_started` + per-claim `claim_verdict`s while it works, mutates, then `emit_final` emits the **revised** brief + usage. The L2 frontend diffs the two and animates the change.
- **Eval/CI safety:** the deterministic layer always runs but is tuned to **no-op on already-clean briefs** (the 6 cassettes are already grounded/structured → 0 mutations → eval unchanged). The LLM semantic layer + the composed-brief emission are gated by `config["configurable"]["verify_llm"]` (default True; replay sets **False**), so deterministic-only replay = single brief, identical event/score profile to Phase 1.
- **Storage/contract:** add an optional `verification` summary field to `MarketBrief` (like `signal`) so it's stored in recents, exported, and replay-safe; mutations to confidence/claims/signal use existing fields.

## Phase 2 — the Claim Verifier (`verify` node)
- **Deterministic layer (always, incl. replay):** re-confirm citations grounded in `seen_urls`; signal-vs-bull/bear consistency; confidence sanity (high confidence on thin support). Mutations mirror the grounding guard.
- **LLM semantic layer (live only):** second LLM pass scoring each cited claim against retrieved evidence (`supported/partial/unsupported`). Skipped in replay via `config["configurable"]["verify_llm"]=False`. Prompt hand-authored by Opus; logic unit-tested with `FakeBackend`.
- **Mutations:** downgrade confidence, drop unsupported claims (re-using grounding repair), neutralize the signal if support is weak. Effects are visible in the existing UI without frontend changes; a per-claim summary is emitted additively for a later UI pass.

## Deps & docs
- Add `langgraph` (+ transitively `langchain-core`) to `backend/pyproject.toml`; one-line justification in `techspec.md`. Verify it installs under `uv` / py3.12 before wiring.
- Update `CLAUDE.md` (architecture line), `schema.md §1` (loop → graph), `techspec.md`.

## Rollout (each phase gated; merge to `working` only after all green)
- **Phase 1 — behavior-identical scaffolding.** Graph wraps the current loop; `verify` is a no-op. **Gate: backend 240 tests + eval 100%/100% must hold** (proves nothing observable changed). Optional live smoke.
- **Phase 2 — verifier node** + deterministic checks + LLM layer (fake-tested) + mutations + tests. Gate: tests + eval 100%.
- **Phase 3 — docs + e2e + one live smoke**, then merge to `working`.

Opus owns the graph wiring, state schema, entrypoint, and verifier prompt; Sonnet 4.6 subagents do mechanical extraction + the deterministic-verifier module + tests. Verify each phase before the next.

## How to resume
1. `git checkout feat/backend-langgraph-rework`
2. Read this doc + the checklist below.
3. Continue at the first unchecked item; re-run the phase gate before advancing.

## Progress checklist
### Phase 1 — scaffolding (behavior-identical)  ✅ COMPLETE
- [x] `langgraph>=1.2.5` (+ langchain-core 1.4.7) added to deps; installs under `uv`/py3.12
- [x] `state.py`: `GraphState` TypedDict added (RunState unchanged; MarketBrief imported at runtime — LangGraph introspects the hints)
- [x] `nodes.py`: `validate_input`, `reason`, `parse_and_enrich`, `repair`, `verify`(no-op), `emit_final`, `emit_error` + routers; CLIENT_SAFE_KINDS moved here
- [x] `agent.py`: `StateGraph` built + compiled at import; `run_agent` wrapper returns identical `RunResult`
- [x] `api/sse.py`, `run.py`, `evals/replay.py` unchanged (entrypoint preserved)
- [x] **Gate held: 240 backend tests pass + eval 100%/100% (6/6)** + ruff/format/mypy strict clean
- [x] techspec.md "Agent" row updated to LangGraph (dep justification); CLAUDE.md updated
- [ ] (optional) one live smoke on branch — deferred; offline gate is green

### Phase 2 — Claim Verifier  ✅ COMPLETE (backend)
- [x] result models `ClaimVerdict`/`Verification` + optional `MarketBrief.verification` field
- [x] `utils/verify.py`: `count_claims` + `run_verification` (deterministic + LLM layers, mutate authority) + 24 unit tests (FakeBackend for the LLM layer; malformed-JSON fallback; token counting)
- [x] LLM semantic layer (live-only, replay-skipped via `verify_llm`) + Opus-authored `VERIFIER_SYSTEM_PROMPT`/`build_verifier_message`
- [x] `verify` node emits `verify_started`/`claim_verdict`/`verify_done` + the composed→revised double `brief` (L2); `events.py` constants; `run_agent(verify_llm=True)`; `replay.py` passes `verify_llm=False`
- [x] `schema.md` §3 (events) + §4 (Verification field + verifier behavior) updated
- [x] **Gate held: 264 tests pass + eval 100%/100% (6/6)** + ruff/format/mypy strict clean (deterministic layer no-ops on clean cassettes)

### Phase 2.5 — Frontend showcase (L2 live before→after) — NEXT
- [ ] types: `Signal` already done; add `Verification`/`ClaimVerdict`; new SSE events in `sse.ts`/types + `runStore` reducers (handle 2nd `brief` as a revision; collect verdicts)
- [ ] agent-log: a `verify` step (like compose) with a hover summary
- [ ] brief diff animation: confidence chips transition, dropped claims fade/strike, signal hero updates; per-claim `✓ verified`/`⚠ adjusted` badges; a "Verification" summary panel
- [ ] persist `verification` in recents; add to `mdExport`
- [ ] frontend gate: lint/prettier/tsc/tests/build

### Phase 3 — docs + ship
- [ ] `CLAUDE.md`, `schema.md §1`, `techspec.md` updated
- [ ] e2e + one live smoke on deploy
- [ ] merge `feat/backend-langgraph-rework` → `working`
