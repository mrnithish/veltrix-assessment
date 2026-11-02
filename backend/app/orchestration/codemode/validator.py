"""Static checks on model-written code before it runs in the sandbox.

Allows a small, side-effect-free Python subset: assignments, if/for/while, comprehensions,
try/except, calls to the provided API functions and safe builtins. Blocks imports, dunder
access, string-format tricks, function/class definitions, and anything that touches the
interpreter (eval/exec/open/getattr/...).
"""

from __future__ import annotations

import ast

MAX_CODE_CHARS = 6000

SAFE_BUILTINS = frozenset({
    "len", "range", "min", "max", "sum", "sorted", "enumerate", "zip", "abs", "round", "int", "float", "str",
    "bool", "list", "dict", "set", "tuple", "any", "all", "print", "isinstance", "reversed", "Exception",
    "ValueError", "KeyError", "TypeError", "True", "False", "None",
})
FORBIDDEN_NAMES = frozenset({
    "eval", "exec", "compile", "open", "__import__", "getattr", "setattr", "delattr", "globals", "locals", "vars",
    "input", "breakpoint", "help", "dir", "type", "object", "memoryview", "super", "classmethod", "staticmethod",
    "property", "exit", "quit", "id", "hash", "iter", "next", "format", "bytes", "bytearray",
})
FORBIDDEN_ATTRS = frozenset({"format", "format_map", "mro", "gi_frame", "f_globals", "f_locals", "f_back"})

ALLOWED_NODES = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Name, ast.Load, ast.Store, ast.Del,
    ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp,
    ast.GeneratorExp, ast.comprehension, ast.Call, ast.keyword, ast.Attribute, ast.Subscript, ast.Slice,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.If, ast.For, ast.While, ast.Break,
    ast.Continue, ast.Pass, ast.Try, ast.ExceptHandler, ast.JoinedStr, ast.FormattedValue, ast.Starred,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Not,
    ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.Delete, ast.Raise,
)


class CodeRejected(ValueError):
    pass


def validate_code(code: str, api_names: set[str]) -> ast.Module:
    if not isinstance(code, str) or not code.strip():
        raise CodeRejected("empty code")
    if len(code) > MAX_CODE_CHARS:
        raise CodeRejected(f"code longer than {MAX_CODE_CHARS} characters")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise CodeRejected(f"SyntaxError: {exc.msg} (line {exc.lineno})") from None
    allowed_names = SAFE_BUILTINS | api_names
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise CodeRejected(f"'{type(node).__name__}' is not allowed (line {getattr(node, 'lineno', '?')})")
        if isinstance(node, ast.Name):
            if node.id.startswith("_") and node.id != "_":
                raise CodeRejected(f"name '{node.id}' is not allowed")
            if node.id in FORBIDDEN_NAMES:
                raise CodeRejected(f"'{node.id}' is not allowed")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr in FORBIDDEN_ATTRS:
                raise CodeRejected(f"attribute '{node.attr}' is not allowed")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = node.func.id
            if fn not in allowed_names and not _assigned_somewhere(tree, fn):
                raise CodeRejected(f"unknown function '{fn}'")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            raise CodeRejected("strings containing '__' are not allowed")
    return tree


def _assigned_somewhere(tree: ast.Module, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Store):
            return True
    return False
