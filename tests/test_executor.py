from pathlib import Path

from testquality.executor import (
    classify_error,
    error_counts,
    parse_junit,
    staged_files,
    summarise,
    write_keyed_csv,
)
from tests.test_generate import fake_settings

JUNIT = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest">
<testcase classname="tests.components.threshold._llm_generated.r1.test_a" name="test_ok"/>
<testcase classname="tests.components.threshold._llm_generated.r1.test_a" name="test_bad">
  <failure message="assert 1 == 2" type="AssertionError">E assert 1 == 2</failure></testcase>
<testcase classname="tests.components.threshold._llm_generated.r1.test_a" name="test_skip">
  <skipped message="why"/></testcase>
<testcase classname="" name="tests.components.threshold._llm_generated.r1.test_b">
  <error message="collection failure" type="">E   ModuleNotFoundError: No module named 'x'</error>
</testcase>
</testsuite></testsuites>"""


def test_classify_error():
    assert classify_error("", "", "E   ModuleNotFoundError: x") == "ModuleNotFoundError"
    assert classify_error("AssertionError", "assert 1 == 2") == "AssertionError"
    assert classify_error("", "fixture 'foo' not found") == "FixtureLookupError"
    assert classify_error("", "something odd") == "Other"


def test_parse_junit(tmp_path):
    x = tmp_path / "j.xml"
    x.write_text(JUNIT)
    out = parse_junit(x)
    by = {(o.unit, o.test): o for o in out}
    assert by[("test_a.py", "test_ok")].outcome == "passed"
    assert by[("test_a.py", "test_bad")].outcome == "failed"
    assert by[("test_a.py", "test_bad")].error_type == "AssertionError"
    assert by[("test_a.py", "test_skip")].outcome == "skipped"
    coll = [o for o in out if o.outcome == "collect_error"]
    assert len(coll) == 1 and coll[0].error_type == "ModuleNotFoundError"


def _rows(outcomes_by_repeat):
    rows = []
    for rep, outs in enumerate(outcomes_by_repeat, 1):
        for name, o in outs.items():
            rows.append({"suite": "s", "unit": "u.py", "test": name, "repeat": rep,
                         "outcome": o, "error_type": "AssertionError" if o == "failed" else ""})
    return rows


def test_summarise_flaky_and_pass_rates():
    rows = _rows([
        {"a": "passed", "b": "passed", "c": "failed"},
        {"a": "passed", "b": "failed", "c": "failed"},
        {"a": "passed", "b": "passed", "c": "failed"},
    ])
    s = summarise("s", rows, units_requested=2, repeats=3, secs=[1, 1, 1])
    assert s["tests_collected"] == 3
    assert s["flaky_tests"] == 1
    assert s["stable_pass_rate"] == round(1 / 3, 4)
    assert s["collect_rate"] == 0.5
    assert s["pass_rate_min"] == round(1 / 3, 4)
    assert s["pass_rate_max"] == round(2 / 3, 4)


def test_error_counts_dedupes_across_repeats():
    rows = _rows([{"c": "failed"}, {"c": "failed"}])
    assert error_counts("s", rows) == [{"suite": "s", "error_type": "AssertionError", "count": 1}]


def test_write_keyed_csv_replaces_suite(tmp_path):
    p = tmp_path / "r.csv"
    write_keyed_csv(p, ["suite", "v"], [{"suite": "a", "v": "1"}, {"suite": "b", "v": "2"}])
    write_keyed_csv(p, ["suite", "v"], [{"suite": "a", "v": "9"}])
    text = p.read_text().splitlines()
    assert "a,9" in text and "b,2" in text and "a,1" not in text


def test_staged_files_are_removed_even_on_error(tmp_path):
    s = fake_settings(tmp_path)
    f = tmp_path / "test_x.py"
    f.write_text("def test_x():\n    pass\n")
    try:
        with staged_files(s, "run1", [f]) as dest:
            assert (dest / "test_x.py").exists() and (dest / "__init__.py").exists()
            raise RuntimeError
    except RuntimeError:
        pass
    assert not (s.generated_tests_dir / "run1").exists()
    assert not s.generated_tests_dir.exists()
    assert isinstance(dest, Path)


def test_staging_root_removed_with_pycache(tmp_path):
    s = fake_settings(tmp_path)
    f = tmp_path / "test_x.py"
    f.write_text("x = 1\n")
    with staged_files(s, "run2", [f]):
        (s.generated_tests_dir / "__pycache__").mkdir()
    assert not s.generated_tests_dir.exists()
