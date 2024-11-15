from __future__ import annotations

import ast
from typing import NamedTuple

from .common import TOKENS, get_name
from .value import UNKNOWN, get_value


try:
    import astroid
except ImportError:
    astroid = None


class Example(NamedTuple):
    args: list[object]
    kwargs: dict[str, object]
    result: object


def get_example(expr, func_name: str) -> Example | None:
    if not isinstance(expr, TOKENS.COMPARE):
        return None
    if not isinstance(expr.left, TOKENS.CALL):
        return None
    ex = _get_example_from_call(expr.left, func_name)
    if ex is None:
        return None
    result_val = _get_right_value(expr)
    return ex._replace(result=result_val)


def _get_right_value(expr) -> object:
    if isinstance(expr, ast.Compare):
        if len(expr.ops) != 1:
            return UNKNOWN
        if not isinstance(expr.ops[0], (ast.Eq, ast.Is)):
            return UNKNOWN
        return get_value(expr.comparators[0])

    if astroid is not None and isinstance(expr, astroid.Compare):
        if len(expr.ops) != 1:
            return UNKNOWN
        op, right = expr.ops[0]
        if op not in {'==', 'is'}:
            return UNKNOWN
        return get_value(right)

    raise RuntimeError('unreachable')


def _get_example_from_call(expr: ast.Call | astroid.Call, func_name: str) -> Example | None:
    if get_name(expr.func) != func_name:
        return None

    args = []
    for arg in expr.args:
        val = get_value(arg)
        if val is UNKNOWN:
            return None
        args.append(val)

    kwargs: dict[str, object] = {}
    for keyword in (expr.keywords or ()):
        val = get_value(keyword.value)
        if val is UNKNOWN:
            return None
        assert keyword.arg is not None
        kwargs[keyword.arg] = val

    return Example(args, kwargs, None)
