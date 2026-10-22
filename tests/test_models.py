import pytest

from llm_dashboard.services.process import CommandResult

OLLAMA_LIST = """NAME             ID            SIZE     MODIFIED
llama3:8b        365c0bd3c000  4.7 GB   2 days ago
mistral:latest   f974a74358d6  4.1 GB   3 weeks ago
"""


def test_mock_mode_pull_then_list(client, runner):
    assert client.get("/api/models").json() == {"models": []}
    resp = client.post("/api/models/pull", json={"name": "llama3:8b"})
    assert resp.status_code == 200
    assert resp.json() == {"name": "llama3:8b", "status": "pulled (mock)"}
    assert client.get("/api/models").json() == {"models": [{"name": "llama3:8b"}]}
    assert runner.calls == []  # the CLI is never touched in mock mode


def test_mock_pull_is_idempotent(client):
    for _ in range(2):
        client.post("/api/models/pull", json={"name": "phi3"})
    assert client.get("/api/models").json()["models"] == [{"name": "phi3"}]


def test_live_pull_invokes_cli(make_client, make_config, runner):
    live = make_client(make_config(mock_mode=False, model_cli="ollama"))
    resp = live.post("/api/models/pull", json={"name": "library/llama3:8b"})
    assert resp.json() == {"name": "library/llama3:8b", "status": "pulled"}
    assert runner.calls == [["ollama", "pull", "library/llama3:8b"]]


def test_live_list_parses_cli_table(make_client, make_config, runner):
    runner.result = CommandResult(0, OLLAMA_LIST, "")
    live = make_client(make_config(mock_mode=False))
    names = [m["name"] for m in live.get("/api/models").json()["models"]]
    assert names == ["llama3:8b", "mistral:latest"]
    assert runner.calls == [["ollama", "list"]]


def test_live_cli_failure_maps_to_502(make_client, make_config, runner):
    runner.result = CommandResult(1, "", "pull model manifest: file does not exist")
    live = make_client(make_config(mock_mode=False))
    resp = live.post("/api/models/pull", json={"name": "ghost"})
    assert resp.status_code == 502
    assert "file does not exist" in resp.json()["detail"]
    assert live.get("/api/models").status_code == 502


@pytest.mark.parametrize("name", ["-rf", "a b", "x;y", "$(id)", "a/../b", "", "x" * 129])
def test_pull_rejects_invalid_names(client, runner, name):
    assert client.post("/api/models/pull", json={"name": name}).status_code == 422
    assert runner.calls == []
