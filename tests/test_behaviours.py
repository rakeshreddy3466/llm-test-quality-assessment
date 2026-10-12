from pathlib import Path

from testquality.behaviours import (
    Behaviour,
    behaviour_statements,
    import_time_lines,
    map_tests,
    reachable_behaviours,
)

SRC = '''"""doc"""
import x

CONST = 1


def func(a):
    if a:
        return 1
    return 2


class K:
    attr = 3

    def method(self):
        return CONST
'''
STM = {"m": [2, 4, 7, 8, 9, 10, 13, 14, 16, 17]}
B = [
    Behaviour("B1", "m.py", (8, 9), "branch a"),
    Behaviour("B2", "m.py", (10, 10), "return 2"),
    Behaviour("B3", "m.py", (4, 4), "module const"),
]


def test_behaviour_statements_uses_inclusive_range():
    assert behaviour_statements(B[0], STM) == {8, 9}


def test_map_tests_threshold_half_of_statements():
    cache = {"u.py": {"tests": {
        "t_half": {"m.py": {"lines": [8]}},          # 1 of 2 statements -> mapped
        "t_none": {"m.py": {"lines": [13]}},
        "t_all": {"m.py": {"lines": [8, 9, 10]}},
    }}}
    got = map_tests(B, STM, cache)
    assert got[("u.py", "t_half")] == {"B1"}
    assert got[("u.py", "t_none")] == set()
    assert got[("u.py", "t_all")] == {"B1", "B2"}


def test_import_time_lines_and_reachability(tmp_path: Path):
    f = tmp_path / "m.py"
    f.write_text(SRC)
    assert {2, 4, 7, 13, 14, 16} <= import_time_lines(f)
    assert 8 not in import_time_lines(f)
    cache = {"u.py": {"tests": {"t": {"m.py": {"lines": [4, 8, 9, 10]}}}}}
    reach = reachable_behaviours(B, STM, cache, tmp_path)
    assert reach == {"B1", "B2"}  # B3 is module level: excluded although a test "covers" it


def test_normalise_docstring_hides_llm_format():
    from testquality.review import normalise_docstring

    src = (
        'async def test_a(hass):\n    """Behaviour: renames the entity.\n\n'
        '    Target: ThresholdSensor.x\n    """\n    assert 1\n'
    )
    out = normalise_docstring(src)
    assert "Behaviour" not in out and "Target" not in out
    assert '"""Renames the entity."""' in out
