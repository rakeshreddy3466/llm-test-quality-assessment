"""Generation pipeline: prompts x samples -> logged LLM calls -> test files + manifest."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .cost import call_cost, estimate_tokens, usage_cost
from .llm import LoggedLLM
from .prompts import Prompt, assert_no_leakage, build_prompt

CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)
BEHAVIOUR = re.compile(r"Behaviou?r:\s*\S", re.IGNORECASE)
TARGET = re.compile(r"Target:\s*\S", re.IGNORECASE)


def extract_code(text: str) -> str | None:
    """Return the longest fenced code block, or None."""
    blocks = CODE_BLOCK.findall(text)
    return max(blocks, key=len).strip("\n") + "\n" if blocks else None


@dataclass
class SampleInfo:
    target: str
    sample: int
    model: str
    file: str | None
    stop_reason: str | None
    syntax_ok: bool = False
    n_tests: int = 0
    n_tests_with_tags: int = 0  # docstring has both "Behaviour:" and "Target:"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


def analyse_source(code: str) -> tuple[bool, int, int]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False, 0, 0
    tests = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test_")
    ]
    tagged = 0
    for fn in tests:
        doc = ast.get_docstring(fn) or ""
        if BEHAVIOUR.search(doc) and TARGET.search(doc):
            tagged += 1
    return True, len(tests), tagged


@dataclass
class Plan:
    prompts: list[Prompt]
    models: list[str]
    k: int
    est_input_tokens: dict[str, int] = field(default_factory=dict)
    est_cost: dict[str, float] = field(default_factory=dict)

    @property
    def n_calls(self) -> int:
        return len(self.prompts) * len(self.models) * self.k

    @property
    def total_cost(self) -> float:
        return sum(self.est_cost.values())


def make_plan(
    settings: Settings,
    *,
    models: list[str],
    k: int,
    targets: list[str] | None = None,
    prompt_version: str | None = None,
) -> Plan:
    cfg = settings.config
    comp = cfg["ha"]["component"]
    comp_dir = settings.ha_core_dir / cfg["ha"]["component_dir"]
    version = prompt_version or cfg["llm"]["prompt_version"]
    prompts = []
    for t in cfg["generation"]["targets"]:
        if targets and t["name"] not in targets:
            continue
        p = build_prompt(
            component=comp, module=t["module"], target=t["name"],
            component_dir=comp_dir, version=version,
        )
        assert_no_leakage(p, settings.developer_tests_dir)
        prompts.append(p)
    plan = Plan(prompts=prompts, models=models, k=k)
    out_tok = cfg["llm"]["expected_output_tokens"]
    for m in models:
        n_in = sum(estimate_tokens(p.text) for p in prompts)
        plan.est_input_tokens[m] = n_in * k
        plan.est_cost[m] = call_cost(m, n_in * k, out_tok * len(prompts) * k, cfg["pricing"])
    return plan


def new_run_id(models: list[str], version: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    short = "+".join(m.replace("claude-", "").replace("-", "") for m in models)
    return f"{stamp}_{short}_{version}"


def run_generation(
    settings: Settings, client: Any, plan: Plan, *, run_id: str | None = None
) -> Path:
    cfg = settings.config
    llm_cfg = cfg["llm"]
    version = plan.prompts[0].version
    run_id = run_id or new_run_id(plan.models, version)
    run_dir = settings.runs_dir / run_id
    samples_dir = run_dir / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    llm = LoggedLLM(client, run_dir / "calls.jsonl", prompt_version=version)
    infos: list[SampleInfo] = []
    for model in plan.models:
        for prompt in plan.prompts:
            for i in range(plan.k):
                res = llm.call(
                    model=model, system=prompt.system, user=prompt.user,
                    max_tokens=llm_cfg["max_tokens"], effort=llm_cfg.get("effort"),
                    meta={"target": prompt.target, "sample": i, "run_id": run_id},
                )
                info = SampleInfo(prompt.target, i, model, None, res.stop_reason, error=res.error)
                info.input_tokens = res.usage.get("input_tokens", 0) or 0
                info.output_tokens = res.usage.get("output_tokens", 0) or 0
                if res.usage:
                    info.cost_usd = round(usage_cost(model, res.usage, cfg["pricing"]), 5)
                code = extract_code(res.text) if res.text else None
                if code and res.stop_reason != "max_tokens":
                    name = f"test_{prompt.target}__{model.replace('claude-', '')}__s{i}.py"
                    (samples_dir / name).write_text(code, encoding="utf-8")
                    info.file = name
                    info.syntax_ok, info.n_tests, info.n_tests_with_tags = analyse_source(code)
                elif not info.error:
                    info.error = f"no usable code (stop_reason={res.stop_reason})"
                infos.append(info)
    manifest = {
        "run_id": run_id,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "prompt_version": version,
        "models": plan.models,
        "k": plan.k,
        "targets": [p.target for p in plan.prompts],
        "total_cost_usd": round(sum(s.cost_usd for s in infos), 4),
        "samples": [asdict(s) for s in infos],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return run_dir
