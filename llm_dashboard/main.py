from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from llm_dashboard.config import Config
from llm_dashboard.errors import DashboardError
from llm_dashboard.routers import agent, health, models, plugins, settings, update
from llm_dashboard.services.models import ModelService
from llm_dashboard.services.plugins import PluginService
from llm_dashboard.services.process import Runner, run_command
from llm_dashboard.services.settings import SettingsStore

STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    config: Config | None = None,
    *,
    plugin_runner: Runner = run_command,
    model_runner: Runner = run_command,
    http_client: httpx.Client | None = None,
    llm_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    """Build the app. The keyword arguments are seams for tests."""
    config = config or Config.from_env()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.data_dir.chmod(0o700)
    config.workspace_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="LLM Dashboard", docs_url=None, redoc_url=None)
    app.state.config = config
    app.state.http_client = http_client
    app.state.llm_transport = llm_transport
    app.state.settings_store = SettingsStore(config.settings_path)
    app.state.plugin_service = PluginService(
        config.plugins_dir, plugin_runner, config.command_timeout
    )
    app.state.model_service = ModelService(
        cli=config.model_cli,
        runner=model_runner,
        timeout=config.command_timeout,
        mock=config.mock_mode,
        state_path=config.mock_models_path,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(DashboardError)
    async def dashboard_error_handler(request: Request, exc: DashboardError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    for module in (health, plugins, models, settings, agent, update):
        app.include_router(module.router)
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
