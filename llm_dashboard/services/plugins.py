from __future__ import annotations

import importlib.metadata
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from llm_dashboard.errors import InvalidInputError, UpstreamError
from llm_dashboard.services.process import Runner, tail

_NAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?")
_VERSION_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.!+_-]{0,48}[A-Za-z0-9])?")


@dataclass(frozen=True)
class PluginInfo:
    name: str
    version: str
    summary: str = ""


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


class PluginService:
    """Plugins are pip packages installed into a dedicated directory."""

    def __init__(self, plugins_dir: Path, runner: Runner, timeout: int) -> None:
        self._dir = plugins_dir
        self._runner = runner
        self._timeout = timeout

    def list_plugins(self) -> list[PluginInfo]:
        if not self._dir.is_dir():
            return []
        found: dict[str, PluginInfo] = {}
        for dist in importlib.metadata.distributions(path=[str(self._dir)]):
            name = dist.metadata["Name"]
            if name:
                found[_normalize(name)] = PluginInfo(
                    name=name, version=dist.version, summary=dist.metadata["Summary"] or ""
                )
        return sorted(found.values(), key=lambda p: p.name.lower())

    def install(self, name: str, version: str | None = None) -> PluginInfo:
        spec = self._build_spec(name, version)
        self._dir.mkdir(parents=True, exist_ok=True)
        result = self._runner(
            [
                sys.executable, "-m", "pip", "install",
                "--disable-pip-version-check", "--no-input", "--upgrade",
                "--target", str(self._dir), spec,
            ],
            self._timeout,
        )  # fmt: skip
        if result.returncode != 0:
            raise UpstreamError(f"pip failed: {tail(result.stderr) or 'unknown error'}")
        wanted = _normalize(name)
        for plugin in self.list_plugins():
            if _normalize(plugin.name) == wanted:
                return plugin
        return PluginInfo(name=name, version=version or "unknown")

    @staticmethod
    def _build_spec(name: str, version: str | None) -> str:
        if not _NAME_RE.fullmatch(name):
            raise InvalidInputError("invalid package name")
        if version is None or version == "":
            return name
        if not _VERSION_RE.fullmatch(version):
            raise InvalidInputError("invalid version")
        return f"{name}=={version}"
