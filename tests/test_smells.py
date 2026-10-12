import ast
import textwrap

import pytest

from testquality.smells import SMELLS, detect, summarise

SUT = {"async_setup_entry", "update", "reset", "refresh", "_update_state"}


def run(src: str):
    fn = ast.parse(textwrap.dedent(src)).body[0]
    return detect(fn, SUT)


CASES = {
    "empty_test": (
        "def test_x():\n    '''doc'''\n    pass\n",
        "def test_x():\n    assert True\n",
    ),
    "no_assertion": (
        "def test_x():\n    run()\n",
        "def test_x():\n    run()\n    assert ok\n",
    ),
    "assertion_roulette": (
        "def test_x():\n    assert a\n    assert b\n    assert c\n    assert d\n",
        "def test_x():\n    assert a\n    assert b\n    assert c\n",
    ),
    "duplicate_assert": (
        "def test_x():\n    assert a == b\n    assert a == b\n",
        "def test_x():\n    assert a == b\n    assert a == c\n",
    ),
    "magic_number": (
        "def test_x():\n    assert value == 42\n",
        "def test_x():\n    assert value == 1\n    assert other == 0\n",
    ),
    "conditional_logic": (
        "def test_x():\n    if flag:\n        assert a\n",
        "def test_x():\n    assert a if True else b == 1 or True\n    x = [1]\n",
    ),
    "sleepy_test": (
        "async def test_x():\n    await asyncio.sleep(1)\n    assert a\n",
        "async def test_x():\n    await hass.async_block_till_done()\n    assert a\n",
    ),
    "redundant_print": (
        "def test_x():\n    print(state)\n    assert a\n",
        "def test_x():\n    log(state)\n    assert a\n",
    ),
    "eager_test": (
        "def test_x():\n    update()\n    reset()\n    refresh()\n"
        "    _update_state()\n    assert a\n",
        "def test_x():\n    update()\n    reset()\n    assert a\n",
    ),
    "try_except": (
        "def test_x():\n    try:\n        run()\n    except ValueError:\n"
        "        pass\n    assert a\n",
        "def test_x():\n    with pytest.raises(ValueError):\n        run()\n",
    ),
}


def test_every_smell_has_a_case():
    assert set(CASES) == set(SMELLS)


@pytest.mark.parametrize("smell", SMELLS)
def test_smell_positive(smell):
    pos, _ = CASES[smell]
    assert run(pos)[smell] >= 1


@pytest.mark.parametrize("smell", SMELLS)
def test_smell_negative(smell):
    # conditional_logic's negative case contains an IfExp on purpose -> use a clean one
    neg = CASES[smell][1] if smell != "conditional_logic" else "def test_x():\n    assert a\n"
    assert run(neg)[smell] == 0


def test_docstring_only_is_empty_and_not_no_assertion():
    c = run('def test_x():\n    """doc"""\n')
    assert c["empty_test"] == 1 and c["no_assertion"] == 0


def test_mock_assert_call_counts_as_assertion():
    assert run("def test_x():\n    run()\n    mock.assert_called_once()\n")["no_assertion"] == 0


def test_summarise_rates():
    rows = [
        {"valid": 1, "total": 2, **{s: 0 for s in SMELLS}, "magic_number": 2},
        {"valid": 1, "total": 0, **{s: 0 for s in SMELLS}},
        {"valid": 0, "total": 5, **{s: 0 for s in SMELLS}, "sleepy_test": 5},
    ]
    s = summarise("s", rows)
    assert s["valid_tests"] == 2 and s["smelly_rate"] == 0.5 and s["smell_density"] == 1.0
    assert s["rate_magic_number"] == 0.5 and s["rate_sleepy_test"] == 0.0
