"""pytest plugin (runs inside the Home Assistant interpreter; stdlib only).

For every test records the SUT functions entered before the test's first assertion:
  TQ_TRACE_OUT       output json path
  TQ_COMPONENT_PART  path fragment identifying SUT files, e.g. homeassistant/components/threshold/
A "first assertion" is the first `assert` statement, the first call of a callable whose name
starts with `assert`, or the first `with pytest.raises(...)` block. Calls evaluated *inside*
the assertion (e.g. `assert await sut()`) happen before it, so the cut-off is the END of the
assertion: tracing stops when execution moves to a later line of the test, or the test ends.
"""

import ast
import inspect
import json
import os
import sys
from pathlib import Path

import pytest

OUT = os.environ.get("TQ_TRACE_OUT", "")
PART = os.environ.get("TQ_COMPONENT_PART", "homeassistant/components/threshold/")
RESULTS: dict[str, dict] = {}
_AST_CACHE: dict[str, ast.Module] = {}


def _first_assert_line(func) -> int | None:
    try:
        path = inspect.getsourcefile(func)
        tree = _AST_CACHE.setdefault(path, ast.parse(Path(path).read_text(encoding="utf-8")))
    except (OSError, TypeError, SyntaxError):
        return None
    node = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == func.__name__),
        None,
    )
    if node is None:
        return None
    best = None  # (start line, end line)
    for sub in ast.walk(node):
        line = None
        if isinstance(sub, ast.Assert):
            line = (sub.lineno, sub.end_lineno)
        elif isinstance(sub, ast.Call):
            f = sub.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name.startswith("assert"):
                line = (sub.lineno, sub.end_lineno)
        elif isinstance(sub, ast.With | ast.AsyncWith):
            for item in sub.items:
                c = item.context_expr
                if isinstance(c, ast.Call):
                    f = c.func
                    name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                    if name in ("raises", "warns"):
                        line = (sub.lineno, sub.end_lineno)
        if line is not None and (best is None or line[0] < best[0]):
            best = line
    return best[1] if best else None


class _State:
    def __init__(self, test_file: str, test_code_name: str, first_assert: int | None):
        self.test_file = test_file
        self.test_name = test_code_name
        self.first_assert = first_assert
        self.done = False
        self.calls: list[str] = []


_state: _State | None = None


def _local(frame, event, arg):
    st = _state
    if st and not st.done and event == "line" and frame.f_code.co_name == st.test_name \
            and st.first_assert is not None and frame.f_lineno > st.first_assert:
        st.done = True
    return _local


def _global(frame, event, arg):
    st = _state
    if st is None or event != "call":
        return None
    fn = frame.f_code.co_filename
    if PART in fn.replace(os.sep, "/"):
        if not st.done:
            module = Path(fn).stem
            qn = frame.f_code.co_qualname.split(".<locals>")[0]
            st.calls.append(f"{module}:{qn}")
        return None
    if fn == st.test_file:
        return _local
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    global _state
    func = getattr(item, "function", None)
    if func is None:
        yield
        return
    fa = _first_assert_line(func)
    _state = _State(inspect.getsourcefile(func) or "", func.__name__, fa)
    sys.settrace(_global)
    try:
        yield
    finally:
        sys.settrace(None)
        st = _state
        calls = st.calls
        RESULTS[item.nodeid] = {
            "has_assert": fa is not None,
            "first_assert_line": fa,
            "called": list(dict.fromkeys(calls)),
            "last": calls[-1] if calls else None,
        }
        _state = None


def pytest_sessionfinish(session, exitstatus):
    if OUT:
        Path(OUT).write_text(json.dumps(RESULTS), encoding="utf-8")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    if _state is not None:
        _state.done = True  # fixture teardown is never "before the first assertion"
    yield
