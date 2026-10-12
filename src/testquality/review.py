"""Blinded manual-review sample (phase 9). Never writes ratings.

Pool: test *functions* (not parametrised cases) that have at least one stably passing case.
Fixed seed. Origin is hidden: item ids are shuffled and the `Behaviour:` / `Target:` docstring
tags of generated tests are normalised away. The origin key goes to a separate file.
"""

from __future__ import annotations

import ast
import csv
import random
import re
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

RATING_COLUMNS = ["relevance", "clarity", "maintainability", "oracle_strength"]
SAMPLE_FIELDS = ["item_id", "test_name", "test_code", "context_code", *RATING_COLUMNS, "notes"]
KEY_FIELDS = ["item_id", "origin", "suite", "unit", "test", "target"]


@dataclass
class Candidate:
    origin: str
    suite: str
    unit: str
    test: str
    target: str
    code: str
    context: str


def normalise_docstring(code: str) -> str:
    """Drop the `Behaviour:` prefix and the `Target:` line (they would reveal the origin)."""
    code = re.sub(r'(\n[ \t]*)Target:[^\n]*', "", code)
    code = re.sub(r"Behaviou?r:\s*([a-z])", lambda m: m.group(1).upper(), code)
    code = re.sub(r"Behaviou?r:\s*", "", code)
    # single-sentence docstring: close the quotes on the same line, as developers usually do
    code = re.sub(r'("""[^\n"]*?)\s*\n\s*"""', r"\1" + '"""', code)
    return code


def _segment(src_lines: list[str], node: ast.AST) -> str:
    first = min([node.lineno, *[d.lineno for d in getattr(node, "decorator_list", [])]])
    return "\n".join(src_lines[first - 1 : node.end_lineno])


def candidates_from_file(
    path: Path, *, origin: str, suite: str, target: str, valid_functions: set[str]
) -> list[Candidate]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    lines = text.splitlines()
    helpers = {
        n.name: n for n in tree.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and not n.name.startswith("test_")
    }
    out = []
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name.startswith("test_") and node.name in valid_functions):
            continue
        used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        # fixtures used as arguments or via decorators also count as context
        used |= {a.arg for a in node.args.args}
        ctx = "\n\n".join(_segment(lines, h) for name, h in helpers.items() if name in used)
        out.append(Candidate(origin, suite, path.name, node.name, target,
                             _segment(lines, node), ctx))
    return out


def valid_functions_by_unit(settings: Settings, suite: str) -> dict[str, set[str]]:
    """unit -> function names with >= 1 stably passing case, from results/exec_tests.csv."""
    runs: dict[tuple[str, str], list[str]] = {}
    with open(settings.results_dir / "exec_tests.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["suite"] == suite:
                runs.setdefault((r["unit"], r["test"]), []).append(r["outcome"])
    out: dict[str, set[str]] = {}
    for (unit, test), outs in runs.items():
        if set(outs) == {"passed"}:
            out.setdefault(unit, set()).add(test.split("[")[0])
    return out


def build_sample(settings: Settings, run_id: str, *, force: bool = False) -> tuple[Path, Path]:
    cfg = settings.config["review"]
    rng = random.Random(cfg["seed"])
    out_dir = settings.project_root / "manual_review"
    sample_path = out_dir / "sample_blinded.csv"
    key_path = out_dir / "key_do_not_open_until_rated.csv"
    if sample_path.exists() and not force:
        raise FileExistsError(f"{sample_path} exists (ratings may have been added); use --force")

    dev_valid = valid_functions_by_unit(settings, "developer")
    pool_dev: list[Candidate] = []
    for path in sorted(settings.developer_tests_dir.glob("test_*.py")):
        pool_dev += candidates_from_file(
            path, origin="developer", suite="developer", target="developer",
            valid_functions=dev_valid.get(path.name, set()),
        )

    run_dir = settings.runs_dir / run_id
    import json

    mani = json.loads((run_dir / "manifest.json").read_text())
    llm_valid = valid_functions_by_unit(settings, run_id)
    by_target: dict[str, list[Candidate]] = {}
    for s in sorted(mani["samples"], key=lambda s: (s["target"], s["sample"])):
        if not s["file"]:
            continue
        by_target.setdefault(s["target"], []).extend(candidates_from_file(
            run_dir / "samples" / s["file"], origin="llm", suite=run_id, target=s["target"],
            valid_functions=llm_valid.get(s["file"], set()),
        ))

    n_dev, n_llm = cfg["n_developer"], cfg["n_llm"]
    chosen = rng.sample(pool_dev, min(n_dev, len(pool_dev)))
    targets = sorted(by_target)
    quota = {t: n_llm // len(targets) + (1 if i < n_llm % len(targets) else 0)
             for i, t in enumerate(targets)}
    for t in targets:
        chosen += rng.sample(by_target[t], min(quota[t], len(by_target[t])))
    rng.shuffle(chosen)

    out_dir.mkdir(exist_ok=True)
    with open(sample_path, "w", newline="", encoding="utf-8") as fh, \
            open(key_path, "w", newline="", encoding="utf-8") as kh:
        w = csv.DictWriter(fh, fieldnames=SAMPLE_FIELDS)
        k = csv.DictWriter(kh, fieldnames=KEY_FIELDS)
        w.writeheader()
        k.writeheader()
        for i, c in enumerate(chosen, 1):
            item = f"R{i:02d}"
            code = normalise_docstring(c.code) if c.origin == "llm" else c.code
            ctx = normalise_docstring(c.context) if c.origin == "llm" else c.context
            w.writerow({"item_id": item, "test_name": c.test, "test_code": code,
                        "context_code": ctx, **{col: "" for col in RATING_COLUMNS}, "notes": ""})
            k.writerow({"item_id": item, "origin": c.origin, "suite": c.suite, "unit": c.unit,
                        "test": c.test, "target": c.target})
    return sample_path, key_path
