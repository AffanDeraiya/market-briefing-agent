"""Offline cassette replay — drives run_agent with recorded LLM + tool responses.

Zero network or LLM calls are made during replay; all external I/O is served
from the cassette JSON.  Use replay_cassette() in evals and tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from src.llm import LLMBackend, LLMResponse, ToolSpec, Turn
from src.schemas import MarketBrief

__all__ = [
    "ReplayBackend",
    "ReplayToolExecutor",
    "ReplayResult",
    "load_cassette",
    "replay_cassette",
    "discover_cassettes",
]


# ---------------------------------------------------------------------------
# ReplayBackend
# ---------------------------------------------------------------------------


class ReplayBackend(LLMBackend):
    """Returns pre-recorded LLMResponse objects in cassette order.

    Raises IndexError (with a descriptive message) if the loop asks for more
    LLM calls than were recorded.
    """

    def __init__(self, llm_turns: list[dict[str, Any]]) -> None:
        self.model = "replay"
        self._turns: list[dict[str, Any]] = llm_turns
        self._i: int = 0

    def complete(
        self,
        *,
        system: str,
        history: list[Turn],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResponse:
        if self._i >= len(self._turns):
            raise IndexError(
                f"ReplayBackend exhausted: requested turn {self._i + 1} "
                f"but cassette only has {len(self._turns)} turns"
            )
        response_dict = self._turns[self._i]["response"]
        self._i += 1
        return LLMResponse.model_validate(response_dict)


# ---------------------------------------------------------------------------
# ReplayToolExecutor
# ---------------------------------------------------------------------------


class ReplayToolExecutor:
    """Returns pre-recorded tool outputs in cassette order.

    Callable signature matches execute_tool: (name, tool_input, **kwargs) → (str, bool).
    Name is accepted but NOT asserted — outputs are returned strictly in sequence.
    """

    def __init__(self, tool_io: list[dict[str, Any]]) -> None:
        self._tool_io: list[dict[str, Any]] = tool_io
        self._i: int = 0

    def __call__(
        self,
        name: str,
        tool_input: dict[str, Any],
        **kwargs: Any,
    ) -> tuple[str, bool]:
        if self._i >= len(self._tool_io):
            recorded_name = self._tool_io[-1]["name"] if self._tool_io else "none"
            raise IndexError(
                f"ReplayToolExecutor exhausted: requested call {self._i + 1} "
                f"but cassette only has {len(self._tool_io)} tool entries "
                f"(last recorded: {recorded_name!r})"
            )
        output: str = self._tool_io[self._i]["output"]
        self._i += 1
        return output, False


# ---------------------------------------------------------------------------
# ReplayResult
# ---------------------------------------------------------------------------


@dataclass
class ReplayResult:
    """Outcome of replaying a single cassette."""

    name: str
    request: dict[str, Any]
    brief: MarketBrief | None
    error: tuple[str, str] | None
    usage: dict[str, Any]
    tool_io: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_cassette(path: str | Path) -> dict[str, Any]:
    """Load and return the cassette dict from *path* (UTF-8 JSON)."""
    with Path(path).open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


def replay_cassette(path: str | Path) -> ReplayResult:
    """Replay a cassette file and return a ReplayResult.

    Makes ZERO network or LLM calls — all I/O is served from the cassette.
    The ``today`` date is taken from ``final_brief.as_of`` when present so
    that time-sensitive prompts render identically to the original run.
    """
    from src.agents.market_brief.agent import run_agent

    cas = load_cassette(path)

    backend = ReplayBackend(cas["llm_turns"])
    executor = ReplayToolExecutor(cas["tool_io"])

    # Preserve the original "today" so the user message matches what was recorded.
    final_brief_dict: dict[str, Any] | None = cas.get("final_brief")
    today: str | None = None
    if isinstance(final_brief_dict, dict):
        as_of = final_brief_dict.get("as_of")
        today = as_of if isinstance(as_of, str) else None

    with patch("src.agents.market_brief.utils.reasoning.execute_tool", executor):
        result = run_agent(
            cas["request"]["ticker"],
            cas["request"]["period"],
            backend=backend,
            today=today,
            verify_llm=False,  # deterministic-only verifier offline; no recorded verifier turn
        )

    return ReplayResult(
        name=Path(path).stem,
        request=cas["request"],
        brief=result.brief,
        error=result.error,
        usage=result.usage,
        tool_io=cas["tool_io"],
    )


def discover_cassettes(cassettes_dir: str | Path) -> list[Path]:
    """Return all *.json cassette files in *cassettes_dir*, sorted by name."""
    return sorted(Path(cassettes_dir).glob("*.json"))
