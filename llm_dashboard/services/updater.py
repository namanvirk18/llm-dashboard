from __future__ import annotations

import subprocess
import sys


def self_update(target: str) -> dict:
    """Upgrade the dashboard's own package to the requested target."""
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
