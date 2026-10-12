"""Load config.yaml and the .env settings. Secrets are never printed."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    config: dict
    ha_core_dir: Path
    ha_python: Path
    project_root: Path

    @property
    def developer_tests_dir(self) -> Path:
        return self.ha_core_dir / self.config["ha"]["developer_tests_dir"]

    @property
    def generated_tests_dir(self) -> Path:
        return self.ha_core_dir / self.config["ha"]["generated_tests_dir"]

    @property
    def runs_dir(self) -> Path:
        return self.project_root / self.config["paths"]["runs_dir"]

    @property
    def results_dir(self) -> Path:
        return self.project_root / self.config["paths"]["results_dir"]


def load_config(path: Path | None = None) -> dict:
    path = path or PROJECT_ROOT / "config.yaml"
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_settings(root: Path | None = None) -> Settings:
    """Read config.yaml plus .env (real environment variables win over .env)."""
    root = root or PROJECT_ROOT
    env = {**dotenv_values(root / ".env"), **os.environ}
    ha_core = env.get("HA_CORE_DIR") or str(Path.home() / "code" / "ha-core")
    ha_python = env.get("HA_PYTHON") or str(Path(ha_core) / ".venv" / "bin" / "python")
    return Settings(
        config=load_config(root / "config.yaml"),
        ha_core_dir=Path(ha_core).expanduser(),
        ha_python=Path(ha_python).expanduser(),
        project_root=root,
    )


def get_api_key(root: Path | None = None) -> str | None:
    """Return the API key or None. Callers must never print it."""
    root = root or PROJECT_ROOT
    env = {**dotenv_values(root / ".env"), **os.environ}
    return env.get("ANTHROPIC_API_KEY") or None


def get_workspace_id(root: Path | None = None) -> str | None:
    """Optional: needed when the API key is not scoped to a workspace."""
    root = root or PROJECT_ROOT
    env = {**dotenv_values(root / ".env"), **os.environ}
    return env.get("ANTHROPIC_WORKSPACE_ID") or None
