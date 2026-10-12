"""Traceability scoring (see docs/metrics.md section 4)."""

from __future__ import annotations

import ast
import contextlib
import csv
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .executor import run_pytest, staged_files, write_keyed_csv

PLUGIN_DIR = Path(__file__).with_name("plugins")
TRACE_FIELDS = [
    "suite", "unit", "test", "valid", "has_assert", "name_target", "cov_target", "n_called",
    "declared_target", "trace_name", "trace_declared",
]
SUMMARY_FIELDS = [
    "suite", "scope", "tests", "valid_tests", "trace_name_mean", "trace_declared_mean",
    "declared_present_rate", "no_assert_rate", "no_sut_call_rate",
]
TARGET_RE = re.compile(r"Target:\s*(.+)", re.IGNORECASE)
STOP = {"test", "async", "the", "a", "an", "of", "is", "are", "for", "when", "with", "and"}


def tokens(name: str) -> set[str]:
    name = re.sub(r"\[.*\]$", "", name)
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    out = set()
    for t in re.split(r"[_.\s]+", name.lower()):
        if not t or t in STOP:
            continue
        out.add(t[:-1] if len(t) > 3 and t.endswith("s") else t)
    return out


def similarity(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def sut_candidates(component_dir: Path) -> list[str]:
    """`module:qualname` for every class, function and method of the component."""
    out: list[str] = []
    for path in sorted(component_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        mod = path.stem
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                out.append(f"{mod}:{node.name}")
            elif isinstance(node, ast.ClassDef):
                out.append(f"{mod}:{node.name}")
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                        out.append(f"{mod}:{node.name}.{sub.name}")
    return out


def name_target(test_name: str, candidates: list[str], min_sim: float = 0.2) -> str | None:
    tt = tokens(test_name)
    best: tuple[float, str] | None = None
    for c in candidates:
        sim = similarity(tt, tokens(c.split(":", 1)[1]))
        if sim >= min_sim and (best is None or (sim, -len(c)) > (best[0], -len(best[1]))):
            best = (sim, c)
    return best[1] if best else None


def declared_target(docstring: str | None, candidates: list[str]) -> str | None:
    """Resolve the docstring's `Target:` to a candidate, or None if absent / unknown."""
    if not docstring:
        return None
    m = TARGET_RE.search(docstring)
    if not m:
        return None
    raw = re.sub(r"[`'\"()]", "", m.group(1)).strip().rstrip(".")
    raw = raw.split(",")[0].split(" ")[0]
    if not raw:
        return None
    exact = [c for c in candidates if c.split(":", 1)[1] == raw or c == raw]
    if exact:
        return exact[0]
    suffix = [c for c in candidates if c.endswith("." + raw.split(".")[-1])
              or c.split(":", 1)[1] == raw.split(".")[-1]]
    if len(suffix) >= 1 and "." not in raw:
        return suffix[0]
    qual = raw.split(".")[-2:] if "." in raw else [raw]
    tail = ".".join(qual)
    hits = [c for c in candidates if c.split(":", 1)[1] == tail]
    return hits[0] if hits else None


@dataclass
class TraceInfo:
    has_assert: bool
    called: list[str]
    last: str | None


def score(claimed: str | None, info: TraceInfo | None) -> float:
    """0 / 0.5 / 1 as defined in docs/metrics.md."""
    if claimed is None or info is None or not info.has_assert or info.last is None:
        return 0.0
    if claimed == info.last:
        return 1.0
    cls = info.last.split(".")[0] if "." in info.last else None
    if claimed in info.called or (cls and claimed == cls):
        return 0.5
    return 0.0


def test_docstrings(path: Path) -> dict[str, str | None]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        n.name: ast.get_docstring(n)
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test_")
    }


def trace_unit(settings: Settings, rel_path: str) -> dict[str, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "trace.json"
        _, _, _ = run_pytest(
            settings, [rel_path],
            extra_args=["-p", "_tq_trace", "--timeout=120"],
            env={"PYTHONPATH": str(PLUGIN_DIR), "TQ_TRACE_OUT": str(out),
                 "TQ_COMPONENT_PART": settings.config["ha"]["component_dir"] + "/"},
            timeout=settings.config["execution"]["timeout_seconds"],
        )
        return json.loads(out.read_text()) if out.exists() else {}


def run_traceability(
    settings: Settings, suite: str, units: list[Path], *, staging_id: str | None,
    stable: set[tuple[str, str]] | None, has_declaration: bool,
) -> list[dict]:
    ha_rel = settings.config["ha"]["developer_tests_dir"]
    cands = sut_candidates(settings.ha_core_dir / settings.config["ha"]["component_dir"])
    rows: list[dict] = []
    for unit in units:
        ctx = (staged_files(settings, staging_id, [unit]) if staging_id
               else contextlib.nullcontext(None))
        with ctx as dest:
            rel = (f"{ha_rel}/{unit.name}" if dest is None
                   else str(dest.relative_to(settings.ha_core_dir) / unit.name))
            traced = trace_unit(settings, rel)
        docs = test_docstrings(unit)
        for node_id, t in traced.items():
            test = node_id.partition("::")[2]
            base = re.sub(r"\[.*\]$", "", test)
            info = TraceInfo(t["has_assert"], t["called"], t["last"])
            nt = name_target(base, cands)
            dt = declared_target(docs.get(base), cands) if has_declaration else None
            rows.append({
                "suite": suite, "unit": unit.name, "test": test,
                "valid": int(stable is None or (unit.name, test) in stable),
                "has_assert": int(t["has_assert"]), "name_target": nt or "",
                "cov_target": t["last"] or "", "n_called": len(t["called"]),
                "declared_target": dt or ("" if has_declaration else "n/a"),
                "trace_name": score(nt, info),
                "trace_declared": score(dt, info) if has_declaration else "",
            })
    write_keyed_csv(settings.results_dir / "trace_tests.csv", TRACE_FIELDS, rows)
    summary = summarise(suite, rows, has_declaration)
    write_keyed_csv(settings.results_dir / "trace_summary.csv", SUMMARY_FIELDS, summary)
    return summary


def summarise(suite: str, rows: list[dict], has_declaration: bool) -> list[dict]:
    def one(scope: str, sel: list[dict]) -> dict:
        valid = [r for r in sel if r["valid"]]
        n = len(valid)
        def mean(xs):
            return round(sum(xs) / len(xs), 4) if xs else ""

        def rate(k, total):
            return round(k / total, 4) if total else ""

        return {
            "suite": suite, "scope": scope, "tests": len(sel), "valid_tests": n,
            "trace_name_mean": mean([float(r["trace_name"]) for r in valid]),
            "trace_declared_mean": (
                mean([float(r["trace_declared"]) for r in valid]) if has_declaration else ""
            ),
            "declared_present_rate": (
                round(sum(1 for r in valid if r["declared_target"]) / n, 4) if n and has_declaration
                else ""
            ),
            "no_assert_rate": rate(sum(1 for r in valid if not r["has_assert"]), n),
            "no_sut_call_rate": rate(sum(1 for r in valid if not r["cov_target"]), n),
        }

    out = [one("all", rows)]
    return out


def load_rows(path: Path, suite: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["suite"] == suite]
