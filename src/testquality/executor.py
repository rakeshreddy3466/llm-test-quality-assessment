"""Run test files inside the Home Assistant tree (subprocess) and parse the results.

Generated files are staged under tests/components/threshold/_llm_generated/<run_id>/ and
always removed afterwards. No other Home Assistant file is touched.
"""

from __future__ import annotations

import contextlib
import csv
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

ERROR_TYPES = (
    "SyntaxError", "ModuleNotFoundError", "ImportError", "FixtureLookupError", "AssertionError",
    "AttributeError", "TypeError", "KeyError", "ValueError", "TimeoutError", "RuntimeError",
)


@dataclass
class TestOutcome:
    __test__ = False  # not a pytest class

    unit: str          # test file (basename)
    test: str          # test function name ("<collection>" for file-level errors)
    outcome: str       # passed | failed | error | skipped | collect_error | timeout
    error_type: str = ""
    message: str = ""


def classify_error(type_attr: str, message: str, text: str = "") -> str:
    blob = f"{type_attr} {message} {text}"
    if "fixture" in blob and "not found" in blob:
        return "FixtureLookupError"
    for name in ERROR_TYPES:
        if name in type_attr or name in blob:
            return name
    if "assert" in blob.lower():
        return "AssertionError"
    return "Other"


def parse_junit(xml_path: Path, unit_for_classname=None) -> list[TestOutcome]:
    """Parse a pytest junit xml. File-level collection errors become 'collect_error'."""
    out: list[TestOutcome] = []
    if not xml_path.exists():
        return out
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        classname = case.get("classname", "")
        name = case.get("name", "")
        unit = classname.split(".")[-1] if classname else name
        if unit.startswith("Test"):  # class-based tests: module is the previous component
            unit = classname.split(".")[-2]
        unit_file = f"{unit}.py"
        node = next((c for c in case if c.tag in ("failure", "error", "skipped")), None)
        if node is None:
            out.append(TestOutcome(unit_file, name, "passed"))
            continue
        msg = (node.get("message") or "")[:300]
        etype = classify_error(node.get("type") or "", msg, (node.text or "")[-1500:])
        if node.tag == "skipped":
            out.append(TestOutcome(unit_file, name, "skipped", "", msg))
        elif node.tag == "failure":
            out.append(TestOutcome(unit_file, name, "failed", etype, msg))
        else:
            is_collect = name == "" or case.get("classname", "") == ""
            out.append(TestOutcome(unit_file, name or "<collection>",
                                   "collect_error" if is_collect else "error", etype, msg))
    return out


@contextlib.contextmanager
def staged_files(settings: Settings, run_id: str, files: list[Path]) -> Iterator[Path]:
    """Copy files into the HA tree, yield the staging dir, always delete it."""
    dest = settings.generated_tests_dir / run_id
    dest.mkdir(parents=True, exist_ok=True)
    try:
        (settings.generated_tests_dir / "__init__.py").touch()
        (dest / "__init__.py").touch()
        for f in files:
            shutil.copy2(f, dest / f.name)
        yield dest
    finally:
        shutil.rmtree(dest, ignore_errors=True)
        with contextlib.suppress(OSError):
            subdirs = [
                d for d in settings.generated_tests_dir.iterdir()
                if d.is_dir() and d.name != "__pycache__"
            ]
            if not subdirs:
                shutil.rmtree(settings.generated_tests_dir, ignore_errors=True)


def run_pytest(
    settings: Settings,
    paths: list[str],
    *,
    extra_args: list[str] | None = None,
    timeout: int = 600,
) -> tuple[list[TestOutcome], subprocess.CompletedProcess | None, float]:
    """Run pytest in the HA tree. `paths` are relative to the HA root."""
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "junit.xml"
        cmd = [
            str(settings.ha_python), "-m", "pytest", *paths,
            "-p", "no:cacheprovider", "-p", "no:sugar", "-q", "--no-header", f"--junitxml={xml}",
            *(extra_args or []),
        ]
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd, cwd=settings.ha_core_dir, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return [TestOutcome(Path(paths[0]).name, "<suite>", "timeout")], None, timeout
        return parse_junit(xml), proc, time.monotonic() - t0


# ---------------------------------------------------------------------------------------------
# Suite level execution and metrics
# ---------------------------------------------------------------------------------------------
TEST_FIELDS = ["suite", "unit", "test", "repeat", "outcome", "error_type"]
SUMMARY_FIELDS = [
    "suite", "units_requested", "units_collected", "collect_rate", "tests_collected",
    "pass_rate_mean", "pass_rate_min", "pass_rate_max", "stable_pass_rate", "flaky_tests",
    "flaky_rate", "repeats", "seconds_mean",
]


def developer_units(settings: Settings) -> list[Path]:
    return sorted(settings.developer_tests_dir.glob("test_*.py"))


def execute_units(
    settings: Settings, suite: str, units: list[Path], *, repeats: int, timeout: int,
    staging_id: str | None = None,
) -> tuple[list[dict], dict]:
    """Run every unit `repeats` times (one pytest process per unit per repeat)."""
    rows: list[dict] = []
    secs: list[float] = []
    ha_rel = settings.config["ha"]["developer_tests_dir"]
    for rep in range(1, repeats + 1):
        t_rep = 0.0
        for unit in units:
            ctx = (
                staged_files(settings, staging_id, [unit]) if staging_id
                else contextlib.nullcontext(None)
            )
            with ctx as dest:
                if dest is None:
                    rel = f"{ha_rel}/{unit.name}"
                else:
                    rel = str(dest.relative_to(settings.ha_core_dir) / unit.name)
                outcomes, _, dt = run_pytest(
                    settings, [rel], extra_args=["--timeout=120"], timeout=timeout
                )
            t_rep += dt
            if not outcomes:  # pytest produced no junit (crash): treat as collection error
                outcomes = [TestOutcome(unit.name, "<collection>", "collect_error", "Other")]
            for o in outcomes:
                rows.append({"suite": suite, "unit": unit.name, "test": o.test, "repeat": rep,
                             "outcome": o.outcome, "error_type": o.error_type})
        secs.append(t_rep)
    return rows, {"seconds": secs}


def summarise(
    suite: str, rows: list[dict], units_requested: int, repeats: int, secs: list[float]
) -> dict:
    by_test: dict[tuple, list[str]] = defaultdict(list)
    for r in rows:
        if r["outcome"] in ("collect_error", "timeout"):
            continue
        by_test[(r["unit"], r["test"])].append(r["outcome"])
    bad = ("collect_error", "timeout")
    collected_units = {r["unit"] for r in rows if r["repeat"] == 1 and r["outcome"] not in bad}
    per_rep_rates = []
    for rep in range(1, repeats + 1):
        ran = [
            r for r in rows
            if r["repeat"] == rep and r["outcome"] not in (*bad, "skipped")
        ]
        per_rep_rates.append(sum(r["outcome"] == "passed" for r in ran) / len(ran) if ran else 0.0)
    n_tests = len(by_test)
    stable = sum(1 for v in by_test.values() if len(v) == repeats and set(v) == {"passed"})
    flaky = sum(1 for v in by_test.values() if len(set(v)) > 1)
    return {
        "suite": suite, "units_requested": units_requested,
        "units_collected": len(collected_units),
        "collect_rate": round(len(collected_units) / units_requested, 4) if units_requested else 0,
        "tests_collected": n_tests,
        "pass_rate_mean": round(sum(per_rep_rates) / len(per_rep_rates), 4),
        "pass_rate_min": round(min(per_rep_rates), 4),
        "pass_rate_max": round(max(per_rep_rates), 4),
        "stable_pass_rate": round(stable / n_tests, 4) if n_tests else 0,
        "flaky_tests": flaky, "flaky_rate": round(flaky / n_tests, 4) if n_tests else 0,
        "repeats": repeats, "seconds_mean": round(sum(secs) / len(secs), 2) if secs else 0,
    }


def error_counts(suite: str, rows: list[dict]) -> list[dict]:
    first: dict[tuple, str] = {}
    for r in rows:
        if r["outcome"] in ("failed", "error", "collect_error", "timeout"):
            first.setdefault((r["unit"], r["test"]), r["error_type"] or r["outcome"])
    counts = Counter(first.values()).most_common()
    return [{"suite": suite, "error_type": k, "count": v} for k, v in counts]


def write_keyed_csv(
    path: Path, fields: list[str], new_rows: list[dict], key: str = "suite"
) -> None:
    """Replace all rows for the suites present in `new_rows`, keep the rest."""
    keep: list[dict] = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as fh:
            keep = list(csv.DictReader(fh))
    replaced = {r[key] for r in new_rows}
    keep = [r for r in keep if r[key] not in replaced]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(keep + new_rows)


def run_executability(
    settings: Settings, suite: str, units: list[Path], *, repeats: int, timeout: int,
    staging_id: str | None, units_requested: int | None = None,
) -> dict:
    rows, meta = execute_units(
        settings, suite, units, repeats=repeats, timeout=timeout, staging_id=staging_id
    )
    n_req = units_requested or len(units)
    summary = summarise(suite, rows, n_req, repeats, meta["seconds"])
    res = settings.results_dir
    write_keyed_csv(res / "exec_tests.csv", TEST_FIELDS, rows)
    write_keyed_csv(res / "exec_summary.csv", SUMMARY_FIELDS, [summary])
    err_fields = ["suite", "error_type", "count"]
    write_keyed_csv(res / "exec_errors.csv", err_fields, error_counts(suite, rows))
    return summary
