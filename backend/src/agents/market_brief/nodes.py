"""LangGraph node definitions — agent.py wires these into a StateGraph.

Each node takes the GraphState + RunnableConfig and returns a PARTIAL state
update. The emitter / backend / recorder travel in config["configurable"] (not in
serializable state). RunState is mutated in place across nodes.

The pure mechanics the nodes drive live in the utils package:
  utils.reasoning — call_llm, run_tool_calls, inject_finalize/repair
  utils.parsing   — parse_final, attach_market_data
  utils.verify    — count_claims, run_verification
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from src.llm import LLMBackend

from .events import (
    EVENT_BRIEF,
    EVENT_CLAIM_VERDICT,
    EVENT_ERROR,
    EVENT_STEP,
    EVENT_USAGE,
    EVENT_VERIFY_DONE,
    EVENT_VERIFY_STARTED,
    Emitter,
    estimate_cost_usd,
    noop_emitter,
)
from .prompts import SYSTEM_PROMPT
from .state import (
    MAX_ITERATIONS,
    MAX_OUTPUT_TOKENS,
    PERIODS,
    RUN_TIMEOUT_S,
    GraphState,
    RunState,
)
from .tools import tool_specs
from .utils.parsing import attach_market_data, parse_final
from .utils.reasoning import call_llm, inject_finalize, inject_repair, run_tool_calls
from .utils.verify import count_claims, run_verification

try:
    from openai import RateLimitError as _OpenAIRateLimitError
except ImportError:  # pragma: no cover
    _OpenAIRateLimitError = None  # type: ignore[assignment,misc]

try:
    from anthropic import RateLimitError as _AnthropicRateLimitError
except ImportError:  # pragma: no cover
    _AnthropicRateLimitError = None  # type: ignore[assignment,misc]

_log = logging.getLogger("market_brief.nodes")

if TYPE_CHECKING:
    from .cassette import CassetteRecorder

# Error kinds whose detail is safe to surface verbatim to clients; others get a
# generic message in the emitted SSE error event (full detail kept server-side).
CLIENT_SAFE_KINDS: frozenset[str] = frozenset(
    {"validation", "budget", "timeout", "parse", "upstream"}
)

__all__ = [
    "CLIENT_SAFE_KINDS",
    "validate_input",
    "reason",
    "parse_and_enrich",
    "repair",
    "verify",
    "emit_final",
    "emit_error",
    "route_after_validate",
    "route_after_reason",
    "route_after_parse",
]


_RATE_LIMIT_MSG = "The demo has hit its LLM provider rate limit. Please try again in a few minutes."


# ---------------------------------------------------------------------------
# Node-local glue
# ---------------------------------------------------------------------------


def _conf(config: RunnableConfig) -> dict[str, Any]:
    """Extract the configurable dict (emit / backend / recorder) from config."""
    return dict(config.get("configurable") or {})


def _build_usage(run: RunState, model: str) -> dict[str, Any]:
    """Compute the usage summary dict emitted on every terminal path."""
    return {
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "est_cost_usd": estimate_cost_usd(model, run.input_tokens, run.output_tokens),
        "tool_calls": run.tool_calls_made,
        "iterations": run.iterations,
        "latency_ms": int(run.elapsed_s() * 1000),
    }


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def validate_input(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Cheap input guard. The API already validates; this keeps the graph honest."""
    run = state["run"]
    if not run.ticker or not run.ticker.strip():
        return {"error": ("validation", "ticker must be a non-empty string")}
    if run.period not in PERIODS:
        return {"error": ("validation", f"invalid period: {run.period!r}")}
    return {}


def reason(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """The multi-step reasoning loop: LLM <-> tools until a final composition.

    This is the original while-loop body verbatim — same LLM calls, tool calls,
    finalize injection and budget caps — now invoked as one node. On a final
    response it returns ``raw_final_text`` and hands off to ``parse_and_enrich``;
    parse failures route back here through the ``repair`` node.
    """
    run = state["run"]
    cfg = _conf(config)
    backend: LLMBackend = cfg["backend"]
    emit: Emitter = cfg.get("emit") or noop_emitter
    recorder: CassetteRecorder | None = cfg.get("recorder")

    try:
        while True:
            if run.timed_out():
                return {"error": ("timeout", f"run exceeded {RUN_TIMEOUT_S}s")}
            if run.iteration_budget_exceeded():
                return {"error": ("budget", f"max iterations ({MAX_ITERATIONS}) reached")}

            response = call_llm(
                run,
                backend,
                system=SYSTEM_PROMPT,
                tools=tool_specs(),
                max_tokens=MAX_OUTPUT_TOKENS,
            )
            if response.text.strip():
                emit(EVENT_STEP, {"iteration": run.iterations, "thinking": response.text[:300]})

            if response.is_final:
                return {"raw_final_text": response.text}

            run_tool_calls(run, response, emit, recorder=recorder)
            if run.tool_budget_exceeded() or run.timed_out():
                if not run.finalize_injected:
                    inject_finalize(run)
                    continue
                return {"error": ("budget", "tool budget exhausted; model did not finalize")}
    except Exception as exc:  # noqa: BLE001 — last-resort guard; emit nodes always run after
        _is_rate_limit = (
            _OpenAIRateLimitError is not None and isinstance(exc, _OpenAIRateLimitError)
        ) or (_AnthropicRateLimitError is not None and isinstance(exc, _AnthropicRateLimitError))
        if _is_rate_limit:
            _log.warning("[rate_limit] provider returned 429: %s", str(exc)[:300])
            return {"error": ("budget", _RATE_LIMIT_MSG)}
        _log.exception("[unhandled] %s: %s", type(exc).__name__, exc)
        return {"error": ("internal", f"{type(exc).__name__}: {exc}")}


def parse_and_enrich(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Parse the final text (with grounding) and attach deterministic market data."""
    run = state["run"]
    raw = state.get("raw_final_text") or ""
    try:
        brief = parse_final(raw, run.seen_urls)
        attach_market_data(run, brief)
        _log.info("[run_ok] brief parsed successfully")
        return {"brief": brief}
    except (ValidationError, ValueError) as exc:
        _log.warning("[parse_fail] %s", str(exc)[:400])
        if not run.repair_attempted:
            return {"parse_error": str(exc)}
        return {"error": ("parse", f"brief failed validation after repair: {exc}")}


def repair(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Inject one repair prompt and route back to ``reason`` (bounded to once)."""
    run = state["run"]
    inject_repair(run, state.get("parse_error") or "validation error")
    return {"parse_error": None, "raw_final_text": None}


def verify(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Claim Verifier: audit the brief's cited claims against retrieved evidence,
    mutate it (downgrade / drop / neutralize), and stream the verdicts.

    Live path (verify_llm=True): emit the COMPOSED brief first, then verify_started
    + per-claim verdicts + verify_done, so the UI can show the before→after
    revision. Replay/eval path (verify_llm=False): deterministic-only, silent —
    identical event/score profile to before the verifier existed.
    """
    run = state["run"]
    cfg = _conf(config)
    emit: Emitter = cfg.get("emit") or noop_emitter
    backend: LLMBackend = cfg["backend"]
    verify_llm = bool(cfg.get("verify_llm", True))
    brief = state.get("brief")
    if brief is None:
        return {}

    if verify_llm:
        # Render the composed brief BEFORE revising it (L2 "before").
        emit(EVENT_BRIEF, brief.model_dump(mode="json"))
        emit(EVENT_VERIFY_STARTED, {"claims_total": count_claims(brief)})

    result = run_verification(brief, run, backend=backend, verify_llm=verify_llm)

    if verify_llm and result is not None:
        for verdict in result.verdicts:
            emit(EVENT_CLAIM_VERDICT, verdict.model_dump(mode="json"))
        emit(
            EVENT_VERIFY_DONE,
            {
                "checked": result.checked,
                "supported": result.supported,
                "adjusted": result.adjusted,
                "dropped": result.dropped,
            },
        )

    return {
        "brief": brief,
        "verification": result.model_dump(mode="json") if result is not None else None,
    }


def emit_final(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Terminal-success node: emit the brief + usage and persist the cassette."""
    run = state["run"]
    cfg = _conf(config)
    emit: Emitter = cfg.get("emit") or noop_emitter
    backend: LLMBackend = cfg["backend"]
    recorder: CassetteRecorder | None = cfg.get("recorder")
    brief = state.get("brief")
    usage = _build_usage(run, backend.model)
    if brief is not None:
        emit(EVENT_BRIEF, brief.model_dump(mode="json"))
    emit(EVENT_USAGE, usage)
    if recorder is not None:
        recorder.set_final(brief.model_dump(mode="json") if brief is not None else None, usage)
    return {"usage": usage}


def emit_error(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Terminal-error node: emit a client-safe error + usage and persist the cassette."""
    run = state["run"]
    cfg = _conf(config)
    emit: Emitter = cfg.get("emit") or noop_emitter
    backend: LLMBackend = cfg["backend"]
    recorder: CassetteRecorder | None = cfg.get("recorder")
    kind, detail = state.get("error") or ("internal", "unknown error")
    _log.error("[run_error] kind=%s detail=%s", kind, detail)
    client_message = (
        detail if kind in CLIENT_SAFE_KINDS else "An internal error occurred. Please try again."
    )
    usage = _build_usage(run, backend.model)
    emit(EVENT_ERROR, {"kind": kind, "message": client_message})
    emit(EVENT_USAGE, usage)
    if recorder is not None:
        recorder.set_final(None, usage)
    return {"usage": usage}


# ---- Conditional edge routers -------------------------------------------------


def route_after_validate(state: GraphState) -> str:
    return "emit_error" if state.get("error") else "reason"


def route_after_reason(state: GraphState) -> str:
    return "emit_error" if state.get("error") else "parse_and_enrich"


def route_after_parse(state: GraphState) -> str:
    if state.get("error"):
        return "emit_error"
    if state.get("brief") is not None:
        return "verify"
    return "repair"
