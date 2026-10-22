from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from llm_dashboard.errors import ConfigurationError, InvalidInputError, UpstreamError
from llm_dashboard.services.process import Runner, tail

_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
_LIST_TIMEOUT = 30


@dataclass(frozen=True)
class ModelInfo:
    name: str


@dataclass(frozen=True)
class PullResult:
    name: str
    status: str


class ModelService:
    """Wraps the local model CLI (ollama-style `pull` / `list`).

    In mock mode no CLI is invoked; pulled names are kept in a small JSON file.
    """

    def __init__(
        self, *, cli: str, runner: Runner, timeout: int, mock: bool, state_path: Path
    ) -> None:
        self._cli = cli
        self._runner = runner
        self._timeout = timeout
        self._mock = mock
        self._state_path = state_path
        self._lock = threading.Lock()

    def list_models(self) -> list[ModelInfo]:
        if self._mock:
            return [ModelInfo(name) for name in self._read_mock()]
        result = self._runner([self._cli, "list"], _LIST_TIMEOUT)
        if result.returncode != 0:
            raise UpstreamError(f"{self._cli} list failed: {tail(result.stderr)}")
        lines = result.stdout.strip().splitlines()[1:]  # first line is the table header
        return [ModelInfo(line.split()[0]) for line in lines if line.strip()]

    def pull(self, name: str) -> PullResult:
        if not _MODEL_RE.fullmatch(name) or ".." in name:
            raise InvalidInputError("invalid model name")
        if self._mock:
            with self._lock:
                names = self._read_mock()
                if name not in names:
                    names.append(name)
                    self._write_mock(names)
            return PullResult(name, "pulled (mock)")
        if not self._cli:
            raise ConfigurationError("no model CLI configured")
        result = self._runner([self._cli, "pull", name], self._timeout)
        if result.returncode != 0:
            raise UpstreamError(f"{self._cli} pull failed: {tail(result.stderr)}")
        return PullResult(name, "pulled")

    def _read_mock(self) -> list[str]:
        if not self._state_path.exists():
            return []
        return list(json.loads(self._state_path.read_text()))

    def _write_mock(self, names: list[str]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(names))
