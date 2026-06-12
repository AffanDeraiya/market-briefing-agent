"""Search adapter + fetch_page tests — fully offline (providers monkeypatched)."""

import datetime as dt
from typing import Any

import pytest

from src.agents.market_brief.utils import fetch, search


class FakeDDGS:
    last_text_query = ""
    last_news_query = ""
    last_max_results = 0
    text_results: list[dict[str, str]] = []
    news_results: list[dict[str, str]] = []
    raise_on_call = False

    def __init__(self, **_: Any) -> None:
        pass

    def text(self, query: str, max_results: int) -> list[dict[str, str]]:
        if FakeDDGS.raise_on_call:
            raise RuntimeError("ddg down")
        FakeDDGS.last_text_query = query
        FakeDDGS.last_max_results = max_results
        return FakeDDGS.text_results

    def news(self, query: str, max_results: int) -> list[dict[str, str]]:
        if FakeDDGS.raise_on_call:
            raise RuntimeError("ddg down")
        FakeDDGS.last_news_query = query
        FakeDDGS.last_max_results = max_results
        return FakeDDGS.news_results


@pytest.fixture(autouse=True)
def fake_ddgs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.agents.market_brief.utils.search.DDGS", FakeDDGS)
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    FakeDDGS.text_results = [
        {"title": "T1", "body": "B1", "href": "https://a.example/1"},
    ]
    FakeDDGS.news_results = [
        {
            "title": "N1",
            "body": "B1",
            "url": "https://n.example/1",
            "source": "Reuters",
            "date": "2026-03-03T12:00:00+00:00",
        },
        {
            "title": "N2",
            "body": "B2",
            "url": "https://n.example/2",
            "source": "AP",
            "date": "2026-01-15T00:00:00+00:00",
        },
    ]
    FakeDDGS.raise_on_call = False


def test_search_web_maps_fields() -> None:
    out = search.search_web("tesla recall")
    assert out.results[0].title == "T1"
    assert out.results[0].snippet == "B1"
    assert out.results[0].url == "https://a.example/1"


def test_search_web_caps_max_results() -> None:
    search.search_web("q", max_results=50)
    assert FakeDDGS.last_max_results == 5


def test_news_date_scoping_in_query_and_postfilter() -> None:
    out = search.get_company_news(
        "TSLA drop",
        from_date=dt.date(2026, 2, 28),
        to_date=dt.date(2026, 3, 6),
    )
    assert "after:2026-02-28" in FakeDDGS.last_news_query
    assert "before:2026-03-06" in FakeDDGS.last_news_query
    # N2 (Jan 15) falls outside the window and is post-filtered out
    assert [r.title for r in out.results] == ["N1"]
    assert out.results[0].published == "2026-03-03"


def test_news_keeps_undated_results() -> None:
    FakeDDGS.news_results = [{"title": "N3", "body": "B", "url": "https://n.example/3"}]
    out = search.get_company_news("q", from_date=dt.date(2026, 3, 1))
    assert [r.title for r in out.results] == ["N3"]
    assert out.results[0].published is None


def test_search_provider_failure_raises_search_error() -> None:
    FakeDDGS.raise_on_call = True
    with pytest.raises(search.SearchError):
        search.search_web("q")


def test_tavily_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(search.SearchError):
        search.search_web("q")


_HTML = """
<html><head><title>Quarterly Results</title></head><body>
<main><h1>Quarterly Results</h1>{}</main></body></html>
"""


def test_fetch_page_extracts_and_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    paragraphs = "".join(
        f"<p>Sentence {i} of substantial article body text.</p>" for i in range(2000)
    )
    monkeypatch.setattr(fetch, "_download", lambda url: _HTML.format(paragraphs))
    page = fetch.fetch_page("https://x.example/article")
    assert "Quarterly Results" in page.title
    assert page.text.endswith("[truncated]")
    assert len(page.text) <= fetch._MAX_CHARS + len("\n[truncated]")


def test_fetch_page_no_article_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch, "_download", lambda url: "<html><body></body></html>")
    with pytest.raises(fetch.PageFetchError):
        fetch.fetch_page("https://x.example/empty")
