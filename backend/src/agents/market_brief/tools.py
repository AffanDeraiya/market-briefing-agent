"""Tool registry: 7 LLM-callable tools (schema.md §2).

Each Tool wraps a ToolSpec (name/description/JSON-Schema) and a handler that
accepts the parsed input dict and returns a compact JSON string.  All network
I/O is delegated to the utils layer; this module only wires specs to handlers
and enforces the wall-clock per-tool timeout.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import date
from typing import Any

from src.llm import ToolSpec

from .state import TOOL_TIMEOUT_S
from .utils.anomalies import detect_anomalies
from .utils.fetch import fetch_page
from .utils.indicators import compute_indicators
from .utils.market_data import fetch_ohlcv, get_fundamentals, get_price_history
from .utils.search import get_company_news, search_web

__all__ = ["Tool", "TOOLS", "tool_specs", "execute_tool"]

# ---------------------------------------------------------------------------
# Primitive
# ---------------------------------------------------------------------------

_PERIOD_ENUM = ["1mo", "3mo", "6mo", "1y"]


@dataclass(frozen=True)
class Tool:
    """Pairs an LLM-facing ToolSpec with a sync handler."""

    spec: ToolSpec
    handler: Callable[[dict[str, Any]], str]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_get_price_history(tool_input: dict[str, Any]) -> str:
    ticker: str = tool_input["ticker"]
    period: str = tool_input["period"]
    return get_price_history(ticker, period).model_dump_json()  # type: ignore[arg-type]


def _handle_get_fundamentals(tool_input: dict[str, Any]) -> str:
    ticker: str = tool_input["ticker"]
    return get_fundamentals(ticker).model_dump_json()


def _handle_compute_indicators(tool_input: dict[str, Any]) -> str:
    ticker: str = tool_input["ticker"]
    period: str = tool_input["period"]
    df = fetch_ohlcv(ticker, period)  # type: ignore[arg-type]
    return compute_indicators(df).model_dump_json()


def _handle_detect_anomalies(tool_input: dict[str, Any]) -> str:
    ticker: str = tool_input["ticker"]
    period: str = tool_input["period"]
    df = fetch_ohlcv(ticker, period)  # type: ignore[arg-type]
    return detect_anomalies(df).model_dump_json()


def _parse_date(value: object) -> date | None:
    """Return a date from an ISO string, or None when absent/empty."""
    if not isinstance(value, str) or not value.strip():
        return None
    return date.fromisoformat(value.strip())


def _handle_get_company_news(tool_input: dict[str, Any]) -> str:
    query: str = tool_input["query"]
    from_date = _parse_date(tool_input.get("from_date"))
    to_date = _parse_date(tool_input.get("to_date"))
    max_results: int = int(tool_input.get("max_results", 5))
    return get_company_news(query, from_date, to_date, max_results).model_dump_json()


def _handle_search_web(tool_input: dict[str, Any]) -> str:
    query: str = tool_input["query"]
    max_results: int = int(tool_input.get("max_results", 5))
    return search_web(query, max_results).model_dump_json()


def _handle_fetch_page(tool_input: dict[str, Any]) -> str:
    url: str = tool_input["url"]
    return fetch_page(url).model_dump_json()


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: dict[str, Tool] = {
    "get_price_history": Tool(
        spec=ToolSpec(
            name="get_price_history",
            description=(
                "Retrieve compact price history for a ticker over a given period: "
                "latest close, period change %, weekly aggregates, and the 5 most "
                "volatile trading days.  Use this first to orient yourself on price action."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "period": {"type": "string", "enum": _PERIOD_ENUM},
                },
                "required": ["ticker", "period"],
                "additionalProperties": False,
            },
        ),
        handler=_handle_get_price_history,
    ),
    "get_fundamentals": Tool(
        spec=ToolSpec(
            name="get_fundamentals",
            description=(
                "Fetch key fundamental data for a ticker: name, sector, market cap, "
                "P/E ratios, dividend yield, beta, and next earnings date.  "
                "Nulls are real — never invented."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                },
                "required": ["ticker"],
                "additionalProperties": False,
            },
        ),
        handler=_handle_get_fundamentals,
    ),
    "compute_indicators": Tool(
        spec=ToolSpec(
            name="compute_indicators",
            description=(
                "Compute technical indicators (SMA20/50 vs price, RSI-14, annualised "
                "volatility, max drawdown, volume trend) for a ticker/period.  "
                "Values are deterministic — do not recompute them yourself."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "period": {"type": "string", "enum": _PERIOD_ENUM},
                },
                "required": ["ticker", "period"],
                "additionalProperties": False,
            },
        ),
        handler=_handle_compute_indicators,
    ),
    "detect_anomalies": Tool(
        spec=ToolSpec(
            name="detect_anomalies",
            description=(
                "Detect statistically significant price spikes/drops, volume surges, "
                "and overnight gaps for a ticker/period.  Returns up to 8 anomaly events "
                "with dates and magnitudes — investigate each anomaly with get_company_news."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "period": {"type": "string", "enum": _PERIOD_ENUM},
                },
                "required": ["ticker", "period"],
                "additionalProperties": False,
            },
        ),
        handler=_handle_detect_anomalies,
    ),
    "get_company_news": Tool(
        spec=ToolSpec(
            name="get_company_news",
            description=(
                "Search recent news for a query, optionally scoped to a date window "
                "(ISO YYYY-MM-DD); use this to investigate what caused an anomaly on "
                "a specific date."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "from_date": {
                        "type": ["string", "null"],
                        "description": "ISO YYYY-MM-DD start date (inclusive), or null",
                    },
                    "to_date": {
                        "type": ["string", "null"],
                        "description": "ISO YYYY-MM-DD end date (inclusive), or null",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 5,
                        "description": "Maximum number of results to return",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        handler=_handle_get_company_news,
    ),
    "search_web": Tool(
        spec=ToolSpec(
            name="search_web",
            description=(
                "Run a general web search for background context; prefer get_company_news "
                "for date-scoped anomaly investigation.  Results include title, snippet, "
                "and URL."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {
                        "type": "integer",
                        "default": 5,
                        "description": "Maximum number of results to return",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        handler=_handle_search_web,
    ),
    "fetch_page": Tool(
        spec=ToolSpec(
            name="fetch_page",
            description=(
                "Fetch and extract the readable article text from a URL; use this to "
                "read a news article returned by get_company_news or search_web in full."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        ),
        handler=_handle_fetch_page,
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def tool_specs() -> list[ToolSpec]:
    """Return the ToolSpec for every registered tool (ordered as defined)."""
    return [t.spec for t in TOOLS.values()]


def execute_tool(
    name: str,
    tool_input: dict[str, Any],
    timeout_s: float = TOOL_TIMEOUT_S,
) -> tuple[str, bool]:
    """Run a tool by name within a wall-clock timeout.

    Returns (content_json, is_error).  Unknown tool name, handler exceptions
    (TickerNotFoundError, SearchError, PageFetchError, ValueError, …), and
    timeout all produce is_error=True with a JSON error payload.
    The timeout is enforced via ThreadPoolExecutor.submit / future.result —
    cross-platform (no signals required).
    """
    if name not in TOOLS:
        return json.dumps({"error": f"unknown tool: {name!r}"}), True

    handler = TOOLS[name].handler

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(handler, tool_input)
        try:
            result = future.result(timeout=timeout_s)
        except FuturesTimeoutError:
            return json.dumps({"error": f"tool timed out after {timeout_s}s"}), True
        except Exception as exc:
            return json.dumps({"error": str(exc)}), True

    return result, False
