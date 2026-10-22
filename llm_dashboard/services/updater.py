from __future__ import annotations

import subprocess
import sys

from packaging.version import InvalidVersion, Version

from llm_dashboard.errors import InvalidInputError


def self_update(target: str) -> dict:
    """Upgrade the dashboard's own package to the requested target."""
    if not isinstance(target, str):
        raise InvalidInputError("invalid target version")
    try:
        target = str(Version(target))
    except InvalidVersion as exc:
        raise InvalidInputError("invalid target version") from exc

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", f"llm-dashboard=={target}"],
        capture_output=True,
        text=True,
    )
    return {
        "success": result.returncode == 0,
        "target": target,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
