from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError, field_validator

from llm_dashboard.errors import ConfigurationError, InvalidInputError

Provider = Literal["openai", "anthropic", "ollama"]
Channel = Literal["stable", "beta", "nightly"]

_CLEARABLE = {"model", "base_url", "api_key"}


class StoredSettings(BaseModel):
    provider: Provider = "ollama"
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    update_channel: Channel = "stable"

    @field_validator("base_url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value:
            parts = urlsplit(value)
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                raise ValueError("base_url must be an http(s) URL")
        return value


class SettingsStore:
    """Provider settings persisted as a 0600 JSON file under the data dir."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def load(self) -> StoredSettings:
        with self._lock:
            return self._load()

    def update(self, changes: dict[str, Any]) -> StoredSettings:
        with self._lock:
            merged = self._load().model_dump()
            for key, value in changes.items():
                if value is None and key in _CLEARABLE:
                    value = ""
                merged[key] = value
            try:
                updated = StoredSettings.model_validate(merged)
            except ValidationError as exc:
                first = exc.errors()[0]
                raise InvalidInputError(f"{first['loc'][0]}: {first['msg']}") from exc
            self._write(updated)
            return updated

    def _load(self) -> StoredSettings:
        if not self._path.exists():
            return StoredSettings()
        try:
            return StoredSettings.model_validate(json.loads(self._path.read_text()))
        except (ValueError, OSError) as exc:
            raise ConfigurationError(f"settings file is unreadable: {self._path}") from exc

    def _write(self, settings: StoredSettings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(settings.model_dump(), fh, indent=2)
        os.replace(tmp, self._path)
