from __future__ import annotations

from collections.abc import Callable, Sequence

import httpx
import pytest
from fastapi.testclient import TestClient

from llm_dashboard.agent import tools
from llm_dashboard.config import Config
from llm_dashboard.main import create_app
from llm_dashboard.services.process import CommandResult


class FakeRunner:
    """Records argv instead of spawning processes; returns a configurable result."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.result = CommandResult(0, "", "")

    def __call__(self, argv: Sequence[str], timeout: int) -> CommandResult:
        self.calls.append(list(argv))
        return self.result


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
def make_config(tmp_path) -> Callable[..., Config]:
    def factory(**overrides) -> Config:
        values = {
            "data_dir": tmp_path / "data",
            "workspace_dir": tmp_path / "workspace",
            "mock_mode": True,
        }
        return Config(**{**values, **overrides})

    return factory


@pytest.fixture
def config(make_config) -> Config:
    return make_config()


@pytest.fixture
def make_client(runner) -> Callable[..., TestClient]:
    def factory(config: Config, **kwargs) -> TestClient:
        kwargs.setdefault("plugin_runner", runner)
        kwargs.setdefault("model_runner", runner)
        return TestClient(create_app(config, **kwargs), base_url="http://127.0.0.1")

    return factory


@pytest.fixture
def client(make_client, config) -> TestClient:
    """App in mock mode."""
    return make_client(config)


@pytest.fixture
def public_dns(monkeypatch) -> None:
    """Resolve every hostname except literal loopback to a public address."""
    monkeypatch.setattr(
        tools, "_resolve_host", lambda host, port: [host if host[0].isdigit() else "93.184.216.34"]
    )


def web_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))
