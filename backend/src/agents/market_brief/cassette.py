"""Cassette recording for offline LLM replay (schema.md §5).

A CassetteRecorder captures every LLM call and tool invocation during a live
run and serialises the result to JSON.  The evals harness replays these
cassettes via a mock backend so CI never makes real API calls.

Cassette format:
    {
      "request":   {...},
      "llm_turns": [{"request_messages_hash": str, "response": {...}}],
      "tool_io":   [{"seq": int, "name": str, "input": {...}, "output": str}],
      "final_brief": {...} | null,
      "usage":     {...}
    }
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.llm import LLMBackend, LLMResponse, ToolSpec, Turn

__all__ = [
    "CassetteRecorder",
    "RecordingBackend",
    "hash_history",
]


# ---------------------------------------------------------------------------
# Stable hash for request deduplication / cassette keying
# ---------------------------------------------------------------------------


def hash_history(system: str, history: list[Turn], tools: list[ToolSpec]) -> str:
    """Return a stable SHA-256 hex digest of the given LLM request inputs.

    The same (system, history, tools) triple always produces the same hash;
    any difference produces a different hash.
    """
    payload = {
        "system": system,
        "history": [t.model_dump(mode="json") for t in history],
        "tools": [s.model_dump(mode="json") for s in tools],
    }
    serialised = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialised.encode()).hexdigest()


# ---------------------------------------------------------------------------
# CassetteRecorder
# ---------------------------------------------------------------------------


class CassetteRecorder:
    """Accumulates LLM-call and tool-call records during a single agent run."""

    def __init__(self, request: dict[str, Any]) -> None:
        self._request: dict[str, Any] = request
        self._llm_turns: list[dict[str, Any]] = []
        self._tool_io: list[dict[str, Any]] = []
        self._final_brief: dict[str, Any] | None = None
        self._usage: dict[str, Any] = {}

    def record_llm(self, request_messages_hash: str, response: LLMResponse) -> None:
        """Store one LLM turn (hash + serialised response)."""
        self._llm_turns.append(
            {
                "request_messages_hash": request_messages_hash,
                "response": response.model_dump(mode="json"),
            }
        )

    def record_tool(
        self,
        seq: int,
        name: str,
        tool_input: dict[str, Any],
        output: str,
    ) -> None:
        """Store one tool invocation."""
        self._tool_io.append(
            {
                "seq": seq,
                "name": name,
                "input": tool_input,
                "output": output,
            }
        )

    def set_final(
        self,
        brief: dict[str, Any] | None,
        usage: dict[str, Any],
    ) -> None:
        """Record the final brief (or None on error) and the run usage summary."""
        self._final_brief = brief
        self._usage = usage

    def to_dict(self) -> dict[str, Any]:
        """Return the full cassette as a plain dict."""
        return {
            "request": self._request,
            "llm_turns": self._llm_turns,
            "tool_io": self._tool_io,
            "final_brief": self._final_brief,
            "usage": self._usage,
        }

    def dump(self, path: str | Path) -> None:
        """Write the cassette to *path* as indented JSON (UTF-8)."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Recording backend wrapper
# ---------------------------------------------------------------------------


class RecordingBackend(LLMBackend):
    """Wraps a real LLMBackend and records every call into a CassetteRecorder."""

    def __init__(self, inner: LLMBackend, recorder: CassetteRecorder) -> None:
        self.model: str = inner.model
        self._inner = inner
        self._rec = recorder

    def complete(
        self,
        *,
        system: str,
        history: list[Turn],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResponse:
        h = hash_history(system, history, tools)
        resp = self._inner.complete(
            system=system,
            history=history,
            tools=tools,
            max_tokens=max_tokens,
        )
        self._rec.record_llm(h, resp)
        return resp
