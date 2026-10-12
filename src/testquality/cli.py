"""Command line interface. Each subcommand maps to one phase of the study."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__

# name -> (phase, help). Phases not yet built are stubs that exit with code 2.
SUBCOMMANDS: dict[str, tuple[int, str]] = {
    "generate": (2, "Generate unit tests with the LLM (supports --dry-run)"),
    "execute": (3, "Run suites: collect rate, pass rate, flaky rate, error types"),
    "coverage": (4, "Suite and per-test line/branch coverage"),
    "mutate": (5, "Mutation testing on the threshold component"),
    "traceability": (6, "Test-to-code traceability scores"),
    "smells": (7, "Test smell detection"),
    "relevance": (8, "Relevance and completeness against behaviours.yaml"),
    "review-sample": (9, "Build the blinded manual-review sample"),
    "metamorphic": (10, "Metamorphic experiment (MR1..MR4) vs noise floor"),
    "report": (11, "Build tables and figures from results/*.csv"),
}


def _cmd_generate(args: argparse.Namespace) -> int:
    from .config import get_api_key, get_workspace_id, load_settings
    from .generate import make_plan, run_generation

    st = load_settings()
    llm = st.config["llm"]
    models = args.model or [llm["cheap_model"] if args.cheap else llm["main_model"]]
    k = args.k or llm["samples_per_prompt"]
    plan = make_plan(st, models=models, k=k, targets=args.target)
    print(f"prompt version: {plan.prompts[0].version}  targets: {[p.target for p in plan.prompts]}")
    print(f"calls: {plan.n_calls} ({len(plan.prompts)} prompts x {len(models)} models x k={k})")
    for m in models:
        print(
            f"  {m}: ~{plan.est_input_tokens[m]:,} input tokens, "
            f"est. cost ${plan.est_cost[m]:.2f} "
            f"(output assumed {llm['expected_output_tokens']:,} tok/call; "
            f"prices as of {st.config['pricing']['as_of']})"
        )
    print(f"estimated total: ${plan.total_cost:.2f}  (limit ${llm['max_cost_usd']:.2f})")
    if args.show_prompt:
        print("\n" + plan.prompts[0].text)
    if args.dry_run:
        print("dry run: no API call made.")
        return 0
    if plan.total_cost > llm["max_cost_usd"]:
        print("refusing: estimate above max_cost_usd; ask the owner first.", file=sys.stderr)
        return 3
    key = get_api_key()
    if not key:
        print("ANTHROPIC_API_KEY is not set in .env", file=sys.stderr)
        return 1
    import anthropic

    ws = get_workspace_id()
    headers = {"anthropic-workspace-id": ws} if ws else None
    client = anthropic.Anthropic(api_key=key, default_headers=headers)
    run_dir = run_generation(st, client, plan, run_id=args.run_id)
    import json

    mani = json.loads((run_dir / "manifest.json").read_text())
    ok = sum(1 for s in mani["samples"] if s["file"] and s["syntax_ok"])
    print(f"run {mani['run_id']}: {ok}/{len(mani['samples'])} usable samples, "
          f"actual cost ${mani['total_cost_usd']:.4f}\nlog: {run_dir / 'calls.jsonl'}")
    return 0


def _cmd_execute(args: argparse.Namespace) -> int:
    import json

    from .config import load_settings
    from .executor import developer_units, run_executability

    st = load_settings()
    repeats = args.repeats or st.config["execution"]["repeats"]
    timeout = st.config["execution"]["timeout_seconds"]
    if args.suite == "developer":
        units, staging, requested, label = developer_units(st), None, None, "developer"
    else:
        run_dir = st.runs_dir / args.suite
        mani = json.loads((run_dir / "manifest.json").read_text())
        units = [run_dir / "samples" / s["file"] for s in mani["samples"] if s["file"]]
        staging, requested, label = args.suite, len(mani["samples"]), args.suite
    summary = run_executability(
        st, label, units, repeats=repeats, timeout=timeout, staging_id=staging,
        units_requested=requested,
    )
    for k, v in summary.items():
        print(f"{k}: {v}")
    return 0


def _suite_units(st, suite: str):
    """Return (units, staging_id, targets) for 'developer' or a generation run id."""
    import json

    from .executor import developer_units

    if suite == "developer":
        units = developer_units(st)
        return units, None, {u.name: "developer" for u in units}
    run_dir = st.runs_dir / suite
    mani = json.loads((run_dir / "manifest.json").read_text())
    samples = [s for s in mani["samples"] if s["file"]]
    units = [run_dir / "samples" / s["file"] for s in samples]
    return units, suite, {s["file"]: s["target"] for s in samples}


def _cmd_coverage(args: argparse.Namespace) -> int:
    from .config import load_settings
    from .coverage_tool import run_coverage, stable_pass_set

    st = load_settings()
    units, staging, targets = _suite_units(st, args.suite)
    rows = run_coverage(
        st, args.suite, units, staging_id=staging,
        stable=stable_pass_set(st, args.suite), targets=targets,
    )
    for r in rows:
        print({k: r[k] for k in ("scope", "line_cov", "branch_cov", "lines_covered", "lines_total",
                                 "branches_covered", "branches_total", "tests_passing")})
    return 0


def _cmd_mutate(args: argparse.Namespace) -> int:
    from .config import load_settings
    from .coverage_tool import stable_pass_set
    from .mutation_tool import run_mutation

    st = load_settings()
    units, _, targets = _suite_units(st, args.suite)
    rows = run_mutation(
        st, args.suite, units, targets, stable_pass_set(st, args.suite),
        with_snapshots=args.suite == "developer",
    )
    for r in rows:
        print(r)
    return 0


def _cmd_traceability(args: argparse.Namespace) -> int:
    from .config import load_settings
    from .coverage_tool import stable_pass_set
    from .traceability import run_traceability

    st = load_settings()
    units, staging, _ = _suite_units(st, args.suite)
    rows = run_traceability(
        st, args.suite, units, staging_id=staging, stable=stable_pass_set(st, args.suite),
        has_declaration=args.suite != "developer",
    )
    for r in rows:
        print(r)
    return 0


def _cmd_smells(args: argparse.Namespace) -> int:
    from .config import load_settings
    from .coverage_tool import stable_pass_set
    from .smells import run_smells

    st = load_settings()
    units, _, _ = _suite_units(st, args.suite)
    print(run_smells(st, args.suite, units, stable_pass_set(st, args.suite)))
    return 0


def _cmd_relevance(args: argparse.Namespace) -> int:
    from .behaviours import run_behaviours
    from .config import load_settings

    st = load_settings()
    _, _, targets = _suite_units(st, args.suite)
    for r in run_behaviours(st, args.suite, targets):
        print(r)
    return 0


IMPLEMENTED: dict[str, object] = {
    "generate": _cmd_generate, "execute": _cmd_execute, "coverage": _cmd_coverage,
    "mutate": _cmd_mutate, "traceability": _cmd_traceability, "smells": _cmd_smells,
    "relevance": _cmd_relevance,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="testquality",
        description="Quality assessment of LLM generated unit tests (Home Assistant: threshold).",
    )
    parser.add_argument("--version", action="version", version=f"testquality {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, (phase, help_text) in SUBCOMMANDS.items():
        p = sub.add_parser(name, help=f"{help_text} [phase {phase}]", description=help_text)
        p.set_defaults(phase=phase)
        if name == "execute":
            p.add_argument("--suite", required=True,
                           help="'developer' or a generation run id under data/runs/")
            p.add_argument("--repeats", type=int, help="runs per suite (default from config)")
        if name == "coverage":
            p.add_argument("--suite", required=True, help="'developer' or a run id")
        if name == "mutate":
            p.add_argument("--suite", required=True, help="'developer' or a run id")
        if name == "traceability":
            p.add_argument("--suite", required=True, help="'developer' or a run id")
        if name == "smells":
            p.add_argument("--suite", required=True, help="'developer' or a run id")
        if name == "relevance":
            p.add_argument("--suite", required=True, help="'developer' or a run id")
        if name == "generate":
            p.add_argument("--model", action="append", help="model id (repeatable); default main")
            p.add_argument("--cheap", action="store_true", help="use the cheap model")
            p.add_argument("-k", type=int, help="samples per prompt (default from config)")
            p.add_argument("--target", action="append", help="limit to target(s)")
            p.add_argument("--dry-run", action="store_true", help="show plan+cost, no API call")
            p.add_argument("--show-prompt", action="store_true", help="print first prompt")
            p.add_argument("--run-id", help="override run id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handler = IMPLEMENTED.get(args.command)
    if handler is None:
        print(
            f"testquality {args.command}: not implemented yet (planned for phase {args.phase}).",
            file=sys.stderr,
        )
        return 2
    return handler(args)  # type: ignore[operator]


if __name__ == "__main__":
    raise SystemExit(main())
