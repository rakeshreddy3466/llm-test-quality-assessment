import csv

import pytest

from testquality.report import md_table, mean_sd, pct, target_of
from testquality.rq2 import agreement_table, weighted_kappa


def test_formatting_helpers():
    assert pct(0.1234) == "12.3 %" and pct(None) == "n/a"
    assert mean_sd([]) == "n/a"
    assert mean_sd([1.0]) == "1.000"
    assert md_table(["a", "b"], [["1", "2"]]).splitlines()[1] == "|---|---|"


def test_target_of():
    assert target_of("test_binary_sensor.py", "developer") == "binary_sensor"
    assert target_of("test_init__sonnet-5-5__s0.py", "main") == "init"
    assert target_of("test_other.py", "developer") == ""


def test_weighted_kappa_perfect_and_opposite():
    assert weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert weighted_kappa([1, 5, 1, 5], [5, 1, 5, 1]) < 0


def test_agreement_table_from_files(tmp_path):
    rated, auto = tmp_path / "r.csv", tmp_path / "a.csv"
    ids = [f"R{i:02d}" for i in range(1, 7)]
    with open(rated, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_id", "relevance", "clarity", "maintainability", "oracle_strength"])
        for i, item in enumerate(ids):
            w.writerow([item, i % 5 + 1, 3, 3, 3])
    with open(auto, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_id", "auto_relevance", "auto_clarity", "auto_maintainability",
                    "auto_oracle"])
        for i, item in enumerate(ids):
            w.writerow([item, i % 5 + 1, 3, 3, 3])
    out = agreement_table(rated, auto)
    assert "| relevance | 6 | 1.000" in out


def test_rq2_bins():
    from testquality.rq2 import bin_clarity, bin_maintainability, bin_oracle, bin_relevance

    assert [bin_relevance(n) for n in (0, 1, 4, 9)] == [1, 2, 5, 5]
    assert [bin_clarity(x) for x in (0.0, 0.5, 1.0)] == [1, 3, 5]
    assert [bin_maintainability(x) for x in (0, 1, 2.4, 9)] == [5, 4, 3, 1]
    assert [bin_oracle(x) for x in (0.0, 0.05, 0.15, 0.3, 0.9)] == [1, 2, 3, 4, 5]
