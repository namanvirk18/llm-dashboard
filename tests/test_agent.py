import httpx

from conftest import web_client

PAGE = "<html><head><title>T</title><script>evil()</script></head><body><p>Hello world. Second one.</p></body></html>"


def ok_html(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text=PAGE, headers={"content-type": "text/html; charset=utf-8"})


def test_workspace_listing(client, config):
    (config.workspace_dir / "sub").mkdir()
    (config.workspace_dir / "a.txt").write_text("a")
    (config.workspace_dir / "sub" / "b.md").write_text("b")
    assert client.get("/api/agent/workspace").json() == {"files": ["a.txt", "sub/b.md"]}


def test_summarize_workspace_file(client, config):
    (config.workspace_dir / "notes.txt").write_text("Cats purr. Dogs bark. Fish swim. Birds fly.")
    resp = client.post("/api/agent/summarize", json={"target": "notes.txt"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"] == "[mock summary] Cats purr. Dogs bark. Fish swim."
    assert [s["tool"] for s in body["steps"]] == ["read_file"]
    assert body["steps"][0]["arguments"] == {"path": "notes.txt"}


def test_summarize_url(make_client, config, public_dns):
    app = make_client(config, http_client=web_client(ok_html))
    resp = app.post("/api/agent/summarize", json={"target": "https://example.com/page"})
    body = resp.json()
    assert body["summary"] == "[mock summary] T Hello world. Second one."
    assert body["steps"][0]["tool"] == "fetch_page"
    assert "evil()" not in body["steps"][0]["output"]


def test_missing_file_is_reported_in_summary(client):
    resp = client.post("/api/agent/summarize", json={"target": "nope.txt"})
    assert resp.status_code == 200
    assert "Could not read the target" in resp.json()["summary"]
    assert resp.json()["steps"][0]["output"] == "error: file not found"


def test_path_traversal_is_blocked(client, config):
    (config.workspace_dir.parent / "secret.txt").write_text("TOP SECRET")
    resp = client.post("/api/agent/summarize", json={"target": "../secret.txt"})
    assert "TOP SECRET" not in resp.text
    assert resp.json()["steps"][0]["output"] == "error: path is outside the workspace"


def test_private_url_is_blocked(client):
    resp = client.post("/api/agent/summarize", json={"target": "http://127.0.0.1:8000/api/settings"})
    assert resp.json()["steps"][0]["output"] == "error: refusing to fetch a non-public address"


def test_invalid_targets_are_rejected(client):
    assert client.post("/api/agent/summarize", json={"target": ""}).status_code == 422
    assert client.post("/api/agent/summarize", json={"target": "a\nb"}).status_code == 422
    assert client.post("/api/agent/summarize", json={"target": "x" * 3000}).status_code == 422
    assert client.post("/api/agent/summarize", json={}).status_code == 422


def test_live_mode_requires_a_configured_model(make_client, make_config):
    live = make_client(make_config(mock_mode=False))
    resp = live.post("/api/agent/summarize", json={"target": "sample.txt"})
    assert resp.status_code == 409
    assert "no model configured" in resp.json()["detail"]


def test_live_mode_uses_configured_provider(make_client, make_config, config):
    seen = {}

    def provider(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "A real summary."}}]})

    live_config = make_config(mock_mode=False)
    live = make_client(live_config, llm_transport=httpx.MockTransport(provider))
    live.put("/api/settings", json={"provider": "ollama", "model": "llama3"})
    resp = live.post("/api/agent/summarize", json={"target": "sample.txt"})
    assert resp.json() == {"summary": "A real summary.", "steps": []}
    assert seen["url"] == "http://127.0.0.1:11434/v1/chat/completions"
