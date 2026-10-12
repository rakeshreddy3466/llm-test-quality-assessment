"""Resolve a suite label ('developer' or a generation run id) to its test files."""

from __future__ import annotations

import json
from pathlib import Path

from .config import Settings
from .executor import developer_units


def suite_units(
    settings: Settings, suite: str
) -> tuple[list[Path], str | None, dict[str, str]]:
    """Return (unit files, staging id or None, unit-name -> target)."""
    if suite == "developer":
        units = developer_units(settings)
        return units, None, {u.name: "developer" for u in units}
    run_dir = settings.runs_dir / suite
    mani = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    samples = [s for s in mani["samples"] if s["file"]]
    units = [run_dir / "samples" / s["file"] for s in samples]
    return units, suite, {s["file"]: s["target"] for s in samples}
