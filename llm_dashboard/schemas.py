from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from llm_dashboard.services.settings import Channel, Provider


class OutModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- plugins ---------------------------------------------------------------


class PluginOut(OutModel):
    name: str
    version: str
    summary: str = ""


class PluginList(OutModel):
    plugins: list[PluginOut]


class PluginInstallRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    version: str | None = Field(default=None, max_length=50)


# --- models ----------------------------------------------------------------


class ModelOut(OutModel):
    name: str


class ModelList(OutModel):
    models: list[ModelOut]


class ModelPullRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class ModelPullOut(OutModel):
    name: str
    status: str


# --- settings --------------------------------------------------------------


class SettingsOut(BaseModel):
    provider: Provider
    model: str
    base_url: str
    api_key_set: bool
    update_channel: Channel


class SettingsUpdate(BaseModel):
    """Partial update: omitted fields are unchanged; null clears string fields."""

    model_config = ConfigDict(extra="forbid")

    provider: Provider | None = None
    model: str | None = Field(default=None, max_length=200)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    update_channel: Channel | None = None


# --- agent -----------------------------------------------------------------


class AgentRequest(BaseModel):
    target: str = Field(min_length=1, max_length=2048)

    @field_validator("target")
    @classmethod
    def _single_line(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(ch) < 32 for ch in value):
            raise ValueError("target must be a single line of printable text")
        return value


class AgentStepOut(OutModel):
    tool: str
    arguments: dict[str, Any]
    output: str


class AgentRunOut(OutModel):
    summary: str
    steps: list[AgentStepOut]


class WorkspaceFiles(OutModel):
    files: list[str]
