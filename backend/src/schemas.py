"""Final-output contract for the Market Briefing Agent.

The LLM agent must emit JSON that parses against `MarketBrief`.
All models use Pydantic v2 with strict validation (extra='forbid').
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DISCLAIMER = (
    "Educational project. Not financial advice."
    " Data via Yahoo Finance; may be delayed or inaccurate."
)

__all__ = [
    "Anomaly",
    "Bullet",
    "Citation",
    "ClaimVerdict",
    "DISCLAIMER",
    "MarketBrief",
    "Signal",
    "Verification",
    "parse_brief",
]


# ---------------------------------------------------------------------------
# Citation
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    url: str | None = None
    title: str
    kind: Literal["news", "web", "tool"]

    @model_validator(mode="after")
    def _url_required_for_non_tool(self) -> Citation:
        if self.kind != "tool" and not self.url:
            raise ValueError("url must be a non-empty string when kind is not 'tool'")
        return self


# ---------------------------------------------------------------------------
# Anomaly
# ---------------------------------------------------------------------------


class Anomaly(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    kind: Literal["price_spike", "price_drop", "volume_surge", "gap"]
    magnitude: str
    explanation: str
    confidence: Literal["high", "medium", "low"]
    citations: list[str]

    @model_validator(mode="after")
    def _citations_required_unless_low_confidence(self) -> Anomaly:
        if self.confidence != "low" and len(self.citations) == 0:
            raise ValueError("citations must contain at least one id when confidence is not 'low'")
        return self


# ---------------------------------------------------------------------------
# Bullet
# ---------------------------------------------------------------------------


class Bullet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    citations: list[str]

    @field_validator("citations", mode="after")
    @classmethod
    def _at_least_one_citation(cls, v: list[str]) -> list[str]:
        if len(v) < 1:
            raise ValueError("each Bullet must reference at least one citation id")
        return v


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stance: Literal["buy", "accumulate", "neutral", "reduce", "sell"]
    as_of: str = ""  # stamped by backend = brief.as_of; LLM may omit
    rationale: str
    citations: list[str]
    confidence: Literal["high", "medium", "low"]

    @field_validator("rationale", mode="after")
    @classmethod
    def _rationale_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("signal.rationale must be a non-empty string")
        return v

    @model_validator(mode="after")
    def _citations_required_unless_neutral(self) -> Signal:
        if self.stance != "neutral" and len(self.citations) == 0:
            raise ValueError('signal.citations must contain >=1 id unless stance is "neutral"')
        return self


# ---------------------------------------------------------------------------
# Claim Verifier result models
# ---------------------------------------------------------------------------


class ClaimVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Claim address: "bull_case:0" | "bear_case:1" | "news_highlights:2" |
    # "risks:0" | "anomaly:2026-06-09" | "signal"
    target: str
    label: str  # short human label (truncated claim text, <= ~80 chars)
    verdict: Literal["supported", "partial", "unsupported"]
    action: Literal["kept", "confidence_downgraded", "dropped", "neutralized"]
    note: str


class Verification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[ClaimVerdict]
    checked: int  # number of claims audited
    supported: int  # verdict == "supported"
    adjusted: int  # action in {confidence_downgraded, neutralized}
    dropped: int  # action == "dropped"


# ---------------------------------------------------------------------------
# MarketBrief
# ---------------------------------------------------------------------------


class MarketBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    name: str
    as_of: str
    period: str
    snapshot: dict[str, Any]
    # Structured technical indicators (rsi14, rsi_signal, annualized_vol_pct,
    # max_drawdown_pct, sma20_vs_price, sma50_vs_price, volume_trend). Attached
    # deterministically by the backend from compute_indicators — the LLM never
    # authors these numbers, so the field is optional in the LLM-emitted JSON.
    indicators: dict[str, Any] = Field(default_factory=dict)
    technical_summary: str
    anomalies: list[Anomaly]
    news_highlights: list[Bullet]
    bull_case: list[Bullet]
    bear_case: list[Bullet]
    risks: list[Bullet]
    signal: Signal | None = None
    verification: Verification | None = None
    citations: list[Citation]
    disclaimer: str

    @model_validator(mode="after")
    def _validate_list_caps(self) -> MarketBrief:
        if len(self.news_highlights) > 5:
            raise ValueError(
                f"news_highlights may contain at most 5 items, got {len(self.news_highlights)}"
            )
        if len(self.bull_case) > 4:
            raise ValueError(f"bull_case may contain at most 4 items, got {len(self.bull_case)}")
        if len(self.bear_case) > 4:
            raise ValueError(f"bear_case may contain at most 4 items, got {len(self.bear_case)}")
        if len(self.risks) > 3:
            raise ValueError(f"risks may contain at most 3 items, got {len(self.risks)}")
        return self

    @model_validator(mode="after")
    def _validate_citation_resolution(self) -> MarketBrief:
        defined_ids = {c.id for c in self.citations}

        unresolved: set[str] = set()

        for anomaly in self.anomalies:
            for cid in anomaly.citations:
                if cid not in defined_ids:
                    unresolved.add(cid)

        for bullet_list in (
            self.news_highlights,
            self.bull_case,
            self.bear_case,
            self.risks,
        ):
            for bullet in bullet_list:
                for cid in bullet.citations:
                    if cid not in defined_ids:
                        unresolved.add(cid)

        if self.signal is not None:
            for cid in self.signal.citations:
                if cid not in defined_ids:
                    unresolved.add(cid)

        if unresolved:
            raise ValueError(f"citation ids referenced but not defined: {sorted(unresolved)}")
        return self

    @model_validator(mode="after")
    def _validate_disclaimer(self) -> MarketBrief:
        if self.disclaimer != DISCLAIMER:
            raise ValueError(
                f"disclaimer must equal the DISCLAIMER constant exactly; got {self.disclaimer!r}"
            )
        return self


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------


def parse_brief(raw: str | dict[str, Any]) -> MarketBrief:
    """Strictly parse a JSON string or dict into a MarketBrief.

    Raises:
        ValueError: if *raw* is a string that is not valid JSON.
        pydantic.ValidationError: on any schema or validation violation.
    """
    if isinstance(raw, str):
        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"brief is not valid JSON: {exc}") from exc
    else:
        data = raw
    return MarketBrief.model_validate(data)
