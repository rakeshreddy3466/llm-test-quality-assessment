"""AST based test smell detector (definitions in docs/metrics.md section 5).

All thresholds are constants below. Detection is per test function (sync or async) and counts
smell *instances*. No test code is executed.
"""

from __future__ import annotations

import ast
import csv
from collections import Counter
from pathlib import Path

from .config import Settings
from .executor import write_keyed_csv
from .traceability import sut_candidates

SMELLS = [
    "empty_test", "no_assertion", "assertion_roulette", "duplicate_assert", "magic_number",
    "conditional_logic", "sleepy_test", "redundant_print", "eager_test", "try_except",
]
ROULETTE_MIN_ASSERTS = 4        # more than 3 asserts without a message
ALLOWED_NUMBERS = {0, 1, -1}    # not "magic"
EAGER_MIN_SUT_FUNCS = 4         # more than 3 distinct SUT functions called
SLEEP_NAMES = {"sleep"}
PRINT_NAMES = {"print", "pprint"}

TEST_FIELDS = ["suite", "unit", "test", "valid", *SMELLS, "total"]
SUMMARY_FIELDS = ["suite", "tests", "valid_tests", "smelly_rate", "smell_density",
                  *[f"rate_{s}" for s in SMELLS]]


def _call_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    return getattr(f, "id", "")


def _is_assertion_call(call: ast.Call) -> bool:
    name = _call_name(call)
    return name.startswith("assert") or name in {"raises", "warns", "fail"}


def _body_statements(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None),
                                                             ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]  # docstring
    return body


def _walk_body(fn) -> list[ast.AST]:
    nodes: list[ast.AST] = []
    for stmt in _body_statements(fn):
        nodes.extend(ast.walk(stmt))
    return nodes


def detect(fn: ast.FunctionDef | ast.AsyncFunctionDef, sut_names: set[str]) -> Counter:
    """Return smell -> instance count for one test function."""
    out: Counter = Counter()
    body = _body_statements(fn)
    nodes = _walk_body(fn)

    if all(
        isinstance(s, ast.Pass)
        or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        for s in body
    ):
        out["empty_test"] += 1
        return out  # an empty test is not additionally flagged as "no assertion"

    asserts = [n for n in nodes if isinstance(n, ast.Assert)]
    has_assertion = bool(asserts) or any(
        isinstance(n, ast.Call) and _is_assertion_call(n) for n in nodes
    ) or any(
        isinstance(n, ast.With | ast.AsyncWith)
        and any(isinstance(i.context_expr, ast.Call) and _is_assertion_call(i.context_expr)
                for i in n.items)
        for n in nodes
    )
    if not has_assertion:
        out["no_assertion"] += 1

    unmessaged = [a for a in asserts if a.msg is None]
    if len(unmessaged) >= ROULETTE_MIN_ASSERTS:
        out["assertion_roulette"] += 1

    seen = Counter(ast.dump(a.test) for a in asserts)
    out["duplicate_assert"] += sum(c - 1 for c in seen.values() if c > 1)

    for a in asserts:
        for sub in ast.walk(a.test):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, int | float) \
                    and not isinstance(sub.value, bool) and sub.value not in ALLOWED_NUMBERS:
                out["magic_number"] += 1
            if isinstance(sub, ast.UnaryOp) and isinstance(sub.op, ast.USub) \
                    and isinstance(sub.operand, ast.Constant) \
                    and isinstance(sub.operand.value, int | float) \
                    and -sub.operand.value not in ALLOWED_NUMBERS:
                # counted via the inner Constant above; avoid double count of the sign
                pass

    for n in nodes:
        if isinstance(n, ast.If | ast.For | ast.AsyncFor | ast.While | ast.IfExp | ast.Match):
            out["conditional_logic"] += 1
        elif isinstance(n, ast.Try | ast.TryStar) and n.handlers:
            out["try_except"] += 1
        elif isinstance(n, ast.Call):
            name = _call_name(n)
            if name in SLEEP_NAMES:
                out["sleepy_test"] += 1
            elif name in PRINT_NAMES:
                out["redundant_print"] += 1

    called = {_call_name(n) for n in nodes if isinstance(n, ast.Call)}
    if len(called & sut_names) >= EAGER_MIN_SUT_FUNCS:
        out["eager_test"] += 1
    return out


def sut_function_names(component_dir: Path) -> set[str]:
    """Simple names of SUT functions/methods (classes and dunder/private excluded)."""
    names = set()
    for c in sut_candidates(component_dir):
        simple = c.split(":", 1)[1].split(".")[-1]
        if "." in c.split(":", 1)[1] or c.split(":", 1)[1][0].islower():
            names.add(simple)
    return {n for n in names if not n.startswith("__")}


def analyse_file(path: Path, sut_names: set[str]) -> dict[str, Counter]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        n.name: detect(n, sut_names)
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test_")
    }


def run_smells(
    settings: Settings, suite: str, units: list[Path], stable: set[tuple[str, str]] | None,
) -> dict:
    """Smells per test function; parametrised cases inherit their function's smells."""
    sut = sut_function_names(settings.ha_core_dir / settings.config["ha"]["component_dir"])
    rows: list[dict] = []
    exec_path = settings.results_dir / "exec_tests.csv"
    cases: dict[tuple[str, str], list[str]] = {}
    if exec_path.exists():
        with open(exec_path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["suite"] == suite:
                    base = r["test"].split("[")[0]
                    cases.setdefault((r["unit"], base), [])
                    if r["test"] not in cases[(r["unit"], base)]:
                        cases[(r["unit"], base)].append(r["test"])
    for unit in units:
        for fname, counter in analyse_file(unit, sut).items():
            # one row per executed case, or one row for the function if never executed
            for test in cases.get((unit.name, fname)) or [fname]:
                row = {"suite": suite, "unit": unit.name, "test": test,
                       "valid": int(stable is None or (unit.name, test) in stable)}
                row.update({s: counter.get(s, 0) for s in SMELLS})
                row["total"] = sum(counter.values())
                rows.append(row)
    summary = summarise(suite, rows)
    write_keyed_csv(settings.results_dir / "smells_tests.csv", TEST_FIELDS, rows)
    write_keyed_csv(settings.results_dir / "smells_summary.csv", SUMMARY_FIELDS, [summary])
    return summary


def summarise(suite: str, rows: list[dict]) -> dict:
    valid = [r for r in rows if r["valid"]]
    n = len(valid)
    out = {
        "suite": suite, "tests": len(rows), "valid_tests": n,
        "smelly_rate": round(sum(1 for r in valid if r["total"]) / n, 4) if n else "",
        "smell_density": round(sum(r["total"] for r in valid) / n, 4) if n else "",
    }
    for s in SMELLS:
        out[f"rate_{s}"] = round(sum(1 for r in valid if r[s]) / n, 4) if n else ""
    return out
