from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    data_dir: Path
    workspace_dir: Path
    mock_mode: bool = False
    model_cli: str = "ollama"
    command_timeout: int = 1800

    def __post_init__(self) -> None:
        # The agent can read anything under the workspace, so keep secrets out of it.
        data = self.data_dir.resolve()
        workspace = self.workspace_dir.resolve()
        if data == workspace or data.is_relative_to(workspace):
            raise ValueError("data_dir must not be inside the agent workspace")

    @property
    def plugins_dir(self) -> Path:
        return self.data_dir / "plugins"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def mock_models_path(self) -> Path:
        return self.data_dir / "mock_models.json"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        env = os.environ if env is None else env
        return cls(
            data_dir=Path(env.get("LLM_DASH_DATA_DIR", "~/.llm-dashboard")).expanduser(),
            workspace_dir=Path(env.get("LLM_DASH_WORKSPACE", "workspace")).expanduser(),
            mock_mode=env.get("LLM_DASH_MOCK", "").strip().lower() in _TRUTHY,
            model_cli=env.get("LLM_DASH_MODEL_CLI", "ollama"),
        )
