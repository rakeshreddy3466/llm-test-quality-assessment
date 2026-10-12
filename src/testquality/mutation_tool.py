"""Mutation testing of the threshold component with mutmut 3.x.

Home Assistant cannot be mutated in place (mutmut needs its own pyproject section and a
`mutants/` directory, and we must not touch the HA tree). Instead a *workspace* is built under
work/mutmut_ha/: a symlink farm of the HA tree in which only
homeassistant/components/threshold and tests/components/threshold are real directories. The
mutmut package itself is installed with --no-deps into work/mutmut_site (HA venv untouched)
and exposed through PYTHONPATH.

Statuses: killed (exit 1/3), survived (0), timeout (24/36/...), no tests (5/33), other.
Scores:
  score_covered = killed / (killed + survived)   (the brief's definition; mutants whose
                  function no test of the unit executes are 'no tests' and excluded)
  score_global  = killed / all mutants            (fixed denominator, comparable across suites)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from .config import Settings
from .executor import write_keyed_csv

MUTMUT_VERSION = "3.8.0"
SITE_PACKAGES = [
    f"mutmut=={MUTMUT_VERSION}", "libcst==1.9.0", "linkify-it-py==2.2.0",
    "mdit-py-plugins==0.6.1", "setproctitle==1.3.8", "textual==8.2.8",
]
STATUS = {1: "killed", 3: "killed", 0: "survived", 5: "no tests", 33: "no tests",
          36: "timeout", 24: "timeout", -24: "timeout", 152: "timeout", 255: "timeout",
          -11: "segfault", -9: "segfault", 34: "skipped"}

UNIT_FIELDS = [
    "suite", "unit", "target", "mutants_total", "killed", "survived", "timeout", "no_tests",
    "other", "score_covered", "score_global", "seconds",
]
SUITE_FIELDS = ["suite", "scope", "mutants_total", "killed", "survived", "timeout", "no_tests",
                "score_covered", "score_global"]
MUTANT_FIELDS = ["suite", "unit", "mutant", "function", "status"]


def work_dir(settings: Settings) -> Path:
    return settings.project_root / "work"


def ensure_site(settings: Settings) -> Path:
    site = work_dir(settings) / "mutmut_site"
    if not (site / "mutmut").exists():
        site.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["uv", "pip", "install", "-q", "--python", str(settings.ha_python), "--target",
             str(site), "--no-deps", *SITE_PACKAGES],
            check=True,
        )
    return site


def _farm(src: Path, dst: Path, skip: set[str]) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        target = dst / entry.name
        if entry.name in skip or target.exists() or target.is_symlink():
            continue
        target.symlink_to(entry)


def _populate_tree(settings: Settings, root: Path, *, real_component: bool) -> None:
    """Symlink farm of homeassistant/ and tests/ under `root`."""
    ha = settings.ha_core_dir
    comp = settings.config["ha"]["component"]
    _farm(ha / "homeassistant", root / "homeassistant", {"components"})
    _farm(ha / "homeassistant/components", root / "homeassistant/components", {comp})
    _farm(ha / "tests", root / "tests", {"components"})
    _farm(ha / "tests/components", root / "tests/components", {comp})
    if real_component:
        (root / "homeassistant/components" / comp).mkdir(parents=True, exist_ok=True)
        (root / "tests/components" / comp).mkdir(parents=True, exist_ok=True)


def build_workspace(
    settings: Settings, test_files: list[Path], *, deselect: list[str], with_snapshots: bool
) -> Path:
    """Fresh workspace holding the given test files (and nothing else) for threshold."""
    comp = settings.config["ha"]["component"]
    ws = work_dir(settings) / "mutmut_ha"
    if ws.exists():
        shutil.rmtree(ws)
    ha = settings.ha_core_dir
    # homeassistant/: symlink farm. tests/: REAL copy (mutmut always copytree()s tests/ into
    # mutants/, which would follow symlinks and drag in all ~1200 other integrations' tests).
    _farm(ha / "homeassistant", ws / "homeassistant", {"components"})
    _farm(ha / "homeassistant/components", ws / "homeassistant/components", {comp})
    (ws / "homeassistant/components" / comp).mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "components")
    shutil.copytree(ha / "tests", ws / "tests", ignore=ignore, symlinks=True)
    (ws / "tests/components").mkdir(exist_ok=True)
    for f in (ha / "tests/components").glob("*.py"):
        shutil.copy2(f, ws / "tests/components" / f.name)
    shutil.copytree(
        settings.ha_core_dir / settings.config["ha"]["component_dir"],
        ws / "homeassistant/components" / comp,
        dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"),
    )
    tdir = ws / "tests/components" / comp
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "__init__.py").touch()
    for f in test_files:
        shutil.copy2(f, tdir / f.name)
    if with_snapshots:
        shutil.copytree(settings.developer_tests_dir / "snapshots", tdir / "snapshots",
                        dirs_exist_ok=True)
    # mutmut recreates mutants/ (source_paths + tests/); the rest of the `homeassistant`
    # package is symlinked in so that it resolves completely from inside mutants/.
    (ws / "mutants").mkdir()
    _farm(ha / "homeassistant", ws / "mutants/homeassistant", {"components"})
    _farm(ha / "homeassistant/components", ws / "mutants/homeassistant/components", {comp})
    pytest_cfg = _pytest_ini(settings)
    args = ['"-p", "no:sugar"', '"-p", "no:cacheprovider"', '"--timeout=120"']
    args += [f'"--deselect", "{d}"' for d in deselect]
    (ws / "pyproject.toml").write_text(
        pytest_cfg
        + "\n[tool.mutmut]\n"
        + f'source_paths = ["homeassistant/components/{comp}"]\n'
        + f'pytest_add_cli_args_test_selection = ["tests/components/{comp}"]\n'
        + f"pytest_add_cli_args = [{', '.join(args)}]\n"
        + "mutate_only_covered_lines = false\n",
        encoding="utf-8",
    )
    return ws


def _pytest_ini(settings: Settings) -> str:
    src = (settings.ha_core_dir / "pyproject.toml").read_text(encoding="utf-8")
    i = src.index("[tool.pytest.ini_options]")
    j = src.find("\n[tool.", i + 10)
    return src[i:j] if j != -1 else src[i:]


def parse_meta(ws: Path) -> dict[str, int | None]:
    import json

    out: dict[str, int | None] = {}
    for meta in (ws / "mutants").rglob("*.py.meta"):
        data = json.loads(meta.read_text(encoding="utf-8"))
        out.update({k: v for k, v in data.get("exit_code_by_key", {}).items()})
    return out


def function_of(mutant: str) -> str:
    return re.sub(r"__mutmut_\d+$", "", mutant.split(".")[-1]).removeprefix("x_")


def run_mutmut(settings: Settings, ws: Path, *, timeout: int = 3600) -> tuple[dict, float, str]:
    env = {**os.environ, "PYTHONPATH": str(ensure_site(settings))}
    n = str(settings.config["mutation"].get("max_children", 4))
    t0 = time.monotonic()
    proc = subprocess.run(
        [str(settings.ha_python), "-m", "mutmut", "run", "--max-children", n],
        cwd=ws, env=env, capture_output=True, text=True, timeout=timeout,
    )
    results = parse_meta(ws)
    return results, time.monotonic() - t0, proc.stdout[-2000:] + proc.stderr[-2000:]


def classify(results: dict) -> dict[str, str]:
    return {k: STATUS.get(v, "other") if v is not None else "no tests" for k, v in results.items()}


def unit_row(suite: str, unit: str, target: str, statuses: dict[str, str],
             total: int, seconds: float) -> dict:
    c = Counter(statuses.values())
    killed, survived = c["killed"], c["survived"]
    total = total or len(statuses)
    return {
        "suite": suite, "unit": unit, "target": target, "mutants_total": total,
        "killed": killed, "survived": survived, "timeout": c["timeout"],
        "no_tests": total - killed - survived - c["timeout"] - c["other"] - c["segfault"],
        "other": c["other"] + c["segfault"],
        "score_covered": round(killed / (killed + survived), 4) if killed + survived else 0.0,
        "score_global": round(killed / total, 4) if total else 0.0,
        "seconds": round(seconds, 1),
    }


def failing_deselects(settings: Settings, suite: str, unit: Path,
                      stable: set[tuple[str, str]] | None) -> list[str]:
    """pytest --deselect args for tests of `unit` that are not stably passing."""
    import csv

    path = settings.results_dir / "exec_tests.csv"
    comp_dir = settings.config["ha"]["developer_tests_dir"]
    names: set[str] = set()
    if path.exists():
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["suite"] == suite and r["unit"] == unit.name:
                    names.add(r["test"])
    return [
        f"{comp_dir}/{unit.name}::{t}" for t in sorted(names)
        if stable is not None and (unit.name, t) not in stable and t != "<collection>"
    ]


def run_mutation(
    settings: Settings, suite: str, units: list[Path], targets: dict[str, str],
    stable: set[tuple[str, str]] | None, *, with_snapshots: bool,
) -> list[dict]:
    unit_rows, mutant_rows, killed_by_unit = [], [], {}
    full_total = 0
    for unit in units:
        passing = None if stable is None else any(u == unit.name for u, _ in stable)
        if passing is False:  # no passing test at all: kills nothing
            statuses = {}
            secs = 0.0
        else:
            ws = build_workspace(
                settings, [unit], deselect=failing_deselects(settings, suite, unit, stable),
                with_snapshots=with_snapshots,
            )
            results, secs, tail = run_mutmut(settings, ws)
            statuses = classify(results)
            if not statuses:
                print(f"[mutation] {unit.name}: no mutant results\n{tail}", file=sys.stderr)
        full_total = max(full_total, len(statuses))
        unit_rows.append(
            unit_row(suite, unit.name, targets.get(unit.name, ""), statuses, full_total, secs)
        )
        killed_by_unit[unit.name] = {m for m, s in statuses.items() if s == "killed"}
        mutant_rows += [
            {"suite": suite, "unit": unit.name, "mutant": m, "function": function_of(m),
             "status": s} for m, s in sorted(statuses.items())
        ]
    for r in unit_rows:  # units run before the total was known (or empty) get the final total
        r["mutants_total"] = full_total
        r["no_tests"] = full_total - r["killed"] - r["survived"] - r["timeout"] - r["other"]
        r["score_global"] = round(r["killed"] / full_total, 4) if full_total else 0.0
    suite_rows = _suite_rows(suite, unit_rows, mutant_rows, targets, full_total)
    res = settings.results_dir
    write_keyed_csv(res / "mutation_units.csv", UNIT_FIELDS, unit_rows)
    write_keyed_csv(res / "mutation_suites.csv", SUITE_FIELDS, suite_rows)
    write_keyed_csv(res / "mutation_mutants.csv", MUTANT_FIELDS, mutant_rows)
    return suite_rows


def _suite_rows(suite, unit_rows, mutant_rows, targets, total) -> list[dict]:
    def agg(scope: str, names: set[str]) -> dict:
        best: dict[str, str] = {}
        rank = {"killed": 3, "survived": 2, "timeout": 1}
        for r in mutant_rows:
            cur = rank.get(best.get(r["mutant"]), 0)
            if r["unit"] in names and rank.get(r["status"], 0) >= cur:
                best[r["mutant"]] = r["status"]
        c = Counter(best.values())
        k, s = c["killed"], c["survived"]
        return {
            "suite": suite, "scope": scope, "mutants_total": total, "killed": k, "survived": s,
            "timeout": c["timeout"], "no_tests": total - k - s - c["timeout"],
            "score_covered": round(k / (k + s), 4) if k + s else 0.0,
            "score_global": round(k / total, 4) if total else 0.0,
        }

    names = {r["unit"] for r in unit_rows}
    rows = [agg("all", names)]
    for tgt in sorted({t for t in targets.values() if t}):
        rows.append(agg(f"target:{tgt}", {u for u, t in targets.items() if t == tgt}))
    return rows
