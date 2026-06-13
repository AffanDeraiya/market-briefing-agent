"""Tests for src/llm.py — pure conversion functions and factory.

All tests are fully offline: no network, no real API keys required.
Fake SDK responses are built with types.SimpleNamespace.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from src.llm import (
    GEMINI_BASE_URL,
    AnthropicBackend,
    LLMResponse,
    OpenAICompatBackend,
    ToolCall,
    ToolResult,
    ToolSpec,
    Turn,
    Usage,
    _safe_json,
    get_backend,
    parse_anthropic_response,
    parse_openai_response,
    to_anthropic_messages,
    to_anthropic_tools,
    to_openai_messages,
    to_openai_tools,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TOOL_SPEC = ToolSpec(
    name="get_price_history",
    description="Fetch OHLCV price history for a ticker.",
    input_schema={
        "type": "object",
        "properties": {"ticker": {"type": "string"}, "period": {"type": "string"}},
        "required": ["ticker"],
    },
)


def _four_turn_history() -> list[Turn]:
    """Returns a 4-turn history: user → assistant(text+tool_call) → tool → assistant(text)."""
    return [
        Turn(role="user", text="What is the price history for AAPL?"),
        Turn(
            role="assistant",
            text="Let me look that up.",
            tool_calls=[ToolCall(id="tc_001", name="get_price_history", input={"ticker": "AAPL"})],
        ),
        Turn(
            role="tool",
            tool_results=[
                ToolResult(
                    call_id="tc_001",
                    name="get_price_history",
                    content='{"latest_close": 185.5, "change_pct": 1.2}',
                )
            ],
        ),
        Turn(role="assistant", text="AAPL closed at $185.50."),
    ]


# ---------------------------------------------------------------------------
# to_anthropic_messages
# ---------------------------------------------------------------------------


class TestToAnthropicMessages:
    def test_full_four_turn_history(self) -> None:
        history = _four_turn_history()
        msgs = to_anthropic_messages(history)

        assert len(msgs) == 4

        # Turn 0: user
        assert msgs[0] == {"role": "user", "content": "What is the price history for AAPL?"}

        # Turn 1: assistant with text block + tool_use block
        assert msgs[1]["role"] == "assistant"
        content = msgs[1]["content"]
        assert isinstance(content, list)
        assert len(content) == 2

        text_block = content[0]
        assert text_block["type"] == "text"
        assert text_block["text"] == "Let me look that up."

        tool_block = content[1]
        assert tool_block["type"] == "tool_use"
        assert tool_block["id"] == "tc_001"
        assert tool_block["name"] == "get_price_history"
        assert tool_block["input"] == {"ticker": "AAPL"}

        # Turn 2: tool result (role "user" with content blocks)
        assert msgs[2]["role"] == "user"
        tool_result_content = msgs[2]["content"]
        assert isinstance(tool_result_content, list)
        assert len(tool_result_content) == 1
        tr_block = tool_result_content[0]
        assert tr_block["type"] == "tool_result"
        assert tr_block["tool_use_id"] == "tc_001"
        assert tr_block["content"] == '{"latest_close": 185.5, "change_pct": 1.2}'
        assert tr_block["is_error"] is False

        # Turn 3: assistant final text
        assert msgs[3]["role"] == "assistant"
        final_content = msgs[3]["content"]
        assert isinstance(final_content, list)
        assert len(final_content) == 1
        assert final_content[0]["type"] == "text"
        assert final_content[0]["text"] == "AAPL closed at $185.50."

    def test_assistant_turn_no_text_no_text_block(self) -> None:
        history = [
            Turn(
                role="assistant",
                text="",
                tool_calls=[ToolCall(id="t1", name="foo", input={})],
            )
        ]
        msgs = to_anthropic_messages(history)
        content = msgs[0]["content"]
        assert all(b["type"] != "text" for b in content)
        assert len(content) == 1

    def test_tool_turn_error_flag_propagated(self) -> None:
        history = [
            Turn(
                role="tool",
                tool_results=[
                    ToolResult(
                        call_id="t1",
                        name="foo",
                        content="timeout",
                        is_error=True,
                    )
                ],
            )
        ]
        msgs = to_anthropic_messages(history)
        assert msgs[0]["content"][0]["is_error"] is True


# ---------------------------------------------------------------------------
# to_openai_messages
# ---------------------------------------------------------------------------


class TestToOpenaiMessages:
    def test_full_four_turn_history(self) -> None:
        history = _four_turn_history()
        msgs = to_openai_messages("You are a helpful assistant.", history)

        # System message is always first
        assert msgs[0] == {"role": "system", "content": "You are a helpful assistant."}
        assert len(msgs) == 5  # system + user + assistant(tool_call) + tool + assistant(final)

        # User message
        assert msgs[1] == {"role": "user", "content": "What is the price history for AAPL?"}

        # Assistant message with tool_calls
        asst_msg = msgs[2]
        assert asst_msg["role"] == "assistant"
        assert "tool_calls" in asst_msg
        tc_list = asst_msg["tool_calls"]
        assert len(tc_list) == 1
        tc = tc_list[0]
        assert tc["id"] == "tc_001"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "get_price_history"
        # arguments must be a JSON STRING
        args_str = tc["function"]["arguments"]
        assert isinstance(args_str, str)
        assert json.loads(args_str) == {"ticker": "AAPL"}

        # Tool message
        tool_msg = msgs[3]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "tc_001"
        assert tool_msg["content"] == '{"latest_close": 185.5, "change_pct": 1.2}'

        # Final assistant message — NO tool_calls key
        final_msg = msgs[4]
        assert final_msg["role"] == "assistant"
        assert final_msg["content"] == "AAPL closed at $185.50."
        assert "tool_calls" not in final_msg

    def test_assistant_no_tool_calls_omits_key(self) -> None:
        history = [Turn(role="assistant", text="Hello!")]
        msgs = to_openai_messages("sys", history)
        asst = msgs[1]
        assert "tool_calls" not in asst
        assert asst["content"] == "Hello!"

    def test_multiple_tool_results_become_separate_messages(self) -> None:
        history = [
            Turn(
                role="tool",
                tool_results=[
                    ToolResult(call_id="t1", name="a", content="result_a"),
                    ToolResult(call_id="t2", name="b", content="result_b"),
                ],
            )
        ]
        msgs = to_openai_messages("sys", history)
        # system + 2 tool messages
        assert len(msgs) == 3
        assert msgs[1]["role"] == "tool"
        assert msgs[1]["tool_call_id"] == "t1"
        assert msgs[2]["role"] == "tool"
        assert msgs[2]["tool_call_id"] == "t2"


# ---------------------------------------------------------------------------
# parse_anthropic_response
# ---------------------------------------------------------------------------


def _fake_anthropic_resp(
    blocks: list[Any],
    input_tokens: int = 10,
    output_tokens: int = 5,
    stop_reason: str = "tool_use",
) -> Any:
    return SimpleNamespace(
        content=blocks,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        stop_reason=stop_reason,
    )


class TestParseAnthropicResponse:
    def test_text_and_tool_use_block(self) -> None:
        resp = _fake_anthropic_resp(
            blocks=[
                SimpleNamespace(type="text", text="hi"),
                SimpleNamespace(
                    type="tool_use",
                    id="t1",
                    name="get_price_history",
                    input={"ticker": "AAPL"},
                ),
            ],
            input_tokens=10,
            output_tokens=5,
            stop_reason="tool_use",
        )
        result = parse_anthropic_response(resp)

        assert isinstance(result, LLMResponse)
        assert result.text == "hi"
        assert len(result.tool_calls) == 1
        tc = result.tool_calls[0]
        assert tc.id == "t1"
        assert tc.name == "get_price_history"
        assert tc.input == {"ticker": "AAPL"}
        assert result.wants_tools is True
        assert result.is_final is False
        assert result.usage == Usage(input_tokens=10, output_tokens=5)
        assert result.stop_reason == "tool_use"

    def test_text_only_is_final(self) -> None:
        resp = _fake_anthropic_resp(
            blocks=[SimpleNamespace(type="text", text="Done.")],
            stop_reason="end_turn",
        )
        result = parse_anthropic_response(resp)
        assert result.text == "Done."
        assert result.tool_calls == []
        assert result.is_final is True
        assert result.wants_tools is False

    def test_multiple_text_blocks_concatenated(self) -> None:
        resp = _fake_anthropic_resp(
            blocks=[
                SimpleNamespace(type="text", text="Hello "),
                SimpleNamespace(type="text", text="World"),
            ],
            stop_reason="end_turn",
        )
        result = parse_anthropic_response(resp)
        assert result.text == "Hello World"

    def test_unknown_block_type_ignored(self) -> None:
        resp = _fake_anthropic_resp(
            blocks=[
                SimpleNamespace(type="thinking", thinking="internal"),
                SimpleNamespace(type="text", text="answer"),
            ],
            stop_reason="end_turn",
        )
        result = parse_anthropic_response(resp)
        assert result.text == "answer"
        assert result.tool_calls == []


# ---------------------------------------------------------------------------
# parse_openai_response
# ---------------------------------------------------------------------------


def _fake_openai_resp(
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    prompt_tokens: int = 8,
    completion_tokens: int = 4,
    finish_reason: str = "stop",
) -> Any:
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=msg, finish_reason=finish_reason)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


class TestParseOpenaiResponse:
    def test_text_only_is_final(self) -> None:
        resp = _fake_openai_resp(content="done", tool_calls=None, finish_reason="stop")
        result = parse_openai_response(resp)

        assert result.text == "done"
        assert result.tool_calls == []
        assert result.is_final is True

    def test_tool_call_arguments_as_string(self) -> None:
        fake_tc = SimpleNamespace(
            id="tc_99",
            function=SimpleNamespace(name="get_price_history", arguments='{"ticker":"TSLA"}'),
        )
        resp = _fake_openai_resp(content=None, tool_calls=[fake_tc], finish_reason="tool_calls")
        result = parse_openai_response(resp)

        assert result.wants_tools is True
        assert len(result.tool_calls) == 1
        tc = result.tool_calls[0]
        assert tc.id == "tc_99"
        assert tc.name == "get_price_history"
        assert tc.input == {"ticker": "TSLA"}

    def test_usage_mapped_correctly(self) -> None:
        resp = _fake_openai_resp(
            content="ok", prompt_tokens=20, completion_tokens=10, finish_reason="stop"
        )
        result = parse_openai_response(resp)
        assert result.usage.input_tokens == 20
        assert result.usage.output_tokens == 10

    def test_stop_reason_propagated(self) -> None:
        resp = _fake_openai_resp(content="x", finish_reason="length")
        result = parse_openai_response(resp)
        assert result.stop_reason == "length"

    def test_null_content_becomes_empty_string(self) -> None:
        resp = _fake_openai_resp(content=None, tool_calls=None)
        result = parse_openai_response(resp)
        assert result.text == ""


# ---------------------------------------------------------------------------
# _safe_json
# ---------------------------------------------------------------------------


class TestSafeJson:
    def test_none_returns_empty_dict(self) -> None:
        assert _safe_json(None) == {}

    def test_empty_string_returns_empty_dict(self) -> None:
        assert _safe_json("") == {}

    def test_malformed_json_returns_empty_dict(self) -> None:
        assert _safe_json("{bad json") == {}

    def test_valid_json_object_parsed(self) -> None:
        assert _safe_json('{"a": 1}') == {"a": 1}

    def test_valid_nested_dict(self) -> None:
        result = _safe_json('{"ticker": "AAPL", "period": "1mo"}')
        assert result == {"ticker": "AAPL", "period": "1mo"}

    def test_json_array_returns_empty_dict(self) -> None:
        # We only handle dicts — arrays should fall back to {}
        assert _safe_json("[1, 2, 3]") == {}


# ---------------------------------------------------------------------------
# to_anthropic_tools / to_openai_tools
# ---------------------------------------------------------------------------


class TestToolSerialisation:
    def test_to_anthropic_tools(self) -> None:
        result = to_anthropic_tools([TOOL_SPEC])
        assert len(result) == 1
        t = result[0]
        assert t["name"] == "get_price_history"
        assert t["description"] == TOOL_SPEC.description
        assert t["input_schema"] == TOOL_SPEC.input_schema

    def test_to_openai_tools(self) -> None:
        result = to_openai_tools([TOOL_SPEC])
        assert len(result) == 1
        t = result[0]
        assert t["type"] == "function"
        assert t["function"]["name"] == "get_price_history"
        assert t["function"]["description"] == TOOL_SPEC.description
        assert t["function"]["parameters"] == TOOL_SPEC.input_schema

    def test_empty_tool_list(self) -> None:
        assert to_anthropic_tools([]) == []
        assert to_openai_tools([]) == []


# ---------------------------------------------------------------------------
# get_backend factory
# ---------------------------------------------------------------------------


class TestGetBackend:
    def test_gemini_with_key_returns_openai_compat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("LLM_MODEL", "gemini-2.5-flash")
        monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")

        backend = get_backend()

        assert isinstance(backend, OpenAICompatBackend)
        assert backend.model == "gemini-2.5-flash"
        assert str(backend._client.base_url) == GEMINI_BASE_URL

    def test_gemini_without_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            get_backend()

    def test_groq_with_key_returns_openai_compat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.setenv("LLM_MODEL", "llama-3.1-8b")
        monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")

        backend = get_backend()

        assert isinstance(backend, OpenAICompatBackend)
        assert backend.model == "llama-3.1-8b"

    def test_anthropic_with_key_returns_anthropic_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")

        backend = get_backend()

        assert isinstance(backend, AnthropicBackend)
        assert backend.model == "claude-haiku-4-5"

    def test_anthropic_without_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            get_backend()

    def test_unknown_provider_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "totally_unknown_provider")

        with pytest.raises(ValueError, match="totally_unknown_provider"):
            get_backend()

    def test_default_provider_is_gemini(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "key123")

        backend = get_backend()

        assert isinstance(backend, OpenAICompatBackend)

    def test_default_model_is_gemini_flash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "key123")

        backend = get_backend()

        assert backend.model == "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# LLMResponse properties
# ---------------------------------------------------------------------------


class TestLLMResponseProperties:
    def test_wants_tools_true_when_tool_calls_present(self) -> None:
        resp = LLMResponse(
            text="",
            tool_calls=[ToolCall(id="t1", name="foo", input={})],
            usage=Usage(),
        )
        assert resp.wants_tools is True
        assert resp.is_final is False

    def test_is_final_true_when_no_tool_calls(self) -> None:
        resp = LLMResponse(text="done", tool_calls=[], usage=Usage())
        assert resp.is_final is True
        assert resp.wants_tools is False
