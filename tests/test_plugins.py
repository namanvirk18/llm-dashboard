import sys

import pytest

from llm_dashboard.services.process import CommandResult


def add_installed_plugin(config, name="demo-plugin", version="1.2.3", summary="Demo plugin"):
    dist = config.plugins_dir / f"{name.replace('-', '_')}-{version}.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nSummary: {summary}\n"
    )


def test_list_plugins_empty(client):
    assert client.get("/api/plugins").json() == {"plugins": []}


def test_list_plugins_reads_installed_distributions(client, config):
    add_installed_plugin(config)
    add_installed_plugin(config, name="alpha", version="0.1", summary="")
    plugins = client.get("/api/plugins").json()["plugins"]
    assert [p["name"] for p in plugins] == ["alpha", "demo-plugin"]
    assert plugins[1] == {"name": "demo-plugin", "version": "1.2.3", "summary": "Demo plugin"}


def test_install_by_name(client, runner, config):
    resp = client.post("/api/plugins", json={"name": "demo-plugin"})
    assert resp.status_code == 201
    argv = runner.calls[0]
    assert argv[:4] == [sys.executable, "-m", "pip", "install"]
    assert argv[argv.index("--target") + 1] == str(config.plugins_dir)
    assert argv[-1] == "demo-plugin"
    assert resp.json()["name"] == "demo-plugin"


def test_install_pins_version_and_reports_installed_metadata(client, runner, config):
    add_installed_plugin(config, version="2.0.0")
    resp = client.post("/api/plugins", json={"name": "Demo_Plugin", "version": "2.0.0"})
    assert runner.calls[0][-1] == "Demo_Plugin==2.0.0"
    assert resp.json() == {"name": "demo-plugin", "version": "2.0.0", "summary": "Demo plugin"}


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "-e git+https://example.com/x.git"},
        {"name": "demo; rm -rf /"},
        {"name": "--index-url=http://evil"},
        {"name": "../escape"},
        {"name": "demo plugin"},
        {"name": "demo", "version": "1.0 --index-url http://evil"},
        {"name": "demo", "version": "1.0;ls"},
        {"name": ""},
    ],
)
def test_install_rejects_unsafe_input(client, runner, payload):
    assert client.post("/api/plugins", json=payload).status_code == 422
    assert runner.calls == []


def test_install_failure_maps_to_502(client, runner):
    runner.result = CommandResult(1, "", "ERROR: No matching distribution found for nope")
    resp = client.post("/api/plugins", json={"name": "nope"})
    assert resp.status_code == 502
    assert "No matching distribution" in resp.json()["detail"]
