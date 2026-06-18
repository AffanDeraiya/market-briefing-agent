"""Agent orchestrator — wires nodes into the while-loop (orchestration only).

No tool mechanics, no LLM wire-format handling live here; those live in
nodes.py and llm.py respectively.  This module is the single place that
encodes the control-flow contract (schema.md §4 agent loop state machine).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from src.llm import LLMBackend, Turn
from src.schemas import MarketBrief

try:
    from openai import RateLimitError as _OpenAIRateLimitError
except ImportError:  # pragma: no cover
    _OpenAIRateLimitError = None  # type: ignore[assignment,misc]

try:
    from anthropic import RateLimitError as _AnthropicRateLimitError
except ImportError:  # pragma: no cover
    _AnthropicRateLimitError = None  # type: ignore[assignment,misc]

from .cassette import CassetteRecorder, RecordingBackend
from .events import (
    EVENT_BRIEF,
    EVENT_ERROR,
    EVENT_RUN_STARTED,
    EVENT_STEP,
    EVENT_USAGE,
    Emitter,
    estimate_cost_usd,
    noop_emitter,
)
from .nodes import (
    attach_market_data,
    call_llm,
    inject_finalize,
    inject_repair,
    parse_final,
    run_tool_calls,
)
from .prompts import SYSTEM_PROMPT, build_user_message
from .state import (
    MAX_ITERATIONS,
    MAX_OUTPUT_TOKENS,
    RUN_TIMEOUT_S,
    RunState,
)
from .tools import tool_specs

_log = logging.getLogger("market_brief.agent")

__all__ = ["RunResult", "run_agent", "CLIENT_SAFE_KINDS"]

# Error kinds whose messages are safe to surface directly to clients.
# All other kinds get a generic message in the emitted SSE event; the
# full detail is still preserved in RunResult.error for server-side logging.
CLIENT_SAFE_KINDS: frozenset[str] = frozenset(
    {"validation", "budget", "timeout", "parse", "upstream"}
)


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
# Main entry point
# ---------------------------------------------------------------------------


def run_agent(
    ticker: str,
    period: str,
    *,
    backend: LLMBackend,
    emit: Emitter | None = None,
    recorder: CassetteRecorder | None = None,
    today: str | None = None,
) -> RunResult:
    """Run the market-brief agent loop and return a RunResult.

    Parameters
    ----------
    ticker:   Stock ticker symbol (e.g. "AAPL").
    period:   Historical period — one of 1mo/3mo/6mo/1y.
    backend:  Concrete LLMBackend to use for completions.
    emit:     Optional Emitter; defaults to noop_emitter.
    recorder: Optional CassetteRecorder; pass to persist a replay cassette.
    today:    ISO date string to inject as "today" in the user message; defaults
              to the real date.today().
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

    state = RunState(ticker=ticker, period=period)  # type: ignore[arg-type]
    state.history.append(Turn(role="user", text=build_user_message(ticker, period, _today)))

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

    error: tuple[str, str] | None = None
    brief: MarketBrief | None = None

    try:
        while True:
            # ── Hard stops ────────────────────────────────────────────────
            if state.timed_out():
                error = ("timeout", f"run exceeded {RUN_TIMEOUT_S}s")
                break
            if state.iteration_budget_exceeded():
                error = ("budget", f"max iterations ({MAX_ITERATIONS}) reached")
                break

            # ── LLM call ─────────────────────────────────────────────────
            _log.info("[iteration %d] calling LLM...", state.iterations + 1)
            response = call_llm(
                state,
                _backend,
                system=SYSTEM_PROMPT,
                tools=tool_specs(),
                max_tokens=MAX_OUTPUT_TOKENS,
            )

            _log.info(
                "[iteration %d] response: is_final=%s tool_calls=%d text_len=%d",
                state.iterations,
                response.is_final,
                len(response.tool_calls),
                len(response.text),
            )
            if response.text.strip():
                _log.debug("[iteration %d] text preview: %s", state.iterations, response.text[:300])

            if response.text.strip():
                _emit(
                    EVENT_STEP,
                    {"iteration": state.iterations, "thinking": response.text[:300]},
                )

            # ── Final response branch ─────────────────────────────────────
            if response.is_final:
                _log.info(
                    "[iteration %d] final response received, attempting parse", state.iterations
                )
                try:
                    brief = parse_final(response.text, state.seen_urls)
                    attach_market_data(state, brief)
                    _log.info("[run_ok] brief parsed successfully")
                    break
                except (ValidationError, ValueError) as exc:
                    _log.warning("[parse_fail] %s", str(exc)[:400])
                    _log.warning("[parse_fail] text was: %s", response.text[:600])
                    if not state.repair_attempted:
                        _log.info("[repair] injecting repair prompt")
                        inject_repair(state, str(exc))
                        continue
                    error = ("parse", f"brief failed validation after repair: {exc}")
                    break

            # ── Tool call branch ──────────────────────────────────────────
            else:
                run_tool_calls(state, response, _emit, recorder=recorder)
                if state.tool_budget_exceeded() or state.timed_out():
                    if not state.finalize_injected:
                        inject_finalize(state)
                        continue
                    else:
                        error = ("budget", "tool budget exhausted; model did not finalize")
                        break

    except Exception as exc:  # noqa: BLE001 — last-resort guard; must always emit usage
        # Surface provider rate-limit errors as 'upstream' so the client sees a useful
        # message instead of the generic "An internal error occurred." fallback.
        _is_rate_limit = (
            _OpenAIRateLimitError is not None and isinstance(exc, _OpenAIRateLimitError)
        ) or (_AnthropicRateLimitError is not None and isinstance(exc, _AnthropicRateLimitError))
        if _is_rate_limit:
            _log.warning("[rate_limit] provider returned 429: %s", str(exc)[:300])
            error = (
                "budget",
                "The demo has hit its LLM provider rate limit. Please try again in a few minutes.",
            )
        else:
            _log.exception("[unhandled] %s: %s", type(exc).__name__, exc)
            error = ("internal", f"{type(exc).__name__}: {exc}")

    # ── Usage summary ─────────────────────────────────────────────────────
    usage: dict[str, Any] = {
        "input_tokens": state.input_tokens,
        "output_tokens": state.output_tokens,
        "est_cost_usd": estimate_cost_usd(_backend.model, state.input_tokens, state.output_tokens),
        "tool_calls": state.tool_calls_made,
        "iterations": state.iterations,
        "latency_ms": int(state.elapsed_s() * 1000),
    }

    if brief is not None:
        _emit(EVENT_BRIEF, brief.model_dump(mode="json"))
    elif error is not None:
        kind, detail = error
        _log.error("[run_error] kind=%s detail=%s", kind, detail)
        # Only expose message detail for well-understood, client-safe error kinds.
        # Internal / upstream errors get a generic message so that stack traces,
        # third-party service names, etc. are not leaked to the client.
        # The full detail remains in RunResult.error for server-side logging.
        client_message = (
            detail if kind in CLIENT_SAFE_KINDS else "An internal error occurred. Please try again."
        )
        _emit(EVENT_ERROR, {"kind": kind, "message": client_message})
    _emit(EVENT_USAGE, usage)

    if recorder is not None:
        recorder.set_final(
            brief.model_dump(mode="json") if brief is not None else None,
            usage,
        )

    return RunResult(brief=brief, error=error, usage=usage)
