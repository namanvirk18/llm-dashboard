"""LLM clients behind one small interface, plus a deterministic mock."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from llm_dashboard.config import Config
from llm_dashboard.errors import ConfigurationError, UpstreamError
from llm_dashboard.services.settings import StoredSettings

TASK_PREFIX = "Summarise this URL or workspace file: "

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "anthropic": "https://api.anthropic.com",
}

Message = dict[str, Any]
REQUEST_TIMEOUT = 60.0


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMReply:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


class LLMClient(Protocol):
    def complete(
        self, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMReply: ...


# --- mock ------------------------------------------------------------------


class MockLLM:
    """Deterministic stand-in: calls the right tool once, then summarises its output."""

    def complete(
        self, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMReply:
        last = messages[-1]
        if last["role"] == "tool":
            return LLMReply(text=_mock_summary(last["content"]))
        target = messages[0]["content"].removeprefix(TASK_PREFIX).strip()
        if target.lower().startswith(("http://", "https://")):
            call = ToolCall("mock-call-1", "fetch_page", {"url": target})
        else:
            call = ToolCall("mock-call-1", "read_file", {"path": target})
        return LLMReply(tool_calls=(call,))


def _mock_summary(tool_output: str) -> str:
    if tool_output.startswith("error:"):
        return f"[mock summary] Could not read the target ({tool_output})."
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(tool_output.split()))
    return "[mock summary] " + " ".join(sentences[:3])[:500]


# --- real providers --------------------------------------------------------


def _post_json(
    transport: httpx.BaseTransport | None,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        with httpx.Client(transport=transport, timeout=REQUEST_TIMEOUT) as client:
            resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise UpstreamError(f"provider returned HTTP {resp.status_code}")
        return resp.json()
    except httpx.HTTPError as exc:
        raise UpstreamError(f"provider request failed ({type(exc).__name__})") from exc
    except ValueError as exc:
        raise UpstreamError("provider returned invalid JSON") from exc


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


class OpenAICompatibleClient:
    """Chat Completions API; also serves Ollama's /v1 endpoint."""

    def __init__(
        self, base_url: str, api_key: str, model: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:  # fmt: skip
        self._url = f"{base_url}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._model = model
        self._transport = transport

    def complete(
        self, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMReply:
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *map(self._convert, messages)],
            "tools": [{"type": "function", "function": spec} for spec in tools],
        }
        data = _post_json(self._transport, self._url, self._headers, payload)
        try:
            message = data["choices"][0]["message"]
            calls = tuple(
                ToolCall(c["id"], c["function"]["name"], _parse_arguments(c["function"]["arguments"]))
                for c in message.get("tool_calls") or []
            )
            return LLMReply(text=message.get("content") or "", tool_calls=calls)
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamError("unexpected response from provider") from exc

    @staticmethod
    def _convert(message: Message) -> Message:
        if message["role"] == "assistant" and message.get("tool_calls"):
            return {
                "role": "assistant",
                "content": message["content"] or None,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                    }
                    for c in message["tool_calls"]
                ],
            }
        return message


class AnthropicClient:
    """Anthropic Messages API."""

    def __init__(
        self, base_url: str, api_key: str, model: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:  # fmt: skip
        self._url = f"{base_url}/v1/messages"
        self._headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        self._model = model
        self._transport = transport

    def complete(
        self, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMReply:
        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "system": system,
            "messages": self._convert(messages),
            "tools": [
                {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                for t in tools
            ],
        }
        data = _post_json(self._transport, self._url, self._headers, payload)
        try:
            blocks = data["content"]
            text = "".join(b["text"] for b in blocks if b["type"] == "text")
            calls = tuple(
                ToolCall(b["id"], b["name"], _parse_arguments(b["input"]))
                for b in blocks
                if b["type"] == "tool_use"
            )
            return LLMReply(text=text, tool_calls=calls)
        except (KeyError, TypeError) as exc:
            raise UpstreamError("unexpected response from provider") from exc

    @staticmethod
    def _convert(messages: list[Message]) -> list[Message]:
        out: list[Message] = []
        for m in messages:
            if m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)  # results of one turn share a user message
                else:
                    out.append({"role": "user", "content": [block]})
            elif m["role"] == "assistant":
                blocks: list[dict[str, Any]] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                blocks += [
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                    for c in m.get("tool_calls", [])
                ]
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": "user", "content": m["content"]})
        return out


def create_llm_client(
    config: Config, settings: StoredSettings, transport: httpx.BaseTransport | None = None
) -> LLMClient:
    if config.mock_mode:
        return MockLLM()
    if not settings.model:
        raise ConfigurationError("no model configured; choose one in Settings")
    base_url = settings.base_url or DEFAULT_BASE_URLS[settings.provider]
    if settings.provider != "ollama" and not settings.api_key:
        raise ConfigurationError(f"no API key configured for {settings.provider}")
    if settings.provider == "anthropic":
        return AnthropicClient(base_url, settings.api_key, settings.model, transport)
    return OpenAICompatibleClient(base_url, settings.api_key, settings.model, transport)
