"""LLM provider adapter — normalises Anthropic native blocks and OpenAI-compat
tool_calls into ONE internal contract so the agent loop never touches wire formats.

Env vars consumed by get_backend():
  LLM_PROVIDER       default "gemini"   | "anthropic" | "groq"
  LLM_MODEL          default "gemini-2.5-flash"
  ANTHROPIC_API_KEY  required for provider "anthropic"
  GEMINI_API_KEY     required for provider "gemini"
  GROQ_API_KEY       required for provider "groq"
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Literal

import anthropic
import openai
from pydantic import BaseModel

__all__ = [
    # contract types
    "ToolSpec",
    "ToolCall",
    "ToolResult",
    "Turn",
    "Usage",
    "LLMResponse",
    # backends
    "LLMBackend",
    "AnthropicBackend",
    "OpenAICompatBackend",
    # factory
    "get_backend",
    # pure helpers (exported for testing)
    "to_anthropic_messages",
    "to_anthropic_tools",
    "parse_anthropic_response",
    "to_openai_messages",
    "to_openai_tools",
    "parse_openai_response",
    "_safe_json",
    # constants
    "GEMINI_BASE_URL",
    "GROQ_BASE_URL",
]

# ---------------------------------------------------------------------------
# Provider constants
# ---------------------------------------------------------------------------

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# ---------------------------------------------------------------------------
# Normalised contract types
# ---------------------------------------------------------------------------


class ToolSpec(BaseModel):
    """Describes a tool the LLM may call."""

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCall(BaseModel):
    """A single tool invocation requested by the assistant."""

    id: str
    name: str
    input: dict[str, Any]


class ToolResult(BaseModel):
    """The result of executing a ToolCall."""

    call_id: str
    name: str
    content: str
    is_error: bool = False


class Turn(BaseModel):
    """One provider-agnostic history message."""

    role: Literal["user", "assistant", "tool"]
    text: str = ""
    tool_calls: list[ToolCall] = []
    tool_results: list[ToolResult] = []

    model_config = {"populate_by_name": True}  # Pydantic v2 compatibility


class Usage(BaseModel):
    """Token usage for one LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0


class LLMResponse(BaseModel):
    """Normalised response from any backend."""

    text: str
    tool_calls: list[ToolCall] = []
    usage: Usage
    stop_reason: str | None = None

    @property
    def wants_tools(self) -> bool:
        """True when the assistant wants to call one or more tools."""
        return bool(self.tool_calls)

    @property
    def is_final(self) -> bool:
        """True when the assistant produced a final text response (no tool calls)."""
        return not self.tool_calls


# ---------------------------------------------------------------------------
# Anthropic pure conversion functions
# ---------------------------------------------------------------------------


def to_anthropic_messages(history: list[Turn]) -> list[dict[str, Any]]:
    """Serialise an internal history into the Anthropic Messages API format."""
    messages: list[dict[str, Any]] = []

    for turn in history:
        if turn.role == "user":
            messages.append({"role": "user", "content": turn.text})

        elif turn.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if turn.text:
                blocks.append({"type": "text", "text": turn.text})
            for tc in turn.tool_calls:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.input,
                    }
                )
            messages.append({"role": "assistant", "content": blocks})

        elif turn.role == "tool":
            content_blocks: list[dict[str, Any]] = [
                {
                    "type": "tool_result",
                    "tool_use_id": tr.call_id,
                    "content": tr.content,
                    "is_error": tr.is_error,
                }
                for tr in turn.tool_results
            ]
            messages.append({"role": "user", "content": content_blocks})

    return messages


def to_anthropic_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Serialise ToolSpec list into Anthropic tool definitions."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in tools
    ]


def parse_anthropic_response(resp: Any) -> LLMResponse:
    """Parse a raw Anthropic Messages response into an LLMResponse."""
    collected_text: list[str] = []
    tool_calls: list[ToolCall] = []

    for block in resp.content:
        if block.type == "text":
            collected_text.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input)))

    return LLMResponse(
        text="".join(collected_text),
        tool_calls=tool_calls,
        usage=Usage(
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        ),
        stop_reason=resp.stop_reason,
    )


# ---------------------------------------------------------------------------
# OpenAI-compat pure conversion functions
# ---------------------------------------------------------------------------


def _safe_json(s: str | None) -> dict[str, Any]:
    """Parse a JSON string defensively; returns {} for None, empty, or malformed input."""
    if not s:
        return {}
    try:
        result = json.loads(s)
        if isinstance(result, dict):
            return result
        return {}
    except json.JSONDecodeError:
        return {}


def to_openai_messages(system: str, history: list[Turn]) -> list[dict[str, Any]]:
    """Serialise a system prompt + history into OpenAI chat completions format."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]

    for turn in history:
        if turn.role == "user":
            messages.append({"role": "user", "content": turn.text})

        elif turn.role == "assistant":
            if turn.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": turn.text or None,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.input),
                                },
                            }
                            for tc in turn.tool_calls
                        ],
                    }
                )
            else:
                messages.append({"role": "assistant", "content": turn.text})

        elif turn.role == "tool":
            for tr in turn.tool_results:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tr.call_id,
                        "content": tr.content,
                    }
                )

    return messages


def to_openai_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Serialise ToolSpec list into OpenAI function tool definitions."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


def parse_openai_response(resp: Any) -> LLMResponse:
    """Parse a raw OpenAI chat completions response into an LLMResponse."""
    msg = resp.choices[0].message
    text: str = msg.content or ""

    tool_calls: list[ToolCall] = []
    for tc in msg.tool_calls or []:
        tool_calls.append(
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                input=_safe_json(tc.function.arguments),
            )
        )

    return LLMResponse(
        text=text,
        tool_calls=tool_calls,
        usage=Usage(
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
        ),
        stop_reason=resp.choices[0].finish_reason,
    )


# ---------------------------------------------------------------------------
# Backend abstract base + concrete implementations
# ---------------------------------------------------------------------------


class LLMBackend(ABC):
    """Abstract base for LLM backends."""

    model: str

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        history: list[Turn],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResponse: ...


class AnthropicBackend(LLMBackend):
    """Thin wrapper around the Anthropic Python SDK."""

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        *,
        system: str,
        history: list[Turn],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "messages": to_anthropic_messages(history),
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = to_anthropic_tools(tools)
        resp = self._client.messages.create(**kwargs)
        return parse_anthropic_response(resp)


class OpenAICompatBackend(LLMBackend):
    """Thin wrapper around the OpenAI Python SDK for OpenAI-compatible providers."""

    def __init__(self, model: str, api_key: str, base_url: str) -> None:
        self.model = model
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

    def complete(
        self,
        *,
        system: str,
        history: list[Turn],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": to_openai_messages(system, history),
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
        resp = self._client.chat.completions.create(**kwargs)
        return parse_openai_response(resp)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_backend() -> LLMBackend:
    """Construct an LLMBackend from environment variables.

    LLM_PROVIDER  default "gemini"  — "anthropic" | "gemini" | "groq"
    LLM_MODEL     default "gemini-2.5-flash"
    """
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("anthropic backend requires ANTHROPIC_API_KEY")
        return AnthropicBackend(model=model, api_key=api_key)

    if provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("gemini backend requires GEMINI_API_KEY")
        return OpenAICompatBackend(model=model, api_key=api_key, base_url=GEMINI_BASE_URL)

    if provider == "groq":
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("groq backend requires GROQ_API_KEY")
        return OpenAICompatBackend(model=model, api_key=api_key, base_url=GROQ_BASE_URL)

    raise ValueError(f"Unknown LLM_PROVIDER {provider!r}. Must be one of: anthropic, gemini, groq")
