"""Agent orchestrator — builds the LangGraph StateGraph (orchestration only).

The graph wires the nodes defined in nodes.py:

    validate_input ─▶ reason ─▶ parse_and_enrich ─▶ verify ─▶ emit_final ─▶ END
              │                        │
              └▶ emit_error            ├▶ repair ─▶ reason
                                       └▶ emit_error

Node bodies (the LLM↔tool reasoning loop, parsing, enrichment, verification)
live in nodes.py; this module only declares the graph and the run_agent
entrypoint. The public contract is unchanged: run_agent(...) streams SSE events
through `emit` and returns a RunResult.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from src.llm import LLMBackend, Turn
from src.schemas import MarketBrief

from .cassette import CassetteRecorder, RecordingBackend
from .events import EVENT_RUN_STARTED, Emitter, noop_emitter
from .nodes import (
    CLIENT_SAFE_KINDS,
    emit_error,
    emit_final,
    parse_and_enrich,
    reason,
    repair,
    route_after_parse,
    route_after_reason,
    route_after_validate,
    validate_input,
    verify,
)
from .prompts import build_user_message
from .state import GraphState, RunState

_log = logging.getLogger("market_brief.agent")

__all__ = ["RunResult", "run_agent", "CLIENT_SAFE_KINDS"]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """The outcome of a single agent run."""

    brief: MarketBrief | None
    # (kind, message) where kind in: validation | budget | timeout | parse | upstream | internal
    error: tuple[str, str] | None
    usage: dict[str, Any]


# ---------------------------------------------------------------------------
# Graph definition (compiled once at import)
# ---------------------------------------------------------------------------


def _build_graph() -> Any:
    """Construct and compile the market-brief StateGraph."""
    g = StateGraph(GraphState)
    g.add_node("validate_input", validate_input)
    g.add_node("reason", reason)
    g.add_node("parse_and_enrich", parse_and_enrich)
    g.add_node("repair", repair)
    g.add_node("verify", verify)
    g.add_node("emit_final", emit_final)
    g.add_node("emit_error", emit_error)

    g.add_edge(START, "validate_input")
    g.add_conditional_edges(
        "validate_input",
        route_after_validate,
        {"reason": "reason", "emit_error": "emit_error"},
    )
    g.add_conditional_edges(
        "reason",
        route_after_reason,
        {"parse_and_enrich": "parse_and_enrich", "emit_error": "emit_error"},
    )
    g.add_conditional_edges(
        "parse_and_enrich",
        route_after_parse,
        {"verify": "verify", "repair": "repair", "emit_error": "emit_error"},
    )
    g.add_edge("repair", "reason")
    g.add_edge("verify", "emit_final")
    g.add_edge("emit_final", END)
    g.add_edge("emit_error", END)
    return g.compile()


_GRAPH = _build_graph()


# ---------------------------------------------------------------------------
# Public entrypoint (signature unchanged across the LangGraph rework)
# ---------------------------------------------------------------------------


def run_agent(
    ticker: str,
    period: str,
    *,
    backend: LLMBackend,
    emit: Emitter | None = None,
    recorder: CassetteRecorder | None = None,
    today: str | None = None,
    verify_llm: bool = True,
) -> RunResult:
    """Run the market-brief agent graph and return a RunResult.

    Parameters
    ----------
    ticker:   Stock ticker symbol (e.g. "AAPL").
    period:   Historical period — one of 1mo/3mo/6mo/1y.
    backend:  Concrete LLMBackend to use for completions.
    emit:     Optional Emitter; defaults to noop_emitter.
    recorder: Optional CassetteRecorder; pass to persist a replay cassette.
    today:    ISO date injected as "today"; defaults to the real date.today().
    verify_llm: Run the LLM semantic layer of the Claim Verifier and stream the
              before→after revision. Set False for offline replay/eval, where the
              deterministic-only verifier runs silently (no extra LLM call).
    """
    _emit: Emitter = emit if emit is not None else noop_emitter
    _today: str = today if today is not None else date.today().isoformat()
    run_id = uuid4().hex

    # Wrap the backend in a RecordingBackend if a cassette recorder was provided.
    _backend: LLMBackend = RecordingBackend(backend, recorder) if recorder is not None else backend

    _log.info(
        "[run_start] ticker=%s period=%s model=%s run_id=%s",
        ticker,
        period,
        _backend.model,
        run_id,
    )

    run = RunState(ticker=ticker, period=period)  # type: ignore[arg-type]
    run.history.append(Turn(role="user", text=build_user_message(ticker, period, _today)))

    _emit(
        EVENT_RUN_STARTED,
        {
            "run_id": run_id,
            "ticker": ticker,
            "name": ticker,
            "period": period,
            "model": _backend.model,
        },
    )

    init: GraphState = {
        "run": run,
        "raw_final_text": None,
        "brief": None,
        "error": None,
        "parse_error": None,
        "verification": None,
        "usage": None,
    }
    config: RunnableConfig = {
        "configurable": {
            "emit": _emit,
            "backend": _backend,
            "recorder": recorder,
            "verify_llm": verify_llm,
        },
        "recursion_limit": 50,
    }
    final: GraphState = _GRAPH.invoke(init, config=config)

    usage: dict[str, Any] = final.get("usage") or {
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "est_cost_usd": 0.0,
        "tool_calls": run.tool_calls_made,
        "iterations": run.iterations,
        "latency_ms": int(run.elapsed_s() * 1000),
    }
    return RunResult(brief=final.get("brief"), error=final.get("error"), usage=usage)
