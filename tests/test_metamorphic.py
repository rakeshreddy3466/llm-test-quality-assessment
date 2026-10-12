import pytest

from testquality.metamorphic import cliffs_delta, compare, delta_label, jaccard, mann_whitney


def test_cliffs_delta_extremes_and_symmetry():
    assert cliffs_delta([5, 6, 7], [1, 2, 3]) == 1.0
    assert cliffs_delta([1, 2, 3], [5, 6, 7]) == -1.0
    assert cliffs_delta([1, 2], [1, 2]) == 0.0
    assert cliffs_delta([2], [1, 3]) == 0.0


def test_delta_labels():
    assert [delta_label(x) for x in (0.0, 0.2, 0.4, 0.9)] == [
        "negligible", "small", "medium", "large"]
    assert delta_label(float("nan")) == "n/a"


def test_jaccard():
    assert jaccard({1, 2}, {2, 3}) == pytest.approx(1 / 3)
    assert jaccard(set(), set()) == 1.0


def test_mann_whitney_identical_and_separated():
    assert mann_whitney([1, 1, 1], [1, 1, 1])[1] == 1.0
    _, p = mann_whitney([10, 11, 12, 13, 14], [1, 2, 3, 4, 5])
    assert p < 0.05


def _unit(**kw):
    base = {"valid_tests": 10.0, "line_cov": 0.8, "branch_cov": 0.7, "mut_global": 0.5,
            "mut_covered": 0.8, "trace_name": 0.3, "smell_density": 0.5,
            "lines": {("b", 1), ("b", 2)}, "killed": {"m1", "m2"}}
    base.update(kw)
    return base


def test_compare_detects_no_change_when_variant_equals_baseline():
    base = {f"s{i}": _unit(line_cov=0.8 + i * 0.01) for i in range(5)}
    pairs, jac = compare(base, dict(base), "same")
    assert all(r["effect_size"] == "negligible" for r in pairs if r["metric"] == "line_cov")
    assert all(r["within_baseline_range"] == 1.0 for r in pairs)
    kinds = {r["kind"]: r for r in jac}
    assert kinds["jaccard_lines"]["cross_mean"] == 1.0


def test_compare_flags_a_real_shift():
    base = {f"s{i}": _unit(mut_global=0.5 + i * 0.01) for i in range(5)}
    var = {f"v{i}": _unit(mut_global=0.7 + i * 0.01, killed={"m9"}) for i in range(5)}
    pairs, jac = compare(base, var, "shift")
    row = next(r for r in pairs if r["metric"] == "mut_global")
    assert row["effect_size"] == "large" and row["mwu_p"] < 0.05
    assert row["within_baseline_range"] == 0.0
    killed = next(r for r in jac if r["kind"] == "jaccard_killed")
    assert killed["cross_mean"] < killed["noise_floor_mean"]
