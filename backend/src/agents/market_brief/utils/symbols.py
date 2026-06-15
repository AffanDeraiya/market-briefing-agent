"""Ticker-symbol autocomplete via Yahoo Finance's public search endpoint."""

from __future__ import annotations

import httpx
from pydantic import BaseModel

from ..state import TOOL_TIMEOUT_S

__all__ = ["SymbolSuggestion", "search_symbols"]

_YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) market-briefing-agent/0.1 (educational project)"
_ALLOWED_TYPES = {"EQUITY", "ETF", "INDEX", "MUTUALFUND", "CRYPTOCURRENCY"}


class SymbolSuggestion(BaseModel):
    """A single ticker suggestion returned by the autocomplete endpoint."""

    symbol: str
    name: str
    exchange: str


def search_symbols(query: str, max_results: int = 8) -> list[SymbolSuggestion]:
    """Return up to *max_results* ticker suggestions for *query*.

    Network-graceful: any HTTP or parse error returns an empty list rather
    than raising, so callers never need to handle exceptions from this function.
    """
    q = (query or "").strip()
    if not q or len(q) > 32:
        return []

    try:
        resp = httpx.get(
            _YAHOO_SEARCH_URL,
            params={"q": q, "quotesCount": max_results, "newsCount": 0},
            headers={"User-Agent": _UA},
            timeout=TOOL_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    out: list[SymbolSuggestion] = []
    for quote in data.get("quotes", []):
        if not isinstance(quote, dict):
            continue
        symbol = quote.get("symbol")
        if not symbol or quote.get("quoteType") not in _ALLOWED_TYPES:
            continue
        name = quote.get("shortname") or quote.get("longname") or symbol
        exchange = quote.get("exchDisp") or quote.get("exchange") or ""
        out.append(
            SymbolSuggestion(
                symbol=str(symbol),
                name=str(name),
                exchange=str(exchange),
            )
        )
        if len(out) >= max_results:
            break

    return out
