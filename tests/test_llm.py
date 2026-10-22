import json

import httpx
import pytest

from llm_dashboard.agent.llm import (
    AnthropicClient,
    LLMReply,
    MockLLM,
    OpenAICompatibleClient,
    ToolCall,
    create_llm_client,
)
from llm_dashboard.agent.loop import Agent
from llm_dashboard.agent.tools import TOOL_SPECS, ToolBox
from llm_dashboard.errors import ConfigurationError, UpstreamError
from llm_dashboard.services.settings import StoredSettings

CALL = ToolCall("call_1", "read_file", {"path": "a.txt"})
HISTORY = [
    {"role": "user", "content": "Summarise this URL or workspace file: a.txt"},
    {"role": "assistant", "content": "", "tool_calls": [CALL]},
    {"role": "tool", "tool_call_id": "call_1", "content": "file text"},
]


def capture(response_json, status=200):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        seen["body"] = json.loads(request.content)
        return httpx.Response(status, json=response_json)

    return seen, httpx.MockTransport(handler)


def test_openai_client_round_trip():
    seen, transport = capture({"choices": [{"message": {"content": None, "tool_calls": [
        {"id": "c9", "function": {"name": "read_file", "arguments": '{"path": "b.txt"}'}}]}}]})
    client = OpenAICompatibleClient("http://llm.test/v1", "sk-1", "gpt-x", transport)
    reply = client.complete("sys", HISTORY, TOOL_SPECS)

    assert reply.tool_calls == (ToolCall("c9", "read_file", {"path": "b.txt"}),)
    assert seen["request"].url == "http://llm.test/v1/chat/completions"
    assert seen["request"].headers["authorization"] == "Bearer sk-1"
    messages = seen["body"]["messages"]
    assert messages[0] == {"role": "system", "content": "sys"}
    assert messages[2]["tool_calls"][0]["function"]["arguments"] == '{"path": "a.txt"}'
    assert messages[3] == HISTORY[2]


def test_openai_client_tolerates_malformed_arguments():
    _, transport = capture({"choices": [{"message": {"tool_calls": [
        {"id": "c", "function": {"name": "read_file", "arguments": "{oops"}}]}}]})
    reply = OpenAICompatibleClient("http://llm.test", "", "m", transport).complete("s", HISTORY[:1], [])
    assert reply.tool_calls[0].arguments == {}


def test_anthropic_client_round_trip():
    seen, transport = capture({"content": [
        {"type": "text", "text": "Looking."},
        {"type": "tool_use", "id": "tu1", "name": "fetch_page", "input": {"url": "https://x.test"}},
    ]})
    reply = AnthropicClient("http://anthropic.test", "key-1", "claude-x", transport).complete(
        "sys", HISTORY, TOOL_SPECS
    )

    assert reply == LLMReply("Looking.", (ToolCall("tu1", "fetch_page", {"url": "https://x.test"}),))
    assert seen["request"].url == "http://anthropic.test/v1/messages"
    assert seen["request"].headers["x-api-key"] == "key-1"
    assert seen["body"]["system"] == "sys"
    assert seen["body"]["tools"][0]["input_schema"] == TOOL_SPECS[0]["parameters"]
    assert seen["body"]["messages"][1]["content"][0]["type"] == "tool_use"
    assert seen["body"]["messages"][2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "file text"}],
    }


@pytest.mark.parametrize("cls", [OpenAICompatibleClient, AnthropicClient])
def test_provider_errors_become_upstream_errors(cls):
    _, transport = capture({"error": "nope"}, status=500)
    with pytest.raises(UpstreamError, match="HTTP 500"):
        cls("http://x.test", "k", "m", transport).complete("s", HISTORY[:1], [])
    _, transport = capture({"unexpected": True})
    with pytest.raises(UpstreamError, match="unexpected response"):
        cls("http://x.test", "k", "m", transport).complete("s", HISTORY[:1], [])


def test_factory_selects_client(config, make_config):
    assert isinstance(create_llm_client(config, StoredSettings()), MockLLM)
    live = make_config(mock_mode=False)
    assert isinstance(
        create_llm_client(live, StoredSettings(provider="ollama", model="m")), OpenAICompatibleClient
    )
    assert isinstance(
        create_llm_client(live, StoredSettings(provider="anthropic", model="m", api_key="k")),
        AnthropicClient,
    )


def test_factory_requires_model_and_key(make_config):
    live = make_config(mock_mode=False)
    with pytest.raises(ConfigurationError, match="model"):
        create_llm_client(live, StoredSettings())
    with pytest.raises(ConfigurationError, match="API key"):
        create_llm_client(live, StoredSettings(provider="openai", model="m"))


def test_agent_gives_up_after_max_steps(tmp_path):
    class Looping:
        def complete(self, system, messages, tools):
            return LLMReply(tool_calls=(CALL,))

    with pytest.raises(UpstreamError, match="did not finish"):
        Agent(Looping(), ToolBox(tmp_path), max_steps=3).summarise("a.txt")


def test_agent_rejects_empty_summary(tmp_path):
    class Silent:
        def complete(self, system, messages, tools):
            return LLMReply(text="  ")

    with pytest.raises(UpstreamError, match="empty"):
        Agent(Silent(), ToolBox(tmp_path)).summarise("a.txt")
