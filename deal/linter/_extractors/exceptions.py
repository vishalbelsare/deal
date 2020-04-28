# built-in
import ast
import builtins
from typing import Iterator

# external
import astroid

# app
from .common import TOKENS, Token, get_name, traverse
from .contracts import get_contracts
from .._stub import StubsManager


def get_exceptions(body: list, *, dive: bool = True, stubs: StubsManager = None) -> Iterator[Token]:
    for expr in traverse(body):
        token_info = dict(line=expr.lineno, col=expr.col_offset)

        # assert
        if isinstance(expr, TOKENS.ASSERT):
            yield Token(value=AssertionError, **token_info)
            continue

        # explicit raise
        if isinstance(expr, TOKENS.RAISE):
            name = get_name(expr.exc)
            if not name:
                # raised a value, too tricky
                if not isinstance(expr.exc, TOKENS.CALL):
                    continue
                # raised an instance of an exception
                name = get_name(expr.exc.func)
                if not name or name[0].islower():
                    continue
            exc = getattr(builtins, name, name)
            token_info['col'] = expr.exc.col_offset
            yield Token(value=exc, **token_info)
            continue

        # division by zero
        if isinstance(expr, TOKENS.BIN_OP):
            if isinstance(expr.op, ast.Div) or expr.op == '/':
                if isinstance(expr.right, astroid.Const) and expr.right.value == 0:
                    token_info['col'] = expr.right.col_offset
                    yield Token(value=ZeroDivisionError, **token_info)
                    continue
                if isinstance(expr.right, ast.Num) and expr.right.n == 0:
                    token_info['col'] = expr.right.col_offset
                    yield Token(value=ZeroDivisionError, **token_info)
                    continue

        # exit()
        if isinstance(expr, TOKENS.CALL):
            name = get_name(expr.func)
            if name and name == 'exit':
                yield Token(value=SystemExit, **token_info)
                continue
            # sys.exit()
            if isinstance(expr.func, TOKENS.ATTR):
                name = get_name(expr.func)
                if name and name == 'sys.exit':
                    yield Token(value=SystemExit, **token_info)
                    continue

        # infer function call and check the function body for raises
        if dive:
            yield from _exceptions_from_funcs(expr=expr)


def _exceptions_from_funcs(expr) -> Iterator[Token]:
    for name_node in get_names(expr):
        # node have to be a name
        if type(name_node) is not astroid.Name:
            continue

        # get possible definitions
        try:
            guesses = tuple(name_node.infer())
        except astroid.exceptions.NameInferenceError:
            continue

        extra = dict(
            line=name_node.lineno,
            col=name_node.col_offset,
        )
        for value in guesses:
            if type(value) is not astroid.FunctionDef:
                continue

            # recursively infer exceptions from the function body
            for error in get_exceptions(body=value.body, dive=False):
                yield Token(value=error.value, **extra)

            # get explicitly specified exceptions from `@deal.raises`
            if not value.decorators:
                continue
            for category, args in get_contracts(value.decorators.nodes):
                if category != 'raises':
                    continue
                for arg in args:
                    name = get_name(arg)
                    if name is None:
                        continue
                    yield Token(value=name, **extra)


def get_names(expr):
    if isinstance(expr, astroid.Assign):
        yield from get_names(expr.value)
    if isinstance(expr, TOKENS.CALL):
        if isinstance(expr.func, TOKENS.NAME):
            yield expr.func
        for subnode in expr.args:
            yield from get_names(subnode)
        for subnode in (expr.keywords or ()):
            yield from get_names(subnode.value)
