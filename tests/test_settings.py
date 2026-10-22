import json
import stat

import pytest


def test_defaults(client):
    assert client.get("/api/settings").json() == {
        "provider": "ollama",
        "model": "",
        "base_url": "",
        "api_key_set": False,
        "update_channel": "stable",
    }


def test_update_is_partial_and_persisted(client, make_client, config):
    resp = client.put("/api/settings", json={"provider": "openai", "model": "gpt-x"})
    assert resp.status_code == 200
    client.put("/api/settings", json={"update_channel": "beta"})
    body = client.get("/api/settings").json()
    assert (body["provider"], body["model"], body["update_channel"]) == ("openai", "gpt-x", "beta")
    # A fresh app on the same data dir sees the same values.
    assert make_client(config).get("/api/settings").json() == body


def test_api_key_is_never_returned(client):
    resp = client.put("/api/settings", json={"api_key": "sk-secret-123"})
    assert resp.json()["api_key_set"] is True
    assert "sk-secret-123" not in client.get("/api/settings").text


def test_api_key_cleared_with_null(client):
    client.put("/api/settings", json={"api_key": "sk-secret-123"})
    assert client.put("/api/settings", json={"api_key": None}).json()["api_key_set"] is False


def test_omitted_api_key_is_kept(client):
    client.put("/api/settings", json={"api_key": "sk-secret-123"})
    assert client.put("/api/settings", json={"model": "m"}).json()["api_key_set"] is True


def test_settings_file_is_private(client, config):
    client.put("/api/settings", json={"api_key": "sk-secret-123"})
    mode = stat.S_IMODE(config.settings_path.stat().st_mode)
    assert mode == 0o600
    assert json.loads(config.settings_path.read_text())["api_key"] == "sk-secret-123"


def test_base_url_is_normalised(client):
    resp = client.put("/api/settings", json={"base_url": "http://localhost:1234/v1/"})
    assert resp.json()["base_url"] == "http://localhost:1234/v1"


@pytest.mark.parametrize(
    "payload",
    [
        {"provider": "bogus"},
        {"update_channel": "weekly"},
        {"update_channel": None},
        {"base_url": "ftp://example.com"},
        {"base_url": "not a url"},
        {"unknown_field": 1},
        {"model": "x" * 201},
    ],
)
def test_invalid_updates_are_rejected(client, payload):
    assert client.put("/api/settings", json=payload).status_code == 422
    assert client.get("/api/settings").json()["provider"] == "ollama"


def test_corrupt_settings_file_reports_conflict(client, config):
    config.settings_path.write_text("{not json")
    assert client.get("/api/settings").status_code == 409
