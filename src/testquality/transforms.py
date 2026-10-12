"""Semantics-preserving transformations of the component source shown to the LLM (MR2-MR4).

Each transform has a checker proving the meaning is kept (see tests/test_transforms.py):
  strip_comments    -> identical AST (comments are not part of the AST)
  rename_locals     -> identical AST after canonical renaming of local variables
  reorder_functions -> identical set of definitions, import-time statements keep their order
                       and never reference a name defined later
"""

from __future__ import annotations

import ast
import io
import tokenize

FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)


# --------------------------------------------------------------------------------------------
# MR4: strip comments
# --------------------------------------------------------------------------------------------
def strip_comments(source: str) -> str:
    """Remove `#` comments (docstrings are kept); trailing whitespace is trimmed."""
    out_lines = source.splitlines(keepends=True)
    cuts: dict[int, int] = {}
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            cuts[tok.start[0]] = tok.start[1]
    for line_no, col in cuts.items():
        line = out_lines[line_no - 1]
        stripped = line[:col].rstrip()
        out_lines[line_no - 1] = (stripped + "\n") if stripped else ""
    return "".join(out_lines)


# --------------------------------------------------------------------------------------------
# MR2: rename local variables
# --------------------------------------------------------------------------------------------
def _params(fn: ast.AST) -> set[str]:
    a = fn.args
    names = {x.arg for x in [*a.posonlyargs, *a.args, *a.kwonlyargs]}
    if a.vararg:
        names.add(a.vararg.arg)
    if a.kwarg:
        names.add(a.kwarg.arg)
    return names


def _local_names(fn: ast.AST) -> set[str]:
    """Names assigned inside `fn` (incl. nested scopes) that are not parameters/global."""
    stored: set[str] = set()
    params: set[str] = set()
    declared: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, (*FUNC, ast.Lambda)):
            params |= _params(node)
        elif isinstance(node, ast.Global | ast.Nonlocal):
            declared |= set(node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            stored.add(node.id)
    return stored - params - declared


def _all_names(tree: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)
    }


def rename_locals(source: str, prefix: str = "loc_") -> str:
    """Rename every local variable (never parameters, attributes or keyword names)."""
    tree = ast.parse(source)
    taken = _all_names(tree)
    edits: list[tuple[int, int, int, str]] = []  # line, col, end_col, new text
    for top in ast.walk(tree):
        if not isinstance(top, FUNC):
            continue
        locs = _local_names(top)
        # only handle the outermost function owning the variable: skip nested functions' own
        # walk by requiring that no enclosing function already renamed it
        mapping = {n: f"{prefix}{n.lstrip('_')}" for n in sorted(locs)}
        if any(new in taken for new in mapping.values()):
            raise ValueError("renaming would collide with an existing name")
        for node in ast.walk(top):
            if isinstance(node, ast.Name) and node.id in mapping:
                edits.append((node.lineno, node.col_offset, node.end_col_offset, mapping[node.id]))
    lines = source.splitlines(keepends=True)
    # de-duplicate (nested functions are walked by their parents too) and apply right-to-left
    for line, col, end, new in sorted(set(edits), reverse=True):
        text = lines[line - 1]
        lines[line - 1] = text[:col] + new + text[end:]
    return "".join(lines)


class _Canon(ast.NodeTransformer):
    """Rename local variables to v0, v1, ... in order of first appearance, per function."""

    def visit_FunctionDef(self, node):
        return self._fn(node)

    def visit_AsyncFunctionDef(self, node):
        return self._fn(node)

    def _fn(self, node):
        locs = _local_names(node)
        order: dict[str, str] = {}
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in locs and sub.id not in order:
                order[sub.id] = f"v{len(order)}"
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in order:
                sub.id = order[sub.id]
        return node


def canonical_dump(source: str) -> str:
    return ast.dump(_Canon().visit(ast.parse(source)))


# --------------------------------------------------------------------------------------------
# MR3: reorder functions
# --------------------------------------------------------------------------------------------
def _top_level_refs(tree: ast.Module) -> set[str]:
    """Names referenced by import-time statements (everything outside function bodies)."""
    refs: set[str] = set()

    def visit(stmts):
        for s in stmts:
            if isinstance(s, FUNC):
                for dec in s.decorator_list:
                    refs.update(n.id for n in ast.walk(dec) if isinstance(n, ast.Name))
                for d in [*s.args.defaults, *s.args.kw_defaults]:
                    if d is not None:
                        refs.update(n.id for n in ast.walk(d) if isinstance(n, ast.Name))
            elif isinstance(s, ast.ClassDef):
                for b in [*s.bases, *s.decorator_list, *[k.value for k in s.keywords]]:
                    refs.update(n.id for n in ast.walk(b) if isinstance(n, ast.Name))
                visit(s.body)
            else:
                refs.update(n.id for n in ast.walk(s) if isinstance(n, ast.Name))

    visit(tree.body)
    return refs


def _segments(source: str, nodes: list[ast.stmt]) -> list[tuple[int, int]]:
    """(first line, last line) incl. decorators and contiguous preceding comment lines."""
    lines = source.splitlines()
    out = []
    for n in nodes:
        first = min([n.lineno, *[d.lineno for d in getattr(n, "decorator_list", [])]])
        while first > 1 and lines[first - 2].lstrip().startswith("#"):
            first -= 1
        out.append((first, n.end_lineno))
    return out


def _permute(source: str, group: list[ast.stmt]) -> str:
    """Reverse the order of `group` statements, keeping each in the other's slot."""
    if len(group) < 2:
        return source
    lines = source.splitlines(keepends=True)
    segs = _segments(source, group)
    texts = ["".join(lines[a - 1 : b]) for a, b in segs]
    # replace from the bottom so earlier line numbers stay valid
    for (a, b), new in zip(reversed(segs), texts, strict=True):  # reversed(segs) x texts
        lines[a - 1 : b] = [new if new.endswith("\n") else new + "\n"]
    return "".join(lines)


def reorder_functions(source: str) -> str:
    """Reverse the order of (a) free-standing top-level functions that no import-time statement
    references and (b) the methods of every class. Everything else keeps its position."""
    tree = ast.parse(source)
    refs = _top_level_refs(tree)
    free = [n for n in tree.body if isinstance(n, FUNC) and n.name not in refs
            and not n.decorator_list]
    out = _permute(source, free)
    for cls_name in [n.name for n in tree.body if isinstance(n, ast.ClassDef)]:
        cls = next(n for n in ast.parse(out).body
                   if isinstance(n, ast.ClassDef) and n.name == cls_name)
        out = _permute(out, [n for n in cls.body if isinstance(n, FUNC)])
    return out


def definitions(source: str) -> dict[str, str]:
    """qualified name -> ast.dump for every function / class in the module."""
    tree = ast.parse(source)
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, FUNC):
            out[node.name] = ast.dump(node)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, FUNC):
                    out[f"{node.name}.{sub.name}"] = ast.dump(sub)
    return out


def _import_refs(node: ast.stmt) -> set[str]:
    """Names evaluated when `node` is executed at import time (function bodies excluded)."""
    refs: set[str] = set()
    if isinstance(node, FUNC):
        for part in [*node.decorator_list, *node.args.defaults,
                     *[d for d in node.args.kw_defaults if d is not None]]:
            refs.update(n.id for n in ast.walk(part) if isinstance(n, ast.Name))
    elif isinstance(node, ast.ClassDef):
        for part in [*node.bases, *node.decorator_list, *[k.value for k in node.keywords]]:
            refs.update(n.id for n in ast.walk(part) if isinstance(n, ast.Name))
        for member in node.body:
            refs |= _import_refs(member)
    else:
        refs.update(n.id for n in ast.walk(node) if isinstance(n, ast.Name))
    return refs


def import_time_order_ok(source: str) -> bool:
    """No import-time evaluation may reference a module-level function defined after it."""
    tree = ast.parse(source)
    funcs = {n.name for n in tree.body if isinstance(n, FUNC)}
    defined: set[str] = set()
    for node in tree.body:
        if (_import_refs(node) & funcs) - defined:
            return False
        if isinstance(node, FUNC):
            defined.add(node.name)
    return True


def non_definition_statements(source: str) -> list[str]:
    """Import-time statements in order; classes contribute everything except their methods."""
    tree = ast.parse(source)
    out = []
    for n in tree.body:
        if isinstance(n, FUNC):
            continue
        if isinstance(n, ast.ClassDef):
            n.body = [b for b in n.body if not isinstance(b, FUNC)]
        out.append(ast.dump(n))
    return out
