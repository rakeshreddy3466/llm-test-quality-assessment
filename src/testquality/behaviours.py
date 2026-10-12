"""Relevance and completeness against data/behaviours.yaml (docs/metrics.md section 6).

The YAML is a DRAFT written by the assistant and must be checked by a human; the numbers
produced here inherit that caveat.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import Settings
from .executor import write_keyed_csv

MAP_THRESHOLD = 0.5  # a test maps to a behaviour if it covers >= 50 % of its statements

TEST_FIELDS = ["suite", "unit", "test", "n_behaviours", "behaviours"]
BEHAVIOUR_FIELDS = ["suite", "behaviour", "statements", "reachable", "tests", "units"]
SUMMARY_FIELDS = [
    "suite", "scope", "behaviours_reachable", "behaviours_covered", "completeness",
    "completeness_weighted", "valid_tests", "relevant_tests", "relevance",
]


@dataclass(frozen=True)
class Behaviour:
    id: str
    file: str
    lines: tuple[int, int]
    title: str


def load_behaviours(path: Path) -> list[Behaviour]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        Behaviour(b["id"], b["file"], tuple(b["lines"]), b["title"]) for b in data["behaviours"]
    ]


def behaviour_statements(b: Behaviour, statements: dict[str, list[int]]) -> set[int]:
    lo, hi = b.lines
    return {ln for ln in statements.get(b.file.split(".")[0], []) if lo <= ln <= hi}


def load_cache(settings: Settings, suite: str) -> dict:
    path = settings.results_dir / "cache" / f"coverage_{suite}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run `testquality coverage --suite {suite}` first")
    return json.loads(path.read_text(encoding="utf-8"))


def _statements(cache: dict) -> dict[str, list[int]]:
    """module -> statement lines (from any unit; identical across units)."""
    for unit in cache.values():
        return {name.split(".")[0]: f["statements"] for name, f in unit["files"].items()}
    return {}


def _test_lines(entry: dict) -> dict[str, set[int]]:
    return {name.split(".")[0]: set(f["lines"]) for name, f in entry.items()}


def map_tests(
    behaviours: list[Behaviour], statements: dict[str, list[int]], cache: dict
) -> dict[tuple[str, str], set[str]]:
    stm = {b.id: behaviour_statements(b, statements) for b in behaviours}
    out: dict[tuple[str, str], set[str]] = {}
    for unit, data in cache.items():
        for test, entry in data["tests"].items():
            lines = _test_lines(entry)
            hit = set()
            for b in behaviours:
                s = stm[b.id]
                if s and len(s & lines.get(b.file.split(".")[0], set())) / len(s) >= MAP_THRESHOLD:
                    hit.add(b.id)
            out[(unit, test)] = hit
    return out


def import_time_lines(path: Path) -> set[int]:
    """Statement lines executed when the module is imported (module / class level, defs)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines: set[int] = set()

    def visit_body(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                lines.add(node.lineno)
                lines.update(d.lineno for d in node.decorator_list)
            elif isinstance(node, ast.ClassDef):
                lines.add(node.lineno)
                visit_body(node.body)
            else:
                lines.update(s.lineno for s in ast.walk(node) if isinstance(s, ast.stmt))

    visit_body(tree.body)
    return lines


def reachable_behaviours(
    behaviours: list[Behaviour], statements: dict[str, list[int]], dev_cache: dict,
    component_dir: Path | None = None,
) -> set[str]:
    """Behaviours whose coverage can be attributed to individual tests.

    Behaviours whose statements all run at import time (module level schemas) are executed in
    whichever test happens to import the module first, so attribution is arbitrary: they are
    excluded from relevance/completeness.
    """
    mapped = map_tests(behaviours, statements, dev_cache)
    reach = set().union(*mapped.values()) if mapped else set()
    if component_dir is not None:
        for b in behaviours:
            stm = behaviour_statements(b, statements)
            if stm and stm <= import_time_lines(component_dir / b.file):
                reach.discard(b.id)
    return reach


def run_behaviours(
    settings: Settings, suite: str, targets: dict[str, str]
) -> list[dict]:
    behaviours = load_behaviours(settings.project_root / "data" / "behaviours.yaml")
    dev_cache = load_cache(settings, "developer")
    cache = load_cache(settings, suite)
    statements = _statements(dev_cache)
    comp_dir = settings.ha_core_dir / settings.config["ha"]["component_dir"]
    reach = reachable_behaviours(behaviours, statements, dev_cache, comp_dir)
    mapping = map_tests(behaviours, statements, cache)
    weight = {b.id: len(behaviour_statements(b, statements)) for b in behaviours}

    test_rows = [
        {"suite": suite, "unit": u, "test": t, "n_behaviours": len(h & reach),
         "behaviours": " ".join(sorted(h & reach))}
        for (u, t), h in sorted(mapping.items())
    ]
    beh_rows = []
    for b in behaviours:
        tests = [(u, t) for (u, t), h in mapping.items() if b.id in h]
        beh_rows.append({
            "suite": suite, "behaviour": b.id, "statements": weight[b.id],
            "reachable": int(b.id in reach), "tests": len(tests),
            "units": len({u for u, _ in tests}),
        })

    def summary(scope: str, units: set[str]) -> dict:
        sel = {k: v for k, v in mapping.items() if k[0] in units}
        covered = set().union(*sel.values()) & reach if sel else set()
        w_total = sum(weight[i] for i in reach)
        relevant = sum(1 for h in sel.values() if h & reach)
        return {
            "suite": suite, "scope": scope, "behaviours_reachable": len(reach),
            "behaviours_covered": len(covered),
            "completeness": round(len(covered) / len(reach), 4) if reach else "",
            "completeness_weighted": (
                round(sum(weight[i] for i in covered) / w_total, 4) if w_total else ""
            ),
            "valid_tests": len(sel), "relevant_tests": relevant,
            "relevance": round(relevant / len(sel), 4) if sel else "",
        }

    all_units = set(cache)
    rows = [summary("all", all_units)]
    for tgt in sorted({t for t in targets.values() if t and t != "developer"}):
        rows.append(summary(f"target:{tgt}", {u for u, t in targets.items() if t == tgt}))
    res = settings.results_dir
    write_keyed_csv(res / "behaviour_tests.csv", TEST_FIELDS, test_rows)
    write_keyed_csv(res / "behaviour_behaviours.csv", BEHAVIOUR_FIELDS, beh_rows)
    write_keyed_csv(res / "behaviour_summary.csv", SUMMARY_FIELDS, rows)
    return rows
