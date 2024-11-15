from __future__ import annotations

import ast
from typing import Iterator, NamedTuple

from ._contract import Category, Contract
from ._extractors import get_contracts, get_definitions


try:
    import astroid
except ImportError:
    astroid = None


class Func(NamedTuple):
    name: str
    body: list
    contracts: list[Contract]
    node: ast.FunctionDef | astroid.FunctionDef

    @property
    def line(self) -> int:
        return self.node.lineno

    @property
    def col(self) -> int:
        return self.node.col_offset

    @property
    def has_self(self) -> bool:
        """Check if the first function argument is `self`.
        """
        args = getattr(self.node.args, 'posonlyargs', None) or self.node.args.args
        if not args:
            return False
        arg = args[0]
        if isinstance(arg, ast.arg):
            return arg.arg == 'self'
        return arg.name == 'self'

    @classmethod
    def from_text(cls, text: str) -> list[Func]:
        if astroid is None:   # pragma: no-astroid
            tree = ast.parse(text)
            return cls.from_ast(tree)
        try:
            tree = astroid.parse(text)
        except astroid.AstroidSyntaxError:  # pragma: no-astroid
            tree = ast.parse(text)
            return cls.from_ast(tree)
        return cls.from_astroid(tree)

    @classmethod
    def from_ast(cls, tree: ast.Module) -> list[Func]:
        funcs = []
        definitions = get_definitions(tree=tree)
        for expr in cls._get_funcs_ast(tree):
            contracts = []
            for cinfo in get_contracts(expr):
                contract = Contract(
                    args=cinfo.args,
                    kwargs=cinfo.kwargs,
                    func_args=expr.args,
                    category=Category(cinfo.name),
                    context=definitions,
                    line=cinfo.line,
                )
                contracts.append(contract)
            funcs.append(cls(
                name=expr.name,
                body=expr.body,
                contracts=contracts,
                node=expr,
            ))
        return funcs

    @classmethod
    def _get_funcs_ast(cls, target: ast.AST) -> Iterator[ast.FunctionDef]:
        if isinstance(target, ast.Module):
            for stmt in target.body:
                yield from cls._get_funcs_ast(stmt)
        elif isinstance(target, ast.FunctionDef):
            yield target
        elif isinstance(target, ast.ClassDef):
            for stmt in target.body:
                if isinstance(stmt, ast.FunctionDef):
                    yield stmt

    @classmethod
    def from_astroid(cls, tree: astroid.Module) -> list[Func]:
        funcs = []
        definitions = get_definitions(tree=tree)
        for expr in cls._get_funcs_astroid(tree):
            # make signature
            code = f'def f({expr.args.as_string()}):0'
            func_args = ast.parse(code).body[0].args  # type: ignore

            # collect contracts
            contracts = []
            for cinfo in get_contracts(expr):
                contract = Contract(
                    args=cinfo.args,
                    kwargs=cinfo.kwargs,
                    func_args=func_args,
                    category=Category(cinfo.name),
                    context=definitions,
                    line=cinfo.line,
                )
                contracts.append(contract)
            assert expr.lineno is not None
            funcs.append(cls(
                name=expr.name,
                body=expr.body,
                contracts=contracts,
                node=expr,
            ))
        return funcs

    @classmethod
    def _get_funcs_astroid(cls, target: astroid.NodeNG) -> Iterator[astroid.FunctionDef]:
        if isinstance(target, astroid.Module):
            for stmt in target.body:
                yield from cls._get_funcs_astroid(stmt)
        elif isinstance(target, astroid.FunctionDef):
            yield target
        elif isinstance(target, astroid.ClassDef):
            for stmt in target.body:
                if isinstance(stmt, astroid.FunctionDef):
                    yield stmt

    def has_contract(self, *categories: Category) -> bool:
        """Check if the function has a contract from any of the given categories.
        """
        for contract in self.contracts:
            if contract.category in categories:
                return True
        return False

    def __repr__(self) -> str:
        cats = ', '.join(contract.category.value for contract in self.contracts)
        return f'{type(self).__name__}({cats})'
