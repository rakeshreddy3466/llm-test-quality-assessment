import ast
import textwrap

import pytest

from testquality.transforms import (
    canonical_dump,
    definitions,
    import_time_order_ok,
    non_definition_statements,
    rename_locals,
    reorder_functions,
    strip_comments,
)

SRC = textwrap.dedent('''
    """Module doc."""
    import logging

    # a module comment
    LOG = logging.getLogger(__name__)  # trailing comment


    def validate(value):
        """Validate."""
        # check
        if value is None:  # none?
            raise ValueError("x")
        return value


    SCHEMA = validate(1)


    async def setup(hass, entry):
        """Set up."""
        registry = hass.get()
        total = 0
        for item in registry:
            total += item
        def inner():
            return total
        return inner()


    def helper(a, b=2):
        result = a + b
        return result


    class Sensor:
        """A sensor."""

        attr = 3

        def __init__(self, name):
            self.name = name
            value = name.upper()
            self.value = value

        @property
        def label(self):
            text = self.name
            return text

        def run(self, *, flag):
            outcome = flag
            return outcome
''')


def test_strip_comments_keeps_ast_and_removes_hash():
    out = strip_comments(SRC)
    assert "#" not in out
    assert ast.dump(ast.parse(out)) == ast.dump(ast.parse(SRC))
    assert "Module doc." in out  # docstrings kept


def test_rename_locals_is_alpha_equivalent_but_different_text():
    out = rename_locals(SRC)
    assert out != SRC
    assert canonical_dump(out) == canonical_dump(SRC)
    assert "loc_registry" in out and "loc_total" in out and "loc_result" in out
    # parameters, attributes and keyword names are untouched
    assert "def helper(a, b=2)" in out and "self.value" in out and "*, flag" in out
    assert "loc_value = name.upper()" in out


def test_rename_locals_changes_semantics_check_is_sensitive():
    broken = SRC.replace("return result", "return a")
    assert canonical_dump(broken) != canonical_dump(SRC)


def test_reorder_functions_preserves_definitions_and_import_order():
    out = reorder_functions(SRC)
    assert out != SRC
    assert definitions(out) == definitions(SRC)
    assert non_definition_statements(out) == non_definition_statements(SRC)
    assert import_time_order_ok(out)
    # `validate` is used at import time (SCHEMA) so it must not have moved
    assert out.index("def validate") < out.index("SCHEMA = validate(1)")
    # methods were reversed
    assert out.index("def run") < out.index("def __init__")


def test_import_time_order_checker_detects_violation():
    bad = "X = f()\n\n\ndef f():\n    return 1\n"
    assert not import_time_order_ok(bad)
    assert import_time_order_ok("def f():\n    return 1\n\n\nX = f()\n")


@pytest.mark.parametrize("fn", [strip_comments, rename_locals, reorder_functions])
def test_transforms_emit_valid_python(fn):
    compile(fn(SRC), "<t>", "exec")


def test_strip_comments_is_idempotent():
    assert strip_comments(strip_comments(SRC)) == strip_comments(SRC)


def test_reorder_is_an_involution():
    assert reorder_functions(reorder_functions(SRC)) == SRC
