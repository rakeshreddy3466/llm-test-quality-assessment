"""Run with the Home Assistant interpreter (it has `coverage`); stdlib + coverage only.

usage: python -I _cov_extract.py <coverage data file> <out.json> <component path fragment>
Writes statements, possible branch arcs and, per test context, executed lines/branch arcs.
"""

import json
import sys

import coverage


def main(data_file: str, out: str, fragment: str) -> None:
    cov = coverage.Coverage(data_file=data_file)
    cov.load()
    data = cov.get_data()
    files = {}
    for f in sorted(data.measured_files()):
        if fragment not in f:
            continue
        an = cov._analyze(f)  # public API has no per-arc possibilities
        parser = cov._get_file_reporter(f).parser
        branch_lines = {ln for ln, n in an.exit_counts.items() if n > 1}
        possible = sorted(a for a in an.arc_possibilities if a[0] in branch_lines)
        files[f.split(fragment, 1)[1].lstrip("/")] = {
            "path": f,
            "statements": sorted(an.statements),
            "branch_arcs": [list(a) for a in possible],
            "_parser": parser,
        }
    tests: dict[str, dict] = {}
    for ctx in sorted(data.measured_contexts()):
        # the empty context holds import-time lines (module level code)
        test_id = ctx.rsplit("|", 1)[0] if ctx else "__import__"
        data.set_query_context(ctx)
        entry = tests.setdefault(test_id, {})
        for name, info in files.items():
            parser = info["_parser"]
            lines = set(parser.translate_lines(data.lines(info["path"]) or []))
            arcs = {tuple(a) for a in parser.translate_arcs(data.arcs(info["path"]) or [])}
            branch = {tuple(a) for a in info["branch_arcs"]} & arcs
            cur = entry.setdefault(name, {"lines": set(), "arcs": set()})
            cur["lines"] |= lines
            cur["arcs"] |= branch
    for entry in tests.values():
        for v in entry.values():
            v["lines"] = sorted(v["lines"])
            v["arcs"] = sorted([list(a) for a in v["arcs"]])
    for info in files.values():
        info.pop("path")
        info.pop("_parser")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"files": files, "tests": tests}, fh)


if __name__ == "__main__":
    main(*sys.argv[1:4])
