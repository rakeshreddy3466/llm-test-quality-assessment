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


# MR1: three paraphrases of USER_V1. They keep every requirement; only the wording differs.
PARAPHRASES = {
    "mr1a": """\
Please create a pytest test module that tests the file `{module}` from the Home Assistant \
integration located at `homeassistant/components/{component}/`. Below you will find the \
whole source code of the integration, so that you know what `{module}` relies on.

About the execution environment:
- The tests are run by pytest within the Home Assistant core repository. Asynchronous tests \
are ordinary `async def test_...` functions (no decorator is required) and can request the \
`hass` fixture.
- Handy imports: `from tests.common import MockConfigEntry`, \
`from homeassistant.setup import async_setup_component`, \
`from homeassistant.core import HomeAssistant`, `from unittest.mock import patch`, and \
`pytest`.
- Avoid snapshot (syrupy) assertions, network access and sleeping.

What I need:
1. Thorough coverage of what `{module}` does: regular paths, boundary values, error paths \
and options.
2. Each test function carries a docstring with exactly this layout:
   \"\"\"Behaviour: <one sentence describing what is verified>.

   Target: <name of the function, method or class under test>
   \"\"\"
3. Every test asserts something specific about observable behaviour.
4. Give tests clear names, keep them small and independent, and factor shared setup into \
helper functions or fixtures when that removes duplication.
5. Deliver a single complete, importable file inside one ```python block.

{sources}
""",
    "mr1b": """\
Task: unit tests for `{module}` (Home Assistant integration `{component}`, path \
`homeassistant/components/{component}/`).

The integration's full source follows at the end of this message; use it to understand the \
module and everything it depends on.

Test environment:
- pytest, run inside the Home Assistant core repository.
- Async tests are plain `async def test_...` functions without any decorator; the `hass` \
fixture is available.
- Imports you will probably want: `from tests.common import MockConfigEntry`, \
`from homeassistant.setup import async_setup_component`, \
`from homeassistant.core import HomeAssistant`, `from unittest.mock import patch`, `pytest`.
- Constraints: no syrupy snapshots, no network, no sleeping.

Rules for the tests:
1. Be thorough about `{module}`: normal behaviour, boundary values, error handling, options.
2. Docstring of every test function, in exactly this form:
   \"\"\"Behaviour: <one sentence describing what is verified>.

   Target: <name of the function, method or class under test>
   \"\"\"
3. Make concrete assertions about observable behaviour in every test.
4. Prefer descriptive names and small independent tests; use helper functions or fixtures \
for shared setup if that cuts duplication.
5. Reply with one complete, importable Python file in one ```python block.

{sources}
""",
    "mr1c": """\
You are given the Home Assistant integration `homeassistant/components/{component}/` (full \
source below). Produce a pytest test module for its file `{module}`.

Facts about how the tests run: pytest, inside the Home Assistant core repository; async \
tests are simply `async def test_...` (no decorator) and may take the `hass` fixture. \
Imports that tend to be useful: `from tests.common import MockConfigEntry`, \
`from homeassistant.setup import async_setup_component`, \
`from homeassistant.core import HomeAssistant`, `from unittest.mock import patch`, \
`pytest`. Do not use snapshot (syrupy) assertions, do not touch the network and do not sleep.

Your tests must:
1. cover `{module}` thoroughly - normal paths, boundary values, error paths and options;
2. give every test function a docstring shaped exactly like this:
   \"\"\"Behaviour: <one sentence describing what is verified>.

   Target: <name of the function, method or class under test>
   \"\"\"
3. assert something specific about observable behaviour in each test;
4. use clear names and small, independent tests, sharing setup through helper functions or \
fixtures where this reduces duplication;
5. be delivered as one complete, importable file in a single ```python block.

{sources}
""",
}
SOURCE_TRANSFORM_VERSIONS = ("mr2", "mr3", "mr4")  # USER_V1 text, transformed source code
VERSIONS = ("v1", *PARAPHRASES, *SOURCE_TRANSFORM_VERSIONS)


@dataclass(frozen=True)
class Prompt:
    version: str
    system: str
    user: str
    target: str

    @property
    def text(self) -> str:
        return f"{self.system}\n\n{self.user}"


def read_sources(component_dir: Path, transform=None) -> str:
    """Concatenate the component's own source files (never tests).

    `transform` (MR2-MR4) is applied to the Python files only.
    """
    parts = []
    for path in sorted(component_dir.glob("*.py")) + [component_dir / "strings.json"]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if transform is not None and path.suffix == ".py":
                text = transform(text)
            parts.append(f"### File: {path.name}\n```\n{text}\n```")
    return "\n\n".join(parts)


def _transform_for(version: str):
    from . import transforms

    return {
        "mr2": transforms.rename_locals,
        "mr3": transforms.reorder_functions,
        "mr4": transforms.strip_comments,
    }.get(version)


def build_prompt(
    *, component: str, module: str, target: str, component_dir: Path, version: str = "v1"
) -> Prompt:
    if version not in VERSIONS:
        raise ValueError(f"unknown prompt version: {version}")
    template = PARAPHRASES.get(version, USER_V1)
    user = template.format(
        module=module, component=component,
        sources=read_sources(component_dir, _transform_for(version)),
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
