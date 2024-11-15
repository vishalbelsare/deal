from __future__ import annotations

import ast
from typing import Any, Iterator, Sequence

from .common import Extractor, Token, infer
from .contracts import get_contracts
from .value import UNKNOWN, get_value


try:
    import astroid
except ImportError:
    pass


get_pre = Extractor()


@get_pre.register(lambda: astroid.Call)
def handle_call(expr: astroid.Call, context: dict[str, ast.stmt] | None = None) -> Iterator[Token]:
    from .._contract import Category, Contract

    args = []
    for subnode in expr.args:
        value = get_value(expr=subnode)
        if value is UNKNOWN:
            return
        args.append(value)

    kwargs: dict[str, Any] = {}
    for subnode in (expr.keywords or ()):
        value = get_value(expr=subnode.value)
        if value is UNKNOWN:
            return
        kwargs[subnode.arg] = value

    for func in infer(expr.func):
        if not isinstance(func, astroid.FunctionDef):
            continue
        code = f'def f({func.args.as_string()}):0'
        func_ast = ast.parse(code).body[0]
        assert isinstance(func_ast, ast.FunctionDef)
        for cinfo in get_contracts(func):
            if cinfo.name != 'pre':
                continue
            contract = Contract(
                args=cinfo.args,
                kwargs=cinfo.kwargs,
                category=Category.PRE,
                func_args=func_ast.args,
                context=context,
            )
            try:
                result = contract.run(*args, **kwargs)
            except NameError:
                continue
            if result is False or type(result) is str:
                yield Token(
                    value=format_call_args(args, kwargs),
                    marker=result or None,
                    line=expr.lineno,
                    col=expr.col_offset,
                )


def format_call_args(args: Sequence, kwargs: dict[str, Any]) -> str:
    sep = ', '
    args_s = sep.join(map(repr, args))
    items = sorted(kwargs.items())
    kwargs_s = sep.join(f'{k}={repr(v)}' for k, v in items)
    if args and kwargs:
        return args_s + sep + kwargs_s
    return args_s + kwargs_s
