"""Prompt construction. Prompts are versioned; the version is logged with every call.

Leakage rule: only the component's own source code is ever included. The developer tests
are never read here. `assert_no_leakage` double-checks that no developer test function name
ended up in a prompt.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

SYSTEM_V1 = """\
You are an experienced Python developer writing unit tests for Home Assistant core \
integrations. You write small, deterministic, readable pytest tests that check observable \
behaviour. You answer with exactly one Python source file in a single ```python code block \
and nothing else of substance."""

USER_V1 = """\
Write a pytest test module for the file `{module}` of the Home Assistant integration \
`homeassistant/components/{component}/`. The complete source of the integration is given \
below so you can see everything the module depends on.

Environment facts:
- Tests run with pytest inside the Home Assistant core repository. Async tests are plain \
`async def test_...` functions (no decorator needed) and may use the `hass` fixture.
- Useful imports: `from tests.common import MockConfigEntry`, \
`from homeassistant.setup import async_setup_component`, \
`from homeassistant.core import HomeAssistant`, `from unittest.mock import patch`, \
`pytest`.
- Do not use snapshot (syrupy) assertions. Do not access the network. Do not sleep.

Requirements:
1. Cover the behaviour of `{module}` thoroughly: normal paths, boundary values, error \
paths and options.
2. Every test function must have a docstring of exactly this shape:
   \"\"\"Behaviour: <one sentence describing what is verified>.

   Target: <name of the function, method or class under test>
   \"\"\"
3. Each test must assert something specific about observable behaviour.
4. Use clear test names and small, independent tests; share setup with helper functions \
or fixtures where that reduces duplication.
5. Output one complete, importable file in one ```python block.

{sources}
"""


@dataclass(frozen=True)
class Prompt:
    version: str
    system: str
    user: str
    target: str

    @property
    def text(self) -> str:
        return f"{self.system}\n\n{self.user}"


def read_sources(component_dir: Path) -> str:
    """Concatenate the component's own source files (never tests)."""
    parts = []
    for path in sorted(component_dir.glob("*.py")) + [component_dir / "strings.json"]:
        if path.exists():
            parts.append(f"### File: {path.name}\n```\n{path.read_text(encoding='utf-8')}\n```")
    return "\n\n".join(parts)


def build_prompt(
    *, component: str, module: str, target: str, component_dir: Path, version: str = "v1"
) -> Prompt:
    if version != "v1":
        raise ValueError(f"unknown prompt version: {version}")
    user = USER_V1.format(
        module=module, component=component, sources=read_sources(component_dir)
    )
    return Prompt(version=version, system=SYSTEM_V1, user=user, target=target)


def developer_test_names(tests_dir: Path) -> set[str]:
    names: set[str] = set()
    for path in tests_dir.rglob("test_*.py"):
        if "_llm_generated" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names |= {
            n.name
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test_")
        }
    return names


def assert_no_leakage(prompt: Prompt, tests_dir: Path) -> None:
    """Raise if any developer test function name occurs in the prompt text."""
    leaked = sorted(n for n in developer_test_names(tests_dir) if n in prompt.text)
    if leaked:
        raise RuntimeError(f"data leakage: developer test names in prompt: {leaked[:5]}")
