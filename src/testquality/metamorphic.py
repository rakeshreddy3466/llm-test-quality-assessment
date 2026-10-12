"""Metamorphic experiment (RQ3): variants vs the noise floor between repeated samples.

Variants (all for the binary_sensor target, k = 5 samples each):
  mr1a mr1b mr1c  paraphrased prompt
  mr2             local variables of the shown source renamed
  mr3             functions / methods of the shown source reordered
  mr4             comments of the shown source stripped
Baseline: the 5 original `v1` samples of the same target (the noise floor is the spread
between those repeated samples).
"""

from __future__ import annotations

import csv
import itertools
import json
import statistics
from pathlib import Path

from .config import Settings
from .executor import write_keyed_csv

VARIANTS = ["mr1a", "mr1b", "mr1c", "mr2", "mr3", "mr4"]
BASELINE_SUITE = "main_sonnet55_v1"
TARGET = "binary_sensor"
METRICS = ["valid_tests", "line_cov", "branch_cov", "mut_global", "mut_covered",
           "trace_name", "smell_density"]
PAIR_FIELDS = ["variant", "metric", "n_baseline", "n_variant", "baseline_mean", "baseline_sd",
               "baseline_min", "baseline_max", "variant_mean", "within_baseline_range",
               "mwu_u", "mwu_p", "cliffs_delta", "effect_size"]
JACCARD_FIELDS = ["variant", "kind", "noise_floor_mean", "cross_mean", "n_noise", "n_cross",
                  "mwu_p", "cliffs_delta"]


def cliffs_delta(a: list[float], b: list[float]) -> float:
    """P(a > b) - P(a < b)."""
    if not a or not b:
        return float("nan")
    gt = sum(x > y for x in a for y in b)
    lt = sum(x < y for x in a for y in b)
    return (gt - lt) / (len(a) * len(b))


def delta_label(d: float) -> str:
    d = abs(d)
    if d != d:  # NaN
        return "n/a"
    for limit, label in ((0.147, "negligible"), (0.33, "small"), (0.474, "medium")):
        if d < limit:
            return label
    return "large"


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 1.0


def mann_whitney(a: list[float], b: list[float]) -> tuple[float, float]:
    from scipy.stats import mannwhitneyu

    if len(set(a) | set(b)) <= 1:  # identical constant samples: no difference at all
        return float(len(a) * len(b)) / 2, 1.0
    res = mannwhitneyu(a, b, alternative="two-sided")
    return float(res.statistic), float(res.pvalue)


def _csv(path: Path, suite: str) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["suite"] == suite]


def unit_metrics(settings: Settings, suite: str, target: str = TARGET) -> dict[str, dict]:
    """unit -> metrics and sets, for the units of `target`."""
    res = settings.results_dir
    mani = json.loads((settings.runs_dir / suite / "manifest.json").read_text())
    units = {s["file"] for s in mani["samples"] if s["file"] and s["target"] == target}
    cov = {r["unit"]: r for r in _csv(res / "coverage_units.csv", suite)}
    mut = {r["unit"]: r for r in _csv(res / "mutation_units.csv", suite)}
    killed: dict[str, set] = {}
    for r in _csv(res / "mutation_mutants.csv", suite):
        if r["status"] == "killed":
            killed.setdefault(r["unit"], set()).add(r["mutant"])
    trace: dict[str, list[float]] = {}
    for r in _csv(res / "trace_tests.csv", suite):
        if r["valid"] == "1":
            trace.setdefault(r["unit"], []).append(float(r["trace_name"]))
    smell: dict[str, list[int]] = {}
    for r in _csv(res / "smells_tests.csv", suite):
        if r["valid"] == "1":
            smell.setdefault(r["unit"], []).append(int(r["total"]))
    cache_path = res / "cache" / f"coverage_{suite}.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    out: dict[str, dict] = {}
    for u in sorted(units):
        lines = set()
        for entry in cache.get(u, {}).get("tests", {}).values():
            for fname, f in entry.items():
                lines |= {(fname, ln) for ln in f["lines"]}
        c, m = cov.get(u), mut.get(u)
        out[u] = {
            "valid_tests": float(c["tests_passing"]) if c else 0.0,
            "line_cov": float(c["line_cov"]) if c else 0.0,
            "branch_cov": float(c["branch_cov"]) if c else 0.0,
            "mut_global": float(m["score_global"]) if m else 0.0,
            "mut_covered": float(m["score_covered"]) if m else 0.0,
            "trace_name": statistics.fmean(trace[u]) if trace.get(u) else 0.0,
            "smell_density": statistics.fmean(smell[u]) if smell.get(u) else 0.0,
            "lines": lines, "killed": killed.get(u, set()),
        }
    return out


def compare(
    base: dict[str, dict], variant: dict[str, dict], name: str
) -> tuple[list[dict], list[dict]]:
    pair_rows, jac_rows = [], []
    for metric in METRICS:
        a = [u[metric] for u in base.values()]
        b = [u[metric] for u in variant.values()]
        if not a or not b:
            continue
        sd = statistics.stdev(a) if len(a) > 1 else 0.0
        u_stat, p = mann_whitney(b, a)
        d = cliffs_delta(b, a)
        pair_rows.append({
            "variant": name, "metric": metric, "n_baseline": len(a), "n_variant": len(b),
            "baseline_mean": round(statistics.fmean(a), 4), "baseline_sd": round(sd, 4),
            "baseline_min": min(a), "baseline_max": max(a),
            "variant_mean": round(statistics.fmean(b), 4),
            "within_baseline_range": round(sum(min(a) <= x <= max(a) for x in b) / len(b), 3),
            "mwu_u": round(u_stat, 3), "mwu_p": round(p, 4), "cliffs_delta": round(d, 4),
            "effect_size": delta_label(d),
        })
    for kind in ("lines", "killed"):
        noise = [jaccard(x[kind], y[kind])
                 for x, y in itertools.combinations(base.values(), 2)]
        cross = [jaccard(x[kind], y[kind]) for x in variant.values() for y in base.values()]
        if not noise or not cross:
            continue
        _, p = mann_whitney(cross, noise)
        jac_rows.append({
            "variant": name, "kind": f"jaccard_{kind}",
            "noise_floor_mean": round(statistics.fmean(noise), 4),
            "cross_mean": round(statistics.fmean(cross), 4),
            "n_noise": len(noise), "n_cross": len(cross), "mwu_p": round(p, 4),
            "cliffs_delta": round(cliffs_delta(cross, noise), 4),
        })
    return pair_rows, jac_rows


def run_compare(settings: Settings, variants: list[str] | None = None) -> None:
    base = unit_metrics(settings, BASELINE_SUITE)
    pair_all, jac_all = [], []
    pooled: dict[str, dict] = {}
    for v in variants or VARIANTS:
        suite = f"mr_{v}_{TARGET}"
        if not (settings.runs_dir / suite / "manifest.json").exists():
            continue
        vm = unit_metrics(settings, suite)
        p, j = compare(base, vm, v)
        pair_all += p
        jac_all += j
        if v.startswith("mr1"):
            pooled.update({f"{v}:{k}": m for k, m in vm.items()})
    if pooled:
        p, j = compare(base, pooled, "mr1_pooled")
        pair_all += p
        jac_all += j
    res = settings.results_dir
    keyed = [{**r, "suite": r["variant"]} for r in pair_all]
    write_keyed_csv(res / "mr_metrics.csv", ["suite", *PAIR_FIELDS], keyed)
    keyed = [{**r, "suite": r["variant"]} for r in jac_all]
    write_keyed_csv(res / "mr_jaccard.csv", ["suite", *JACCARD_FIELDS], keyed)
