"""Agent tools: fetch a web page, read a workspace file.

Both tools treat their input as untrusted (it comes from a model that may have
been steered by page content): `read_file` is confined to the workspace and
`fetch_page` refuses non-public network addresses.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

MAX_FETCH_BYTES = 1_000_000
MAX_FILE_BYTES = 200_000
MAX_REDIRECTS = 3
FETCH_TIMEOUT = 10.0
USER_AGENT = "llm-dashboard-agent/0.1"

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "fetch_page",
        "description": "Fetch a public web page over http(s) and return its text content.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Absolute http(s) URL"}},
            "required": ["url"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file from the workspace folder by relative path.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path relative to workspace"}},
            "required": ["path"],
        },
    },
]


class ToolError(Exception):
    """A tool call failed in a way the model should be told about."""


def _resolve_host(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ToolError(f"could not resolve host {host!r}") from exc
    return [info[4][0] for info in infos]


def _assert_public_url(url: str) -> None:
    """Reject non-http(s) URLs and hosts that resolve to non-public addresses.

    Note: this checks at resolve time, so a hostile DNS server could still
    rebind between the check and the connection.
    """
    try:
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise ToolError("invalid URL") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ToolError("only absolute http(s) URLs are allowed")
    if parts.username or parts.password:
        raise ToolError("URLs with embedded credentials are not allowed")
    for address in _resolve_host(parts.hostname, port):
        ip = ipaddress.ip_address(address.split("%")[0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise ToolError("refusing to fetch a non-public address")


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    return re.sub(r"\s+", " ", " ".join(extractor.parts)).strip()


class ToolBox:
    def __init__(self, workspace: Path, http_client: httpx.Client | None = None) -> None:
        self._workspace = workspace
        self._client = http_client

    @property
    def specs(self) -> list[dict[str, Any]]:
        return TOOL_SPECS

    def run(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool; failures come back as `error: ...` text for the model."""
        try:
            if name == "fetch_page":
                return self.fetch_page(self._string_arg(arguments, "url"))
            if name == "read_file":
                return self.read_file(self._string_arg(arguments, "path"))
            raise ToolError(f"unknown tool {name!r}")
        except ToolError as exc:
            return f"error: {exc}"

    @staticmethod
    def _string_arg(arguments: dict[str, Any], key: str) -> str:
        value = arguments.get(key) if isinstance(arguments, dict) else None
        if not isinstance(value, str) or not value:
            raise ToolError(f"missing string argument {key!r}")
        return value

    def fetch_page(self, url: str) -> str:
        client = self._client or httpx.Client(timeout=FETCH_TIMEOUT)
        try:
            return self._fetch(client, url)
        except httpx.HTTPError as exc:
            raise ToolError(f"request failed ({type(exc).__name__})") from exc
        finally:
            if client is not self._client:
                client.close()

    def _fetch(self, client: httpx.Client, url: str) -> str:
        for _ in range(MAX_REDIRECTS + 1):
            _assert_public_url(url)  # re-checked on every hop
            with client.stream(
                "GET", url, headers={"User-Agent": USER_AGENT}, follow_redirects=False
            ) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location", "")
                    if not location:
                        raise ToolError("redirect without a location")
                    url = urljoin(url, location)
                    continue
                if resp.status_code >= 400:
                    raise ToolError(f"HTTP {resp.status_code}")
                content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_FETCH_BYTES:
                        del body[MAX_FETCH_BYTES:]
                        break
            text = bytes(body).decode("utf-8", errors="replace")
            if content_type in {"text/html", "application/xhtml+xml"}:
                return html_to_text(text)
            if content_type.startswith("text/") or content_type in {"application/json", ""}:
                return text
            raise ToolError(f"unsupported content type {content_type!r}")
        raise ToolError("too many redirects")

    def read_file(self, path: str) -> str:
        root = self._workspace.resolve()
        try:
            candidate = (root / path).resolve()  # absolute `path` replaces root, then fails below
        except (ValueError, OSError) as exc:
            raise ToolError("invalid path") from exc
        if not candidate.is_relative_to(root):
            raise ToolError("path is outside the workspace")
        if not candidate.is_file():
            raise ToolError("file not found")
        with candidate.open("rb") as fh:
            data = fh.read(MAX_FILE_BYTES + 1)
        if b"\0" in data[:8192]:
            raise ToolError("binary files are not supported")
        text = data[:MAX_FILE_BYTES].decode("utf-8", errors="replace")
        return text + ("\n[truncated]" if len(data) > MAX_FILE_BYTES else "")


def list_workspace_files(workspace: Path, limit: int = 500) -> list[str]:
    root = workspace.resolve()
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if len(files) >= limit:
            break
        if path.resolve().is_relative_to(root) and path.is_file():
            files.append(path.relative_to(root).as_posix())
    return files
