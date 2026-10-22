import os
import sys
from unittest.mock import Mock

import pytest

from llm_dashboard.errors import InvalidInputError
from llm_dashboard.services.process import CommandResult
from llm_dashboard.services.updater import self_update


@pytest.fixture
def pip_run(monkeypatch):
    run = Mock(return_value=CommandResult(0, "installed", ""))
    monkeypatch.setattr("llm_dashboard.services.updater.subprocess.run", run)
    return run


@pytest.mark.parametrize(
    ("target", "canonical"),
    [
        ("0.2.0", "0.2.0"),
        (" v01.02.03-RC1 ", "1.2.3rc1"),
        ("1.2.post1", "1.2.post1"),
        ("1!2.0.dev2+Build-3", "1!2.0.dev2+build.3"),
    ],
)
@pytest.mark.parametrize("returncode", [0, 1])
def test_update_uses_canonical_version(client, pip_run, target, canonical, returncode):
    pip_run.return_value = CommandResult(returncode, "pip output", "pip diagnostics")
    response = client.post("/api/update", json={"target": target})
    assert response.status_code == 200
    pip_run.assert_called_once_with(
        [sys.executable, "-m", "pip", "install", "--upgrade", f"llm-dashboard=={canonical}"],
        capture_output=True,
        text=True,
    )
    assert response.json() == {
        "success": returncode == 0,
        "target": canonical,
        "stdout": "pip output",
        "stderr": "pip diagnostics",
    }


def test_update_rejects_local_project(client, pip_run, tmp_path):
    project = tmp_path / "untrusted-project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "untrusted-project"\nversion = "0.0.0"\n'
    )
    # pip normalizes away the package prefix before checking for a local project.
    target = "/../" + os.path.relpath(project)
    assert os.path.abspath(f"llm-dashboard=={target}") == str(project)
    assert client.post("/api/update", json={"target": target}).status_code == 422
    pip_run.assert_not_called()


@pytest.mark.parametrize(
    "target",
    [
        "../project",
        "/../../tmp/project",
        r"\..\project",
        "https://example.com/project.tar.gz",
        "1.0 @ https://example.com/project.whl",
        "1.0; python_version >= '3'",
        "1.0 --index-url https://example.com",
        "1.0,!=1.0.1",
        "1.0.*",
        ">=1.0",
        "latest",
        " ",
        "1.0\x00",
        123,
        True,
        ["1.0"],
        {"version": "1.0"},
    ],
)
def test_update_rejects_invalid_targets(client, pip_run, target):
    response = client.post("/api/update", json={"target": target})
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid target version"}
    pip_run.assert_not_called()


@pytest.mark.parametrize("target", ["/../project", None, 123, ""])
def test_service_rejects_invalid_targets(pip_run, target):
    with pytest.raises(InvalidInputError, match="invalid target version"):
        self_update(target)
    pip_run.assert_not_called()


@pytest.mark.parametrize("body", ["{", "[]", "null", '"1.0"', "123"])
def test_update_rejects_invalid_body(client, pip_run, body):
    assert client.post("/api/update", content=body).status_code == 400
    pip_run.assert_not_called()


@pytest.mark.parametrize("payload", [{}, {"target": None}, {"target": ""}])
def test_update_rejects_missing_target(client, pip_run, payload):
    assert client.post("/api/update", json=payload).status_code == 400
    pip_run.assert_not_called()
