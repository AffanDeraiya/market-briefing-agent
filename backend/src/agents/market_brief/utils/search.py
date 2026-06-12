"""News/web search adapter — ddgs by default, Tavily behind SEARCH_PROVIDER env (techspec §1).

DuckDuckGo has no exact date-range filter; date scoping is approximated by
appending after:/before: operators to the query and post-filtering news
results on their published date when one is present. Tavily (optional, keyed)
supports ranges natively via days-back.
"""

import datetime as dt
import os
from typing import Any

import httpx
from ddgs import DDGS
from pydantic import BaseModel

from ..state import SEARCH_MAX_RESULTS, TOOL_TIMEOUT_S


class SearchResult(BaseModel):
    title: str
    snippet: str
    url: str


class NewsResult(BaseModel):
    title: str
    snippet: str
    url: str
    source: str | None
    published: str | None


class SearchResponse(BaseModel):
    results: list[SearchResult]


class NewsResponse(BaseModel):
    results: list[NewsResult]


class SearchError(RuntimeError):
    """Upstream search provider failure."""


def _provider() -> str:
    return os.environ.get("SEARCH_PROVIDER", "ddgs").lower()


def _cap(max_results: int) -> int:
    return max(1, min(max_results, SEARCH_MAX_RESULTS))


def _scoped_query(query: str, from_date: dt.date | None, to_date: dt.date | None) -> str:
    if from_date:
        query += f" after:{from_date.isoformat()}"
    if to_date:
        query += f" before:{to_date.isoformat()}"
    return query


def search_web(query: str, max_results: int = SEARCH_MAX_RESULTS) -> SearchResponse:
    if _provider() == "tavily":
        return SearchResponse(results=_tavily_search(query, _cap(max_results)))
    try:
        raw = DDGS(timeout=TOOL_TIMEOUT_S).text(query, max_results=_cap(max_results))
    except Exception as exc:
        raise SearchError(f"web search failed: {exc}") from exc
    return SearchResponse(
        results=[
            SearchResult(
                title=r.get("title", ""),
                snippet=r.get("body", ""),
                url=r.get("href", ""),
            )
            for r in raw
        ]
    )


def get_company_news(
    query: str,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    max_results: int = SEARCH_MAX_RESULTS,
) -> NewsResponse:
    if _provider() == "tavily":
        results = _tavily_search(_scoped_query(query, from_date, to_date), _cap(max_results))
        return NewsResponse(
            results=[NewsResult(**r.model_dump(), source=None, published=None) for r in results]
        )
    try:
        raw = DDGS(timeout=TOOL_TIMEOUT_S).news(
            _scoped_query(query, from_date, to_date), max_results=_cap(max_results)
        )
    except Exception as exc:
        raise SearchError(f"news search failed: {exc}") from exc

    news_items: list[NewsResult] = []
    for r in raw:
        published = _normalize_date(r.get("date"))
        if _outside_window(published, from_date, to_date):
            continue
        news_items.append(
            NewsResult(
                title=r.get("title", ""),
                snippet=r.get("body", ""),
                url=r.get("url", ""),
                source=r.get("source"),
                published=published,
            )
        )
    return NewsResponse(results=news_items)


def _normalize_date(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10] if len(value) >= 10 else value


def _outside_window(
    published: str | None, from_date: dt.date | None, to_date: dt.date | None
) -> bool:
    if published is None:
        return False  # keep undated results; the agent weighs them itself
    try:
        date = dt.date.fromisoformat(published[:10])
    except ValueError:
        return False
    return (from_date is not None and date < from_date) or (to_date is not None and date > to_date)


def _tavily_search(query: str, max_results: int) -> list[SearchResult]:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise SearchError("SEARCH_PROVIDER=tavily but TAVILY_API_KEY is not set")
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": max_results},
            timeout=TOOL_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise SearchError(f"tavily search failed: {exc}") from exc
    return [
        SearchResult(
            title=r.get("title", ""),
            snippet=r.get("content", ""),
            url=r.get("url", ""),
        )
        for r in data.get("results", [])
    ]
