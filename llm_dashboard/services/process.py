from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from llm_dashboard.errors import UpstreamError


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


# (argv, timeout_seconds) -> result. Injected so tests never spawn real processes.
Runner = Callable[[Sequence[str], int], CommandResult]


def run_command(argv: Sequence[str], timeout: int) -> CommandResult:
    """Run argv without a shell and capture its output."""
    try:
        proc = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:
        raise UpstreamError(f"command not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise UpstreamError(f"{argv[0]} timed out after {timeout}s") from exc
    return CommandResult(proc.returncode, proc.stdout, proc.stderr)


def tail(text: str, limit: int = 500) -> str:
    text = text.strip()
    return text if len(text) <= limit else "..." + text[-limit:]
