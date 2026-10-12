from pathlib import Path

from testquality.coverage_tool import _pct, _short_test_id, _union, analyse_unit
from testquality.executor import TestOutcome

FILES = {
    "m.py": {"statements": [1, 2, 3, 4], "branch_arcs": [[2, 3], [2, 4]]},
}
COV = {
    "files": FILES,
    "tests": {
        "tests/x/test_u.py::test_a": {"m.py": {"lines": [1, 2, 3], "arcs": [[2, 3]]}},
        "tests/x/test_u.py::test_b": {"m.py": {"lines": [1, 2, 4], "arcs": [[2, 4]]}},
        "tests/x/test_u.py::test_bad": {"m.py": {"lines": [1, 2, 3, 4], "arcs": [[2, 3], [2, 4]]}},
        "__import__": {"m.py": {"lines": [1], "arcs": []}},
    },
}


def test_short_test_id():
    assert _short_test_id("a/b/test_u.py::test_x[p-1]") == ("test_u.py", "test_x[p-1]")


def test_union_counts_lines_and_branches():
    ents = [COV["tests"]["tests/x/test_u.py::test_a"]]
    assert _union(ents, FILES) == (3, 4, 1, 2)
    ents.append(COV["tests"]["tests/x/test_u.py::test_b"])
    assert _union(ents, FILES) == (4, 4, 2, 2)
    assert _pct(1, 0) == 0.0


def test_only_passing_tests_count():
    outcomes = [
        TestOutcome("test_u.py", "test_a", "passed"),
        TestOutcome("test_u.py", "test_b", "passed"),
        TestOutcome("test_u.py", "test_bad", "failed", "AssertionError"),
        TestOutcome("test_u.py", "test_noop", "passed"),
    ]
    unit, tests, _ = analyse_unit("s", Path("test_u.py"), COV, outcomes, None, "tgt")
    assert unit["tests_passing"] == 3  # incl. test_noop, which touches no component code
    assert unit["tests_total"] == 4
    assert unit["line_cov"] == 1.0  # failing test_bad is not required for full coverage
    assert unit["branch_cov"] == 1.0
    assert {t["test"] for t in tests} == {"test_a", "test_b", "test_noop"}


def test_failing_test_coverage_is_ignored():
    outcomes = [
        TestOutcome("test_u.py", "test_a", "passed"),
        TestOutcome("test_u.py", "test_bad", "failed", "AssertionError"),
    ]
    unit, tests, _ = analyse_unit("s", Path("test_u.py"), COV, outcomes, None)
    assert unit["lines_covered"] == 3 and unit["branches_covered"] == 1
    a = next(t for t in tests if t["test"] == "test_a")
    assert a["unique_lines"] == 3  # no other passing test covers them


def test_stable_set_excludes_flaky_tests():
    outcomes = [TestOutcome("test_u.py", "test_a", "passed"),
                TestOutcome("test_u.py", "test_b", "passed")]
    unit, _, _ = analyse_unit("s", Path("test_u.py"), COV, outcomes, {("test_u.py", "test_a")})
    assert unit["tests_passing"] == 1
