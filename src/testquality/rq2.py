"""RQ2: agreement between automatic scores and the manual ratings (needs the rated file)."""

from __future__ import annotations

import csv
from pathlib import Path

SCALES = {  # manual scale -> automatic column in results/rq2_auto.csv
    "relevance": "auto_relevance",
    "clarity": "auto_clarity",
    "maintainability": "auto_maintainability",
    "oracle_strength": "auto_oracle",
}


def weighted_kappa(a: list[int], b: list[int], k: int = 5) -> float:
    """Linearly weighted Cohen's kappa for ratings 1..k."""
    n = len(a)
    if n == 0:
        return float("nan")
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b, strict=True):
        obs[x - 1][y - 1] += 1 / n
    ra = [sum(obs[i]) for i in range(k)]
    rb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    w = [[abs(i - j) / (k - 1) for j in range(k)] for i in range(k)]
    num = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k))
    den = sum(w[i][j] * ra[i] * rb[j] for i in range(k) for j in range(k))
    return 1.0 - num / den if den else float("nan")


def agreement_rows(rated: Path, auto: Path) -> list[dict]:
    """One dict per manual scale: n, rho, p, kappa (None when undefined)."""
    from scipy.stats import spearmanr

    with open(rated, newline="", encoding="utf-8") as fh:
        manual = {r["item_id"]: r for r in csv.DictReader(fh)}
    with open(auto, newline="", encoding="utf-8") as fh:
        autos = {r["item_id"]: r for r in csv.DictReader(fh)}
    out = []
    for scale, col in SCALES.items():
        pairs = []
        for item, m in manual.items():
            try:
                pairs.append((int(m[scale]), int(float(autos[item][col]))))
            except (KeyError, ValueError):
                continue
        x, y = [p[0] for p in pairs], [p[1] for p in pairs]
        rec = {"scale": scale, "n": len(pairs), "rho": None, "p": None, "kappa": None,
               "status": "ok"}
        if len(pairs) < 3:
            rec["status"] = "pending"
        elif len(set(x)) < 2 or len(set(y)) < 2:
            rec["status"] = "undefined (constant ratings)"
        else:
            rho, p = spearmanr(x, y)
            rec.update(rho=float(rho), p=float(p), kappa=weighted_kappa(x, y))
        out.append(rec)
    return out


def agreement_table(rated: Path, auto: Path) -> str:
    lines = ["| Scale | n | Spearman rho | p | Weighted kappa |", "|---|---|---|---|---|"]
    for r in agreement_rows(rated, auto):
        if r["status"] == "ok":
            lines.append(f"| {r['scale']} | {r['n']} | {r['rho']:.3f} | {r['p']:.3f} | "
                         f"{r['kappa']:.3f} |")
        else:
            lines.append(f"| {r['scale']} | {r['n']} | {r['status']} | - | - |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------
# Automatic scores for the 60 sampled tests (inputs of the RQ2 comparison)
# --------------------------------------------------------------------------------------------
AUTO_FIELDS = ["item_id", "n_cases", "behaviours", "trace_name", "smells", "killed", "killed_frac",
               "auto_relevance", "auto_clarity", "auto_maintainability", "auto_oracle"]


def bin_relevance(n_behaviours: int) -> int:
    return min(5, n_behaviours + 1)


def bin_clarity(trace: float) -> int:
    return 1 + round(4 * trace)


def bin_maintainability(smells: float) -> int:
    return max(1, 5 - round(smells))


def bin_oracle(killed_frac: float) -> int:
    for limit, score in ((0.0, 1), (0.10, 2), (0.20, 3), (0.35, 4)):
        if killed_frac <= limit:
            return score
    return 5


def prepare_auto(settings) -> Path:
    """Per sampled test function: behaviours mapped, trace score, smells, mutants it kills alone.

    The origin key is read only to locate the test; it is never written to the output.
    """
    from .coverage_tool import stable_pass_set
    from .mutation_tool import (
        build_workspace,
        classify,
        failing_deselects,
        run_mutmut,
    )
    from .suites import suite_units

    res = settings.results_dir
    key_path = settings.project_root / "manual_review" / "key_do_not_open_until_rated.csv"
    with open(key_path, newline="", encoding="utf-8") as fh:
        key = list(csv.DictReader(fh))

    def rows(name: str, suite: str) -> list[dict]:
        p = res / name
        if not p.exists():
            return []
        with open(p, newline="", encoding="utf-8") as fh:
            return [r for r in csv.DictReader(fh) if r["suite"] == suite]

    comp = settings.config["ha"]["component"]
    out_rows = []
    for k in key:
        suite, unit, func = k["suite"], k["unit"], k["test"]
        beh = [r for r in rows("behaviour_tests.csv", suite)
               if r["unit"] == unit and r["test"].split("[")[0] == func]
        trace = [float(r["trace_name"]) for r in rows("trace_tests.csv", suite)
                 if r["unit"] == unit and r["test"].split("[")[0] == func and r["valid"] == "1"]
        smell = [int(r["total"]) for r in rows("smells_tests.csv", suite)
                 if r["unit"] == unit and r["test"].split("[")[0] == func and r["valid"] == "1"]
        units, _, _ = suite_units(settings, suite)
        path = next(u for u in units if u.name == unit)
        stable = stable_pass_set(settings, suite)
        deselect = [d for d in failing_deselects(settings, suite, path, stable)
                    if d.split("::")[1].split("[")[0] == func]
        ws = build_workspace(
            settings, [path], deselect=deselect, with_snapshots=suite == "developer",
            select=f"tests/components/{comp}/{unit}::{func}",
        )
        results, _, _ = run_mutmut(settings, ws)
        statuses = classify(results)
        total = len(statuses)
        killed = sum(1 for s in statuses.values() if s == "killed")
        frac = killed / total if total else 0.0
        n_beh = max((int(r["n_behaviours"]) for r in beh), default=0)
        tr = sum(trace) / len(trace) if trace else 0.0
        sm = sum(smell) / len(smell) if smell else 0.0
        out_rows.append({
            "item_id": k["item_id"], "n_cases": len(beh), "behaviours": n_beh,
            "trace_name": round(tr, 4), "smells": round(sm, 4), "killed": killed,
            "killed_frac": round(frac, 4), "auto_relevance": bin_relevance(n_beh),
            "auto_clarity": bin_clarity(tr), "auto_maintainability": bin_maintainability(sm),
            "auto_oracle": bin_oracle(frac),
        })
    path = res / "rq2_auto.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=AUTO_FIELDS)
        w.writeheader()
        w.writerows(sorted(out_rows, key=lambda r: r["item_id"]))
    return path
