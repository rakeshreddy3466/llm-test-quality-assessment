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


def agreement_table(rated: Path, auto: Path) -> str:
    from scipy.stats import spearmanr

    with open(rated, newline="", encoding="utf-8") as fh:
        manual = {r["item_id"]: r for r in csv.DictReader(fh)}
    with open(auto, newline="", encoding="utf-8") as fh:
        autos = {r["item_id"]: r for r in csv.DictReader(fh)}
    lines = ["| Scale | n | Spearman rho | p | Weighted kappa |", "|---|---|---|---|---|"]
    for scale, col in SCALES.items():
        pairs = []
        for item, m in manual.items():
            try:
                pairs.append((int(m[scale]), int(float(autos[item][col]))))
            except (KeyError, ValueError):
                continue
        if len(pairs) < 3:
            lines.append(f"| {scale} | {len(pairs)} | pending | pending | pending |")
            continue
        x, y = [p[0] for p in pairs], [p[1] for p in pairs]
        if len(set(x)) < 2 or len(set(y)) < 2:
            lines.append(f"| {scale} | {len(pairs)} | undefined (constant ratings) | - | - |")
            continue
        rho, p = spearmanr(x, y)
        lines.append(f"| {scale} | {len(pairs)} | {rho:.3f} | {p:.3f} | "
                     f"{weighted_kappa(x, y):.3f} |")
    return "\n".join(lines) + "\n"
