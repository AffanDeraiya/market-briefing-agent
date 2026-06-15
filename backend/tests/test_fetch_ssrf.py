"""SSRF / memory-DoS / prompt-injection hardening tests for fetch.py.

All tests are network-free: socket.getaddrinfo is monkeypatched throughout.
"""

import socket
from collections.abc import Callable
from typing import Any

import pytest

from src.agents.market_brief.utils import fetch
from src.agents.market_brief.utils.fetch import (
    PageFetchError,
    UnsafeURLError,
    _host_is_safe,
    _validate_url,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _fake_gai(ip: str) -> Callable[..., list[tuple[Any, ...]]]:
    """Return a getaddrinfo stub that always resolves to *ip*."""

    def _stub(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, None, None, "", (ip, 0))]

    return _stub


# ---------------------------------------------------------------------------
# _validate_url — scheme checks
# ---------------------------------------------------------------------------


def test_validate_url_blocks_non_http_scheme_file() -> None:
    with pytest.raises(UnsafeURLError, match="scheme"):
        _validate_url("file:///etc/passwd")


def test_validate_url_blocks_non_http_scheme_ftp() -> None:
    with pytest.raises(UnsafeURLError, match="scheme"):
        _validate_url("ftp://host/x")


# ---------------------------------------------------------------------------
# _validate_url — private / metadata address blocks (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip",
    [
        "169.254.169.254",  # AWS/GCP cloud-metadata
        "127.0.0.1",  # loopback
        "10.0.0.1",  # RFC-1918 private class A
        "192.168.1.1",  # RFC-1918 private class C
    ],
)
def test_validate_url_blocks_metadata_and_private(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai(ip))
    with pytest.raises(UnsafeURLError, match="blocked non-public address"):
        _validate_url("http://whatever/")


def test_validate_url_blocks_literal_loopback_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Literal-IP host in the URL should still be blocked via getaddrinfo resolution."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("127.0.0.1"))
    with pytest.raises(UnsafeURLError, match="blocked non-public address"):
        _validate_url("http://127.0.0.1/")


# ---------------------------------------------------------------------------
# _validate_url — allows public IPs
# ---------------------------------------------------------------------------


def test_validate_url_allows_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("93.184.216.34"))
    # Must NOT raise — example.com is globally routable
    _validate_url("https://example.com/article")


# ---------------------------------------------------------------------------
# _host_is_safe — unknown host
# ---------------------------------------------------------------------------


def test_host_is_safe_unknown_host_is_unsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        raise socket.gaierror("name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", _raise)
    assert _host_is_safe("nope.invalid") is False


# ---------------------------------------------------------------------------
# fetch_page — rejects unsafe URL (SSRF guard visible at public API boundary)
# ---------------------------------------------------------------------------


def test_fetch_page_rejects_unsafe_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("127.0.0.1"))
    # UnsafeURLError is a PageFetchError subclass — callers need only catch the base.
    with pytest.raises(PageFetchError):
        fetch.fetch_page("http://localhost/")


def test_fetch_page_rejects_unsafe_url_raises_unsafe_subclass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("127.0.0.1"))
    with pytest.raises(UnsafeURLError):
        fetch.fetch_page("http://localhost/")


# ---------------------------------------------------------------------------
# fetch_page — untrusted prefix is always prepended
# ---------------------------------------------------------------------------

_HTML_ARTICLE = """
<html><head><title>Test Article</title></head>
<body><article><p>This is the article body text with enough words to be extracted.</p>
<p>More content here to make trafilatura happy with extraction.</p></article></body></html>
"""


def test_untrusted_prefix_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch, "_download", lambda url: _HTML_ARTICLE)
    page = fetch.fetch_page("https://example.com/article")
    assert page.text.startswith("[Untrusted external web content")


def test_untrusted_prefix_present_with_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prefix must appear even when the article text hits the truncation cap."""
    long_para = "<p>" + ("Word " * 200) + "</p>"
    many_paras = long_para * 500  # well over _MAX_CHARS worth of text
    html = (
        f"<html><head><title>Long</title></head><body><article>{many_paras}</article></body></html>"
    )
    monkeypatch.setattr(fetch, "_download", lambda url: html)
    page = fetch.fetch_page("https://example.com/long")
    assert page.text.startswith("[Untrusted external web content")
    assert page.text.endswith("[truncated]")
    # Verify the total length is bounded (prefix + capped text + "[truncated]")
    assert len(page.text) <= len(fetch._UNTRUSTED_PREFIX) + fetch._MAX_CHARS + len("\n[truncated]")


# ---------------------------------------------------------------------------
# Existing behaviour preserved: no-article raises, truncation cap
# ---------------------------------------------------------------------------


def test_fetch_page_no_article_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch, "_download", lambda url: "<html><body></body></html>")
    with pytest.raises(fetch.PageFetchError):
        fetch.fetch_page("https://x.example/empty")
