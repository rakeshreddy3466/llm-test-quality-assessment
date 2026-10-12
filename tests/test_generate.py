import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from testquality.config import Settings, load_config
from testquality.generate import analyse_source, extract_code, make_plan, run_generation
from testquality.llm import LoggedLLM
from testquality.prompts import Prompt, assert_no_leakage

GOOD = '''
async def test_a(hass):
    """Behaviour: it works.

    Target: foo
    """
    assert True


def test_b():
    """No tags."""
    assert 1
'''


def fake_settings(tmp_path: Path) -> Settings:
    ha = tmp_path / "ha"
    comp = ha / "homeassistant/components/threshold"
    comp.mkdir(parents=True)
    (comp / "binary_sensor.py").write_text("X = 1\n")
    (comp / "config_flow.py").write_text("Y = 2\n")
    (comp / "__init__.py").write_text("Z = 3\n")
    tests = ha / "tests/components/threshold"
    tests.mkdir(parents=True)
    (tests / "test_dev.py").write_text("def test_secret_developer_case():\n    assert True\n")
    return Settings(load_config(), ha, ha / ".venv/bin/python", tmp_path)


class FakeClient:
    def __init__(self, text: str, stop: str = "end_turn"):
        self.calls: list[dict] = []
        self.messages = self
        self._text, self._stop = text, stop

    def create(self, **kw):
        self.calls.append(kw)
        usage = SimpleNamespace(model_dump=lambda: {"input_tokens": 100, "output_tokens": 50})
        block = SimpleNamespace(type="text", text=self._text, model_dump=lambda: {"type": "text"})
        return SimpleNamespace(content=[block], stop_reason=self._stop, usage=usage)


def test_extract_code_picks_longest_block():
    text = "a\n```python\nx=1\n```\nb\n```python\nlonger = 2\nmore = 3\n```"
    assert "longer" in extract_code(text)
    assert extract_code("no code here") is None


def test_analyse_source_counts_tags_and_syntax():
    ok, n, tagged = analyse_source(GOOD)
    assert (ok, n, tagged) == (True, 2, 1)
    assert analyse_source("def broken(:\n")[0] is False


def test_leakage_check_detects_dev_test_names(tmp_path):
    s = fake_settings(tmp_path)
    clean = Prompt("v1", "sys", "write tests", "t")
    assert_no_leakage(clean, s.developer_tests_dir)
    leaky = Prompt("v1", "sys", "see test_secret_developer_case", "t")
    with pytest.raises(RuntimeError):
        assert_no_leakage(leaky, s.developer_tests_dir)


def test_prompt_never_contains_developer_tests(tmp_path):
    s = fake_settings(tmp_path)
    plan = make_plan(s, models=["claude-haiku-5-5"], k=2)
    assert len(plan.prompts) == 3
    for p in plan.prompts:
        assert "test_secret_developer_case" not in p.text
        assert "Behaviour:" in p.user and "Target:" in p.user
    assert plan.n_calls == 6
    assert plan.total_cost > 0


def test_run_generation_logs_every_call(tmp_path):
    s = fake_settings(tmp_path)
    plan = make_plan(s, models=["claude-haiku-5-5"], k=2, targets=["init"])
    client = FakeClient(f"```python\n{GOOD}\n```")
    run_dir = run_generation(s, client, plan, run_id="r1")
    lines = (run_dir / "calls.jsonl").read_text().splitlines()
    assert len(lines) == 2 == len(client.calls)
    rec = json.loads(lines[0])
    for key in ("model", "prompt", "response", "usage", "params", "timestamp", "prompt_version"):
        assert key in rec
    for kw in client.calls:
        for banned in ("temperature", "top_p", "top_k"):
            assert banned not in kw
    mani = json.loads((run_dir / "manifest.json").read_text())
    assert all(x["syntax_ok"] and x["n_tests"] == 2 for x in mani["samples"])
    assert len(list((run_dir / "samples").glob("*.py"))) == 2


def test_truncated_response_is_not_used(tmp_path):
    s = fake_settings(tmp_path)
    plan = make_plan(s, models=["claude-haiku-5-5"], k=1, targets=["init"])
    client = FakeClient(f"```python\n{GOOD}\n```", stop="max_tokens")
    run_dir = run_generation(s, client, plan, run_id="r2")
    mani = json.loads((run_dir / "manifest.json").read_text())
    assert mani["samples"][0]["file"] is None


def test_logged_llm_logs_errors(tmp_path):
    class Boom:
        messages = None

        def create(self, **kw):
            raise RuntimeError("boom")

    c = Boom()
    c.messages = c
    llm = LoggedLLM(c, tmp_path / "calls.jsonl", prompt_version="v1")
    res = llm.call(model="m", system="s", user="u", max_tokens=5, effort=None)
    assert res.error and "boom" in res.error
    assert json.loads((tmp_path / "calls.jsonl").read_text())["error"]
