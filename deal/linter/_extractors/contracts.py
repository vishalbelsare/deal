from __future__ import annotations

import ast
from typing import Iterator, NamedTuple

from .common import TOKENS, get_name


try:
    import astroid
except ImportError:
    astroid = None


SUPPORTED_CONTRACTS = frozenset({
    'deal.ensure',
    'deal.example',
    'deal.has',
    'deal.post',
    'deal.pre',
    'deal.pure',
    'deal.raises',
    'deal.safe',
})
SUPPORTED_MARKERS = frozenset({'deal.pure', 'deal.safe', 'deal.inherit'})


class ContractInfo(NamedTuple):
    name: str
    args: list[ast.expr | astroid.NodeNG]
    kwargs: list[ast.keyword | astroid.Keyword]
    line: int


def get_contracts(
    func: ast.FunctionDef | astroid.FunctionDef | astroid.UnboundMethod,
) -> Iterator[ContractInfo]:
    if isinstance(func, ast.FunctionDef):
        yield from _get_contracts(func.decorator_list)
        return
    if func.decorators is None:
        return
    yield from _get_contracts(func.decorators.nodes)


def _get_contracts(decorators: list) -> Iterator[ContractInfo]:
    for contract in decorators:
        if isinstance(contract, TOKENS.ATTR):
            name = get_name(contract)
            if name not in SUPPORTED_MARKERS:
                continue
            yield ContractInfo(
                name=name.split('.')[-1],
                args=[],
                kwargs=[],
                line=contract.lineno,
            )
            if name == 'deal.inherit':
                yield from _resolve_inherit(contract)

        if isinstance(contract, TOKENS.CALL):
            if not isinstance(contract.func, TOKENS.ATTR):
                continue
            name = get_name(contract.func)
            if name == 'deal.chain':
                yield from _get_contracts(contract.args)
            if name not in SUPPORTED_CONTRACTS:
                continue
            yield ContractInfo(
                name=name.split('.')[-1],
                args=contract.args,
                kwargs=contract.keywords,
                line=contract.lineno,
            )

        # infer assigned value
        if astroid is not None and isinstance(contract, astroid.Name):
            assigments = contract.lookup(contract.name)[1]
            if not assigments:
                continue
            # use only the closest assignment
            expr = assigments[0]
            # can it be not an assignment? IDK
            if not isinstance(expr, astroid.AssignName):  # pragma: no cover
                continue
            expr = expr.parent
            if not isinstance(expr, astroid.Assign):  # pragma: no cover
                continue
            yield from _get_contracts([expr.value])


def _resolve_inherit(contract: ast.Attribute | astroid.Attribute) -> Iterator[ContractInfo]:
    if astroid is None or not isinstance(contract, astroid.Attribute):
        return
    cls = _get_parent_class(contract)
    if cls is None:
        return
    func = _get_parent_func(contract)
    for base_class in cls.ancestors():
        assert isinstance(base_class, astroid.ClassDef)
        for method in base_class.mymethods():
            assert isinstance(method, astroid.FunctionDef)
            if method.name != func.name:
                continue
            yield from get_contracts(method)


def _get_parent_class(node) -> astroid.ClassDef | None:
    if isinstance(node, astroid.ClassDef):
        return node
    if isinstance(node, (astroid.Attribute, astroid.FunctionDef, astroid.Decorators)):
        return _get_parent_class(node.parent)
    return None


def _get_parent_func(node) -> astroid.FunctionDef:
    if isinstance(node, (astroid.Attribute, astroid.Decorators)):
        return _get_parent_func(node.parent)
    assert isinstance(node, astroid.FunctionDef)
    return node
