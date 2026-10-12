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

IMPLEMENTED: dict[str, object] = {}


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
