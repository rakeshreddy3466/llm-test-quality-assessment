"""Suite and per-test coverage of the threshold component.

Coverage is measured inside the Home Assistant tree with pytest-cov and
`--cov-context=test`. NOTE: on Python 3.12+ coverage's default `sysmon` core drops per-test
contexts (each line is only reported once), so `COVERAGE_CORE=ctrace` is forced.
Only passing tests count towards coverage.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .config import Settings
from .executor import (
    TestOutcome,
    run_pytest,
    staged_files,
    write_keyed_csv,
)

EXTRACT = Path(__file__).with_name("_cov_extract.py")
COV_ENV = {"COVERAGE_CORE": "ctrace"}

UNIT_FIELDS = [
    "suite", "unit", "target", "tests_passing", "tests_total", "line_cov", "branch_cov",
    "lines_covered", "lines_total", "branches_covered", "branches_total",
]
SUITE_FIELDS = [
    "suite", "scope", "line_cov", "branch_cov", "lines_covered", "lines_total",
    "branches_covered", "branches_total", "tests_passing",
]
TEST_FIELDS = [
    "suite", "unit", "test", "lines_covered", "branches_covered", "unique_lines", "lines",
]


def measure_unit(
    settings: Settings, rel_path: str, extra: list[str] | None = None, timeout: int = 600
) -> tuple[dict[str, Any], list[TestOutcome]]:
    """Run one test file under coverage; return the extracted coverage JSON and outcomes."""
    comp = settings.config["ha"]["component_dir"]
    with tempfile.TemporaryDirectory() as tmp:
        data_file = str(Path(tmp) / "cov.db")
        outcomes, proc, _ = run_pytest(
            settings,
            [rel_path],
            extra_args=[
                "--timeout=120", "--cov=" + comp.replace("/", "."), "--cov-branch",
                "--cov-context=test", "--cov-report=", *(extra or []),
            ],
            timeout=timeout,
            env={**COV_ENV, "COVERAGE_FILE": data_file},
        )
        out = str(Path(tmp) / "cov.json")
        if not Path(data_file).exists():
            return {"files": {}, "tests": {}}, outcomes
        subprocess.run(
            [str(settings.ha_python), "-I", str(EXTRACT), data_file, out, comp],
            cwd=settings.ha_core_dir, check=True, capture_output=True, text=True,
        )
        return json.loads(Path(out).read_text()), outcomes


def _short_test_id(node_id: str) -> tuple[str, str]:
    path, _, name = node_id.partition("::")
    return Path(path).name, name


def _union(entries: list[dict], files: dict) -> tuple[int, int, int, int]:
    """(lines covered, lines total, branches covered, branches total) over given tests."""
    lines_total = sum(len(f["statements"]) for f in files.values())
    br_total = sum(len(f["branch_arcs"]) for f in files.values())
    cl = cb = 0
    for fname, f in files.items():
        stm = set(f["statements"])
        lines: set[int] = set()
        arcs: set[tuple] = set()
        for e in entries:
            if fname in e:
                lines |= set(e[fname]["lines"])
                arcs |= {tuple(a) for a in e[fname]["arcs"]}
        cl += len(lines & stm)
        cb += len(arcs)
    return cl, lines_total, cb, br_total


def _pct(a: int, b: int) -> float:
    return round(a / b, 4) if b else 0.0


def analyse_unit(
    suite: str, unit: Path, cov: dict, outcomes: list[TestOutcome], stable: set | None,
    target: str = "",
) -> tuple[dict, list[dict], list[dict]]:
    """Per-unit row, per-test rows, plus entries (passing tests only) for suite unions."""
    passed = {
        o.test for o in outcomes if o.outcome == "passed"
        and (stable is None or (unit.name, o.test) in stable)
    }
    total = len([o for o in outcomes if o.outcome != "collect_error"])
    by_name = {name: {} for name in passed}  # passing tests that touch no threshold code
    for node_id, entry in cov["tests"].items():
        fname, name = _short_test_id(node_id)
        if fname == unit.name and name in passed:
            by_name[name] = entry
    files = cov["files"]
    import_entry = cov["tests"].get("__import__", {})
    # import-time lines count for the unit as soon as one of its tests passes
    unit_entries = ([import_entry] if by_name and import_entry else []) + list(by_name.values())
    cl, lt, cb, bt = _union(unit_entries, files)
    unit_row = {
        "suite": suite, "unit": unit.name, "target": target, "tests_passing": len(by_name),
        "tests_total": total, "line_cov": _pct(cl, lt), "branch_cov": _pct(cb, bt),
        "lines_covered": cl, "lines_total": lt, "branches_covered": cb, "branches_total": bt,
    }
    line_owner: Counter = Counter()
    per_test_lines = {}
    for name, entry in by_name.items():
        ls = {(fn, ln) for fn, f in entry.items() for ln in f["lines"]
              if ln in set(files[fn]["statements"])}
        per_test_lines[name] = ls
        line_owner.update(ls)
    test_rows = []
    for name, entry in sorted(by_name.items()):
        ls = per_test_lines[name]
        test_rows.append({
            "suite": suite, "unit": unit.name, "test": name, "lines_covered": len(ls),
            "branches_covered": sum(len(f["arcs"]) for f in entry.values()),
            "unique_lines": sum(1 for x in ls if line_owner[x] == 1),
            "lines": " ".join(f"{fn.split('.')[0]}:{ln}" for fn, ln in sorted(ls)),
        })
    return unit_row, test_rows, [{"unit": unit.name, "entries": unit_entries,
                                   "files": files, "tests": by_name}]


def run_coverage(
    settings: Settings, suite: str, units: list[Path], *, staging_id: str | None,
    stable: set | None = None, targets: dict[str, str] | None = None,
) -> list[dict]:
    """Measure every unit; write results/coverage_*.csv and a JSON cache for later phases."""
    ha_rel = settings.config["ha"]["developer_tests_dir"]
    unit_rows, test_rows, parts, cache = [], [], [], {}
    for unit in units:
        ctx = (
            staged_files(settings, staging_id, [unit]) if staging_id
            else contextlib.nullcontext(None)
        )
        with ctx as dest:
            rel = (
                f"{ha_rel}/{unit.name}" if dest is None
                else str(dest.relative_to(settings.ha_core_dir) / unit.name)
            )
            cov, outcomes = measure_unit(
                settings, rel, timeout=settings.config["execution"]["timeout_seconds"]
            )
        if not cov["files"]:
            unit_rows.append({"suite": suite, "unit": unit.name,
                              "target": (targets or {}).get(unit.name, ""), "tests_passing": 0,
                              "tests_total": 0, "line_cov": 0, "branch_cov": 0,
                              "lines_covered": 0, "lines_total": 0, "branches_covered": 0,
                              "branches_total": 0})
            continue
        urow, trows, part = analyse_unit(
            suite, unit, cov, outcomes, stable, (targets or {}).get(unit.name, "")
        )
        unit_rows.append(urow)
        test_rows += trows
        parts += part
        cache[unit.name] = {
            "tests": {n: e for n, e in part[0]["tests"].items()},
            "files": cov["files"],
        }
    res = settings.results_dir
    suite_rows = []
    if parts:
        files = parts[0]["files"]
        all_entries = [e for p in parts for e in p["entries"]]
        cl, lt, cb, bt = _union(all_entries, files)
        suite_rows.append({"suite": suite, "scope": "all", "line_cov": _pct(cl, lt),
                           "branch_cov": _pct(cb, bt), "lines_covered": cl, "lines_total": lt,
                           "branches_covered": cb, "branches_total": bt,
                           "tests_passing": sum(len(p["tests"]) for p in parts)})
        for tgt in sorted({r["target"] for r in unit_rows if r["target"]}):
            names = {u for u, t in (targets or {}).items() if t == tgt}
            ents = [e for p in parts if p["unit"] in names for e in p["entries"]]
            cl, lt, cb, bt = _union(ents, files)
            suite_rows.append({"suite": suite, "scope": f"target:{tgt}", "line_cov": _pct(cl, lt),
                               "branch_cov": _pct(cb, bt), "lines_covered": cl, "lines_total": lt,
                               "branches_covered": cb, "branches_total": bt,
                               "tests_passing": sum(
                                   len(p["tests"]) for p in parts if p["unit"] in names)})
    write_keyed_csv(res / "coverage_units.csv", UNIT_FIELDS, unit_rows)
    write_keyed_csv(res / "coverage_suites.csv", SUITE_FIELDS, suite_rows)
    write_keyed_csv(res / "coverage_per_test.csv", TEST_FIELDS, test_rows)
    cache_dir = res / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"coverage_{suite}.json").write_text(json.dumps(cache), encoding="utf-8")
    return suite_rows


def stable_pass_set(settings: Settings, suite: str) -> set[tuple[str, str]] | None:
    """(unit, test) pairs that passed in every repeat of phase 3, or None if not measured."""
    import csv

    path = settings.results_dir / "exec_tests.csv"
    if not path.exists():
        return None
    outcomes: dict[tuple[str, str], list[str]] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["suite"] == suite:
                outcomes.setdefault((r["unit"], r["test"]), []).append(r["outcome"])
    if not outcomes:
        return None
    return {k for k, v in outcomes.items() if set(v) == {"passed"}}
