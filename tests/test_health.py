from llm_dashboard.config import Config


def test_health_reports_mock_mode(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "mock_mode": True}


def test_health_reports_live_mode(make_client, make_config):
    resp = make_client(make_config(mock_mode=False)).get("/api/health")
    assert resp.json()["mock_mode"] is False


def test_frontend_is_served_with_security_headers(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "LLM Dashboard" in resp.text
    assert resp.headers["content-security-policy"] == "default-src 'self'"
    assert client.get("/app.js").status_code == 200


def test_config_from_env(tmp_path):
    cfg = Config.from_env(
        {
            "LLM_DASH_MOCK": "1",
            "LLM_DASH_DATA_DIR": str(tmp_path / "d"),
            "LLM_DASH_WORKSPACE": str(tmp_path / "w"),
            "LLM_DASH_MODEL_CLI": "mycli",
        }
    )
    assert cfg.mock_mode and cfg.model_cli == "mycli"
    assert Config.from_env({"LLM_DASH_DATA_DIR": str(tmp_path)}).mock_mode is False


def test_data_dir_inside_workspace_is_refused(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        Config(data_dir=tmp_path / "ws" / "data", workspace_dir=tmp_path / "ws")
