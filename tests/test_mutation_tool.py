from testquality.mutation_tool import (
    _suite_rows,
    classify,
    function_of,
    unit_row,
)


def test_function_of():
    m = "homeassistant.components.threshold.binary_sensor.x_async_setup_entry__mutmut_3"
    assert function_of(m) == "async_setup_entry"


def test_classify_exit_codes():
    got = classify({"a": 1, "b": 3, "c": 0, "d": 33, "e": 36, "f": None, "g": 99})
    assert got == {"a": "killed", "b": "killed", "c": "survived", "d": "no tests",
                   "e": "timeout", "f": "no tests", "g": "other"}


def test_unit_row_scores():
    statuses = {"m1": "killed", "m2": "killed", "m3": "survived", "m4": "no tests",
                "m5": "timeout"}
    r = unit_row("s", "u.py", "t", statuses, total=10, seconds=1.0)
    assert r["score_covered"] == round(2 / 3, 4)  # killed / (killed + survived)
    assert r["score_global"] == 0.2               # killed / all mutants
    assert r["timeout"] == 1
    assert r["no_tests"] == 10 - 2 - 1 - 1


def test_suite_union_takes_best_status():
    units = [{"unit": "a"}, {"unit": "b"}]
    mutants = [
        {"unit": "a", "mutant": "m1", "status": "survived"},
        {"unit": "b", "mutant": "m1", "status": "killed"},
        {"unit": "a", "mutant": "m2", "status": "survived"},
        {"unit": "b", "mutant": "m2", "status": "no tests"},
    ]
    rows = _suite_rows("s", units, mutants, {"a": "x", "b": "x"}, total=4)
    allrow = rows[0]
    assert (allrow["killed"], allrow["survived"]) == (1, 1)
    assert allrow["score_covered"] == 0.5 and allrow["score_global"] == 0.25
