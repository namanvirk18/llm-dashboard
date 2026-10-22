from typing import Annotated

from fastapi import Depends, Request

from llm_dashboard.config import Config
from llm_dashboard.services.models import ModelService
from llm_dashboard.services.plugins import PluginService
from llm_dashboard.services.settings import SettingsStore


def _config(request: Request) -> Config:
    return request.app.state.config


def _plugins(request: Request) -> PluginService:
    return request.app.state.plugin_service


def _models(request: Request) -> ModelService:
    return request.app.state.model_service


def _settings(request: Request) -> SettingsStore:
    return request.app.state.settings_store


ConfigDep = Annotated[Config, Depends(_config)]
PluginServiceDep = Annotated[PluginService, Depends(_plugins)]
ModelServiceDep = Annotated[ModelService, Depends(_models)]
SettingsStoreDep = Annotated[SettingsStore, Depends(_settings)]
