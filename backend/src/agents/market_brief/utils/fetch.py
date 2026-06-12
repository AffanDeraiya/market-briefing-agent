"""fetch_page: extract readable article text from a URL with trafilatura (techspec §1, §4)."""

import json

import httpx
import trafilatura
from pydantic import BaseModel

from ..state import FETCH_PAGE_MAX_TOKENS, TOOL_TIMEOUT_S

# ~4 chars per token keeps the output under the schema.md ~2000-token cap
_MAX_CHARS = FETCH_PAGE_MAX_TOKENS * 4

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) market-briefing-agent/0.1 (educational project)"


class Page(BaseModel):
    title: str
    text: str


class PageFetchError(RuntimeError):
    """URL unreachable or no extractable article text."""


def _download(url: str) -> str:
    resp = httpx.get(
        url,
        timeout=TOOL_TIMEOUT_S,
        follow_redirects=True,
        headers={"User-Agent": _UA},
    )
    resp.raise_for_status()
    return resp.text


def fetch_page(url: str) -> Page:
    try:
        html = _download(url)
    except httpx.HTTPError as exc:
        raise PageFetchError(f"could not fetch {url}: {exc}") from exc

    extracted = trafilatura.extract(html, output_format="json", with_metadata=True)
    if not extracted:
        raise PageFetchError(f"no extractable article text at {url}")

    data = json.loads(extracted)
    text = (data.get("text") or "").strip()
    if not text:
        raise PageFetchError(f"no extractable article text at {url}")
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n[truncated]"
    return Page(title=data.get("title") or url, text=text)
