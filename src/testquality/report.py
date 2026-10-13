"""Build every Markdown table and PNG figure from results/*.csv (and nothing else).

Outputs: results/tables/*.md, results/figures/*.png. Missing inputs yield 'pending' notes
instead of invented numbers.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

from .config import Settings

DEVELOPER = "developer"
LLM_SUITE = "main_sonnet55_v1"
TARGETS = ["binary_sensor", "config_flow", "init"]
DEV_FILE = {t: f"test_{t}.py" for t in TARGETS}

# categorical slots 1-3 of the validated reference palette (light surface)
COL_DEV, COL_LLM, COL_THIRD = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e3e2de", "#fcfcfb"


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(x: str | float | None) -> float | None:
    try:
        return float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{100 * x:.{digits}f} %"


def f3(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def mean_sd(xs: list[float], fmt=f3) -> str:
    if not xs:
        return "n/a"
    if len(xs) == 1:
        return fmt(xs[0])
    return f"{fmt(statistics.fmean(xs))} ± {fmt(statistics.stdev(xs))}"


def target_of(unit: str, suite: str) -> str:
    if suite == DEVELOPER:
        for t, f in DEV_FILE.items():
            if unit == f:
                return t
        return ""
    for t in TARGETS:
        if unit.startswith(f"test_{t}__"):
            return t
    return ""


class Data:
    def __init__(self, results: Path):
        r = results
        self.exec_summary = read(r / "exec_summary.csv")
        self.exec_errors = read(r / "exec_errors.csv")
        self.cov_units = read(r / "coverage_units.csv")
        self.cov_suites = read(r / "coverage_suites.csv")
        self.mut_units = read(r / "mutation_units.csv")
        self.mut_suites = read(r / "mutation_suites.csv")
        self.trace = read(r / "trace_summary.csv")
        self.trace_tests = read(r / "trace_tests.csv")
        self.smells = read(r / "smells_summary.csv")
        self.behaviour = read(r / "behaviour_summary.csv")
        self.mr_metrics = read(r / "mr_metrics.csv")
        self.mr_jaccard = read(r / "mr_jaccard.csv")


def row(rows: list[dict], **kw) -> dict | None:
    for r in rows:
        if all(r.get(k) == v for k, v in kw.items()):
            return r
    return None


# ------------------------------------------------------------------------------- tables
def table_executability(d: Data) -> str:
    header = ["Suite", "Units", "Collect rate", "Tests", "Pass rate (mean of 3)",
              "Stable pass rate", "Flaky rate"]
    rows = []
    for s in d.exec_summary:
        rows.append([
            "developer" if s["suite"] == DEVELOPER else s["suite"],
            f'{s["units_collected"]}/{s["units_requested"]}', pct(num(s["collect_rate"])),
            s["tests_collected"], pct(num(s["pass_rate_mean"])), pct(num(s["stable_pass_rate"])),
            pct(num(s["flaky_rate"])),
        ])
    errs = [r for r in d.exec_errors if r["suite"] != DEVELOPER]
    out = "### Executability\n\n" + md_table(header, rows)
    if errs:
        out += "\n**Failure types of non-passing tests**\n\n" + md_table(
            ["Suite", "Error type", "Tests"], [[r["suite"], r["error_type"], r["count"]]
                                                for r in errs])
    return out


def table_suite_quality(d: Data) -> str:
    header = ["Target / scope", "Suite", "Tests passing", "Line cov.", "Branch cov.",
              "Mutation score (global)", "Mutation score (covered)"]
    rows = []
    for scope in ["all"] + [f"target:{t}" for t in TARGETS]:
        for suite, label in ((DEVELOPER, "developer"), (LLM_SUITE, "LLM (union of k=5)")):
            c = row(d.cov_suites, suite=suite, scope=scope) or (
                row(d.cov_suites, suite=suite, scope="target:developer")
                if suite == DEVELOPER and scope != "all" else None)
            m = row(d.mut_suites, suite=suite, scope=scope)
            if suite == DEVELOPER and scope != "all":
                # developer files map one-to-one to targets: use that unit's own numbers
                unit = DEV_FILE.get(scope.split(":")[1])
                cu = row(d.cov_units, suite=suite, unit=unit)
                mu = row(d.mut_units, suite=suite, unit=unit)
                if cu and mu:
                    rows.append([scope, label, cu["tests_passing"], pct(num(cu["line_cov"])),
                                 pct(num(cu["branch_cov"])), pct(num(mu["score_global"])),
                                 pct(num(mu["score_covered"]))])
                continue
            if c and m:
                rows.append([scope, label, c["tests_passing"], pct(num(c["line_cov"])),
                             pct(num(c["branch_cov"])), pct(num(m["score_global"])),
                             pct(num(m["score_covered"]))])
    return ("### Coverage and mutation score (suite level)\n\n"
            "Developer rows per target are the matching developer file; the LLM rows are the "
            "union over the k = 5 samples of that target.\n\n" + md_table(header, rows))


def table_per_sample(d: Data) -> str:
    header = ["Target", "Developer file", "LLM samples (mean ± sd, k=5)"]
    rows = []
    for t in TARGETS:
        dev_c = row(d.cov_units, suite=DEVELOPER, unit=DEV_FILE[t])
        dev_m = row(d.mut_units, suite=DEVELOPER, unit=DEV_FILE[t])
        cu = [r for r in d.cov_units
              if r["suite"] == LLM_SUITE and target_of(r["unit"], LLM_SUITE) == t]
        mu = [r for r in d.mut_units
              if r["suite"] == LLM_SUITE and target_of(r["unit"], LLM_SUITE) == t]
        if not cu:
            continue
        rows += [
            [t + " - valid tests", dev_c["tests_passing"] if dev_c else "n/a",
             mean_sd([float(r["tests_passing"]) for r in cu], lambda x: f"{x:.1f}")],
            [t + " - line cov.", pct(num(dev_c["line_cov"])) if dev_c else "n/a",
             mean_sd([float(r["line_cov"]) for r in cu], lambda x: pct(x))],
            [t + " - branch cov.", pct(num(dev_c["branch_cov"])) if dev_c else "n/a",
             mean_sd([float(r["branch_cov"]) for r in cu], lambda x: pct(x))],
            [t + " - mutation score (global)", pct(num(dev_m["score_global"])) if dev_m else "n/a",
             mean_sd([float(r["score_global"]) for r in mu], lambda x: pct(x))],
        ]
    return "### Per file / per sample\n\n" + md_table(header, rows)


def table_quality_dims(d: Data) -> str:
    header = ["Suite", "Trace (name target)", "Trace (declared target)", "Declared present",
              "Smelly tests", "Smell density", "Relevance", "Completeness"]
    rows = []
    for suite, label in ((DEVELOPER, "developer"), (LLM_SUITE, "LLM")):
        t = row(d.trace, suite=suite, scope="all")
        s = row(d.smells, suite=suite)
        b = row(d.behaviour, suite=suite, scope="all")
        rows.append([
            label, f3(num(t["trace_name_mean"])) if t else "n/a",
            f3(num(t["trace_declared_mean"])) if t and t["trace_declared_mean"] else "n/a",
            pct(num(t["declared_present_rate"])) if t and t["declared_present_rate"] else "n/a",
            pct(num(s["smelly_rate"])) if s else "n/a",
            f3(num(s["smell_density"])) if s else "n/a",
            pct(num(b["relevance"])) if b else "n/a",
            pct(num(b["completeness"])) if b else "n/a",
        ])
    return ("### Traceability, smells, relevance, completeness\n\n"
            "Behaviour list is a DRAFT (needs human check); completeness is relative to the "
            "behaviours the developer tests reach.\n\n" + md_table(header, rows))


def table_smells(d: Data) -> str:
    keys = ["assertion_roulette", "duplicate_assert", "magic_number", "conditional_logic",
            "no_assertion", "try_except", "sleepy_test", "redundant_print", "eager_test",
            "empty_test"]
    header = ["Smell", "developer", "LLM"]
    dev, llm = row(d.smells, suite=DEVELOPER), row(d.smells, suite=LLM_SUITE)
    rows = [[k, pct(num(dev[f"rate_{k}"])) if dev else "n/a",
             pct(num(llm[f"rate_{k}"])) if llm else "n/a"] for k in keys]
    return "### Test smells (share of valid tests with the smell)\n\n" + md_table(header, rows)


def table_rq3(d: Data) -> str:
    if not d.mr_metrics:
        return "### RQ3 metamorphic sensitivity\n\npending: results/mr_metrics.csv not found.\n"
    header = ["Variant", "Metric", "Baseline mean (sd)", "Variant mean", "In baseline range",
              "MWU p", "Cliff's delta", "Effect"]
    wanted = {"valid_tests", "line_cov", "branch_cov", "mut_global", "trace_name",
              "smell_density"}
    rows = [
        [r["variant"], r["metric"], f'{f3(num(r["baseline_mean"]))} ({f3(num(r["baseline_sd"]))})',
         f3(num(r["variant_mean"])), pct(num(r["within_baseline_range"]), 0), r["mwu_p"],
         r["cliffs_delta"], r["effect_size"]]
        for r in d.mr_metrics if r["metric"] in wanted
    ]
    out = ("### RQ3 metamorphic sensitivity (binary_sensor target, n = 5 samples per variant)\n\n"
           + md_table(header, rows))
    if d.mr_jaccard:
        out += "\n**Overlap of covered lines and of killed mutants**\n\n" + md_table(
            ["Variant", "Set", "Noise floor (same prompt)", "Variant vs original", "MWU p",
             "Cliff's delta"],
            [[r["variant"], r["kind"].replace("jaccard_", ""), f3(num(r["noise_floor_mean"])),
              f3(num(r["cross_mean"])), r["mwu_p"], r["cliffs_delta"]] for r in d.mr_jaccard])
    return out


def section_rq2(settings: Settings) -> str:
    rated = settings.project_root / "manual_review" / "sample_rated.csv"
    auto = settings.results_dir / "rq2_auto.csv"
    if not rated.exists() or not auto.exists():
        return ("### RQ2 agreement with manual review\n\npending manual review "
                "(manual_review/sample_rated.csv not present).\n")
    from .rq2 import agreement_table

    return "### RQ2 agreement with manual review\n\n" + agreement_table(rated, auto)


# ------------------------------------------------------------------------------- figures
def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def figure_suite(d: Data, out: Path) -> bool:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    c = {s: row(d.cov_suites, suite=s, scope="all") for s in (DEVELOPER, LLM_SUITE)}
    m = {s: row(d.mut_suites, suite=s, scope="all") for s in (DEVELOPER, LLM_SUITE)}
    if not all(c.values()) or not all(m.values()):
        return False
    labels = ["Line coverage", "Branch coverage", "Mutation score\n(global)"]
    vals = {
        s: [float(c[s]["line_cov"]), float(c[s]["branch_cov"]), float(m[s]["score_global"])]
        for s in c
    }
    fig, ax = plt.subplots(figsize=(6.4, 3.8), facecolor=SURFACE)
    _style(ax)
    w = 0.32
    for i, (s, col, lab) in enumerate(((DEVELOPER, COL_DEV, "Developer"),
                                       (LLM_SUITE, COL_LLM, "LLM (union of 15 samples)"))):
        xs = [x + (i - 0.5) * (w + 0.04) for x in range(3)]
        bars = ax.bar(xs, vals[s], width=w, color=col, label=lab, edgecolor=SURFACE, linewidth=2)
        for b, v in zip(bars, vals[s], strict=True):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.015, f"{100 * v:.1f}", ha="center",
                    color=INK, fontsize=8)
    ax.set_xticks(range(3), labels, color=INK2)
    ax.set_ylim(0, 1.25)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0], ["0", "25", "50", "75", "100"])
    ax.set_ylabel("percent", color=INK2)
    ax.set_title("Suite level quality: developer vs LLM tests", color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="upper center", ncol=2)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return True


def figure_samples(d: Data, out: Path) -> bool:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pts = {
        t: [float(r["score_global"]) for r in d.mut_units
            if r["suite"] == LLM_SUITE and target_of(r["unit"], LLM_SUITE) == t]
        for t in TARGETS
    }
    if not any(pts.values()):
        return False
    dev = {t: row(d.mut_units, suite=DEVELOPER, unit=DEV_FILE[t]) for t in TARGETS}
    fig, ax = plt.subplots(figsize=(6.4, 3.8), facecolor=SURFACE)
    _style(ax)
    for i, t in enumerate(TARGETS):
        ys = pts[t]
        offs = [(-0.12 + 0.06 * k) for k in range(len(ys))]
        ax.scatter([i + o for o in offs], ys, s=40, color=COL_LLM, edgecolor=SURFACE,
                   linewidth=1.5, zorder=3, label="LLM sample" if i == 0 else None)
        if dev[t]:
            ax.scatter([i + 0.3], [float(dev[t]["score_global"])], s=70, color=COL_DEV,
                       marker="D", edgecolor=SURFACE, linewidth=1.5, zorder=3,
                       label="Developer file" if i == 0 else None)
    ax.set_xticks(range(len(TARGETS)), TARGETS, color=INK2)
    ax.set_ylim(0, 1.15)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0], ["0", "25", "50", "75", "100"])
    ax.set_ylabel("mutation score, global (%)", color=INK2)
    ax.set_title("Mutation score per sample (fixed 164-mutant population)", color=INK,
                 fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="upper center", ncol=2)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return True


def figure_rq3(d: Data, out: Path) -> bool:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [r for r in d.mr_jaccard if r["kind"] == "jaccard_killed"]
    if not rows:
        return False
    names = [r["variant"] for r in rows]
    noise = [float(r["noise_floor_mean"]) for r in rows]
    cross = [float(r["cross_mean"]) for r in rows]
    fig, ax = plt.subplots(figsize=(6.4, 3.8), facecolor=SURFACE)
    _style(ax)
    w = 0.34
    xs = range(len(names))
    ax.bar([x - w / 2 - 0.02 for x in xs], noise, width=w, color=COL_DEV, edgecolor=SURFACE,
           linewidth=2, label="Noise floor: same prompt, different samples")
    ax.bar([x + w / 2 + 0.02 for x in xs], cross, width=w, color=COL_LLM, edgecolor=SURFACE,
           linewidth=2, label="Variant vs original samples")
    ax.set_xticks(list(xs), names, color=INK2)
    ax.set_ylim(0, 1.3)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_ylabel("Jaccard of killed mutants", color=INK2)
    ax.set_title("Metamorphic variants vs sampling noise", color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="upper center", ncol=1)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return True


# ------------------------------------------------------------------------------- driver
def build(settings: Settings) -> list[Path]:
    d = Data(settings.results_dir)
    tdir = settings.results_dir / "tables"
    fdir = settings.results_dir / "figures"
    tdir.mkdir(parents=True, exist_ok=True)
    fdir.mkdir(parents=True, exist_ok=True)
    tables = {
        "executability.md": table_executability(d),
        "suite_quality.md": table_suite_quality(d),
        "per_sample.md": table_per_sample(d),
        "quality_dimensions.md": table_quality_dims(d),
        "smells.md": table_smells(d),
        "rq3.md": table_rq3(d),
        "rq2.md": section_rq2(settings),
    }
    written = []
    for name, text in tables.items():
        p = tdir / name
        p.write_text(text, encoding="utf-8")
        written.append(p)
    (tdir / "all.md").write_text("\n".join(tables.values()), encoding="utf-8")
    figures = (
        ("suite_quality.png", figure_suite),
        ("mutation_per_sample.png", figure_samples),
        ("rq3_jaccard.png", figure_rq3),
    )
    for name, fn in figures:
        if fn(d, fdir / name):
            written.append(fdir / name)
    written += build_documents(settings)
    return written


# ------------------------------------------------------------------------------- findings
def _g(rows: list[dict], key: str, **kw) -> float | None:
    r = row(rows, **kw)
    return num(r[key]) if r and key in r else None


def findings(settings: Settings) -> list[str]:
    """Plain-language findings; every number is read from results/*.csv."""
    d = Data(settings.results_dir)
    out: list[str] = []
    ex_d = row(d.exec_summary, suite=DEVELOPER)
    ex_l = row(d.exec_summary, suite=LLM_SUITE)
    if ex_d and ex_l:
        out.append(
            f"**Executability.** {ex_l['units_collected']} of {ex_l['units_requested']} LLM "
            f"samples collect; {pct(num(ex_l['stable_pass_rate']))} of the "
            f"{ex_l['tests_collected']} generated tests pass in all three runs "
            f"(developer tests: {pct(num(ex_d['stable_pass_rate']))}); flaky rate "
            f"{pct(num(ex_l['flaky_rate']))}."
        )
    cd, cl = (row(d.cov_suites, suite=s, scope="all") for s in (DEVELOPER, LLM_SUITE))
    md, ml = (row(d.mut_suites, suite=s, scope="all") for s in (DEVELOPER, LLM_SUITE))
    if cd and cl and md and ml:
        out.append(
            f"**Coverage and mutation (suite level).** Line coverage {pct(num(cd['line_cov']))} "
            f"(developer) vs {pct(num(cl['line_cov']))} (union of the LLM samples); branch "
            f"coverage {pct(num(cd['branch_cov']))} vs {pct(num(cl['branch_cov']))}; mutation "
            f"score over the fixed {md['mutants_total']} mutants "
            f"{pct(num(md['score_global']))} vs {pct(num(ml['score_global']))}."
        )
    parts = []
    for t in TARGETS:
        mu = [float(r["score_global"]) for r in d.mut_units
              if r["suite"] == LLM_SUITE and target_of(r["unit"], LLM_SUITE) == t]
        dv = row(d.mut_units, suite=DEVELOPER, unit=DEV_FILE[t])
        if mu and dv:
            parts.append(f"{t}: {pct(statistics.fmean(mu))} per LLM sample vs "
                         f"{pct(num(dv['score_global']))} for the developer file")
    if parts:
        out.append("**Per target mutation score (global).** " + "; ".join(parts) + ".")
    tr_d, tr_l = (row(d.trace, suite=s, scope="all") for s in (DEVELOPER, LLM_SUITE))
    if tr_d and tr_l:
        out.append(
            f"**Traceability.** Mean name-vs-coverage score {f3(num(tr_d['trace_name_mean']))} "
            f"(developer) vs {f3(num(tr_l['trace_name_mean']))} (LLM); the LLM's declared "
            f"`Target:` scores {f3(num(tr_l['trace_declared_mean']))}, and "
            f"{pct(num(tr_l['declared_present_rate']))} of valid LLM tests carry a parsable "
            "declaration."
        )
    sm_d, sm_l = (row(d.smells, suite=s) for s in (DEVELOPER, LLM_SUITE))
    if sm_d and sm_l:
        out.append(
            f"**Test smells.** Share of valid tests with at least one smell: "
            f"{pct(num(sm_d['smelly_rate']))} (developer) vs {pct(num(sm_l['smelly_rate']))} "
            f"(LLM); smell density {f3(num(sm_d['smell_density']))} vs "
            f"{f3(num(sm_l['smell_density']))} per test."
        )
    bd, bl = (row(d.behaviour, suite=s, scope="all") for s in (DEVELOPER, LLM_SUITE))
    if bd and bl:
        out.append(
            f"**Relevance and completeness (draft behaviour list).** Relevance "
            f"{pct(num(bd['relevance']))} (developer) vs {pct(num(bl['relevance']))} (LLM); "
            f"LLM completeness {pct(num(bl['completeness']))} of the "
            f"{bl['behaviours_reachable']} behaviours reachable by the developer tests."
        )
    if d.mr_metrics:
        names = sorted({r["variant"] for r in d.mr_metrics if r["variant"] != "mr1_pooled"})
        bits = []
        for v in names:
            rows_v = [r for r in d.mr_metrics if r["variant"] == v]
            sig = [r["metric"] for r in rows_v if (num(r["mwu_p"]) or 1) < 0.05]
            jac = row(d.mr_jaccard, variant=v, kind="jaccard_killed")
            tail = (f", killed-mutant overlap {f3(num(jac['cross_mean']))} vs noise floor "
                    f"{f3(num(jac['noise_floor_mean']))}" if jac else "")
            bits.append(f"{v}: {len(sig)}/{len(rows_v)} metrics differ at p<0.05"
                        f"{' (' + ', '.join(sig) + ')' if sig else ''}{tail}")
        out.append("**Metamorphic sensitivity (binary_sensor, n=5 per variant).** "
                   + "; ".join(bits) + ".")
    else:
        out.append("**Metamorphic sensitivity.** pending (results/mr_metrics.csv missing).")
    rated = settings.project_root / "manual_review/sample_rated.csv"
    auto = settings.results_dir / "rq2_auto.csv"
    if rated.exists() and auto.exists():
        from .rq2 import agreement_rows

        bits = [f"{r['scale']}: rho {r['rho']:.2f}, kappa {r['kappa']:.2f}"
                for r in agreement_rows(rated, auto) if r["status"] == "ok"]
        out.append("**Agreement with manual review (RQ2, n=60).** " + "; ".join(bits)
                   + " (table in the RQ2 section).")
    else:
        out.append("**Agreement with manual review (RQ2).** pending manual review.")
    return out



def facts(settings: Settings) -> dict[str, str]:
    """Numbers quoted in the abstract and discussion; all read from results/*.csv."""
    d = Data(settings.results_dir)
    f: dict[str, str] = {}

    def put(key: str, val: str | None) -> None:
        f[key] = val if val is not None else "n/a"

    cd, cl = (row(d.cov_suites, suite=s, scope="all") for s in (DEVELOPER, LLM_SUITE))
    md, ml = (row(d.mut_suites, suite=s, scope="all") for s in (DEVELOPER, LLM_SUITE))
    if cd and cl and md and ml:
        put("dev_line", pct(num(cd["line_cov"])))
        put("llm_line", pct(num(cl["line_cov"])))
        put("dev_branch", pct(num(cd["branch_cov"])))
        put("llm_branch", pct(num(cl["branch_cov"])))
        put("dev_mut", pct(num(md["score_global"])))
        put("llm_mut", pct(num(ml["score_global"])))
        put("mutants", md["mutants_total"])
        put("dev_tests", cd["tests_passing"])
        put("llm_tests", cl["tests_passing"])
        nd, nl = num(cd["tests_passing"]), num(cl["tests_passing"])
        put("test_ratio", f"{nl / nd:.1f}" if nd and nl else None)
    ex = row(d.exec_summary, suite=LLM_SUITE)
    if ex:
        put("llm_pass", pct(num(ex["stable_pass_rate"])))
        put("llm_generated", ex["tests_collected"])
    for t in TARGETS:
        mu = [float(r["score_global"]) for r in d.mut_units
              if r["suite"] == LLM_SUITE and target_of(r["unit"], LLM_SUITE) == t]
        dv = row(d.mut_units, suite=DEVELOPER, unit=DEV_FILE[t])
        put(f"{t}_llm_mut", pct(statistics.fmean(mu)) if mu else None)
        put(f"{t}_dev_mut", pct(num(dv["score_global"])) if dv else None)
        u = row(d.mut_suites, suite=LLM_SUITE, scope=f"target:{t}")
        v = row(d.mut_suites, suite=DEVELOPER, scope=f"target:{t}")
        put(f"{t}_llm_union_mut", pct(num(u["score_global"])) if u else None)
        put(f"{t}_dev_file_mut", pct(num(v["score_global"])) if v else None)
    sd, sl = (row(d.smells, suite=s) for s in (DEVELOPER, LLM_SUITE))
    if sd and sl:
        put("dev_smelly", pct(num(sd["smelly_rate"])))
        put("llm_smelly", pct(num(sl["smelly_rate"])))
        put("dev_roulette", pct(num(sd["rate_assertion_roulette"])))
        put("llm_roulette", pct(num(sl["rate_assertion_roulette"])))
        put("dev_cond", pct(num(sd["rate_conditional_logic"])))
        put("llm_cond", pct(num(sl["rate_conditional_logic"])))
    rated = settings.project_root / "manual_review" / "sample_rated.csv"
    auto = settings.results_dir / "rq2_auto.csv"
    if rated.exists() and auto.exists():
        from .rq2 import agreement_rows

        for r in agreement_rows(rated, auto):
            k = r["scale"]
            put(f"rq2_{k}_rho", f"{r['rho']:.2f}" if r["rho"] is not None else None)
            put(f"rq2_{k}_p", f"{r['p']:.3f}" if r["p"] is not None else None)
            put(f"rq2_{k}_kappa", f"{r['kappa']:.2f}" if r["kappa"] is not None else None)
            put(f"rq2_{k}_n", str(r["n"]))
        ok = [r for r in agreement_rows(rated, auto) if r["rho"] is not None]
        if ok:
            best = max(ok, key=lambda r: r["rho"])
            put("rq2_best_scale", best["scale"].replace("_", " "))
            put("rq2_best_rho", f"{best['rho']:.2f}")
            put("rq2_max_kappa", f"{max(r['kappa'] for r in ok):.2f}")
    if d.mr_metrics:
        rows_v = [r for r in d.mr_metrics if r["variant"] != "mr1_pooled"]
        sig = [r for r in rows_v if (num(r["mwu_p"]) or 1) < 0.05]
        put("mr_sig", str(len(sig)))
        put("mr_total", str(len(rows_v)))
        put("mr_variants", str(len({r["variant"] for r in rows_v})))
        jk = [r for r in d.mr_jaccard if r["kind"] == "jaccard_killed"
              and r["variant"] != "mr1_pooled"]
        if jk:
            cross = [float(r["cross_mean"]) for r in jk]
            put("mr_jac_min", f3(min(cross)))
            put("mr_jac_max", f3(max(cross)))
            put("mr_noise", f3(num(jk[0]["noise_floor_mean"])))
    return f

def _fill(template: str, tables: Path, figures: str, items: list[str],
          fact_map: dict[str, str] | None = None) -> str:
    text = template.replace("{{FINDINGS}}", "\n".join(f"- {x}" for x in items))
    for k, v in (fact_map or {}).items():
        text = text.replace("{{F:" + k + "}}", v)
    for p in sorted(tables.glob("*.md")):
        text = text.replace("{{TABLE:" + p.stem + "}}", p.read_text(encoding="utf-8"))
    for name in ("suite_quality", "mutation_per_sample", "rq3_jaccard"):
        text = text.replace("{{FIG:" + name + "}}", f"{figures}/{name}.png")
    return text


def build_documents(settings: Settings) -> list[Path]:
    """Fill report/report_template.md -> report/report.md and the README results block."""
    root = settings.project_root
    items = findings(settings)
    tables = settings.results_dir / "tables"
    written: list[Path] = []
    tpl = root / "report" / "report_template.md"
    if tpl.exists():
        out = root / "report" / "report.md"
        out.write_text(_fill(tpl.read_text(encoding="utf-8"), tables, "../results/figures",
                             items, facts(settings)), encoding="utf-8")
        written.append(out)
    readme = root / "README.md"
    start, end = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
    text = readme.read_text(encoding="utf-8")
    if start in text and end in text:
        block = ["_Generated by `make all` from `results/*.csv`; do not edit by hand._", "",
                 "### Key findings", ""]
        block += [f"- {x}" for x in items]
        for name in ("suite_quality", "per_sample", "executability"):
            p = tables / f"{name}.md"
            if p.exists():
                block += ["", p.read_text(encoding="utf-8")]
        block += ["", "![Suite quality](results/figures/suite_quality.png)", ""]
        head, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        readme.write_text(head + start + "\n" + "\n".join(block) + "\n" + end + tail,
                          encoding="utf-8")
        written.append(readme)
    return written
