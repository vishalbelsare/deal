import typing
from inspect import signature

import hypothesis
import hypothesis.strategies
from pydantic import BaseModel

from .core import Raises, Pre


class TestCase(typing.NamedTuple):
    args: typing.List[typing.Any]
    kwargs: typing.Dict[str, typing.Any]
    func: typing.Callable
    exceptions: typing.Tuple[Exception]

    def __call__(self) -> typing.Any:
        """Calls the given test case returning the called functions result on success or
        Raising an exception on error
        """
        try:
            result = self.func(*self.args, **self.kwargs)
        except self.exceptions:
            return typing.NoReturn
        self._check_result(result)
        return result

    def _check_result(self, result):
        return_type = typing.get_type_hints(self.func).get('return', None)
        if not return_type:
            return

        class ReturnModel(BaseModel):
            __annotations__ = {'returns': return_type}

        ReturnModel(returns=result)


def get_excs(func):
    while True:
        if func.__closure__:
            for cell in func.__closure__:
                obj = cell.cell_contents
                if isinstance(obj, Raises):
                    yield from obj.exceptions
                elif isinstance(obj, Pre):
                    exc = obj.exception
                    if not isinstance(exc, type):
                        exc = type(exc)
                    yield exc

        if not hasattr(func, '__wrapped__'):
            return
        func = func.__wrapped__


def get_examples(func: typing.Callable, kwargs: typing.Dict[str, typing.Any], count: int):
    kwargs = kwargs.copy()
    for name, value in kwargs.items():
        if not isinstance(value, hypothesis.SearchStrategy):
            kwargs[name] = hypothesis.just(value)

    def pass_along_variables(*args, **kwargs):
        return args, kwargs

    pass_along_variables.__signature__ = signature(func)
    pass_along_variables.__annotations__ = getattr(func, '__annotations__', {})
    strategy = hypothesis.strategies.builds(pass_along_variables, **kwargs)
    examples = []

    @hypothesis.given(strategy)
    @hypothesis.settings(
        database=None,
        max_examples=count,
        deadline=None,
        verbosity=hypothesis.Verbosity.quiet,
        phases=(hypothesis.Phase.generate,),
        suppress_health_check=hypothesis.HealthCheck.all(),
    )
    def example_generator(ex):
        examples.append(ex)

    example_generator()
    return examples


def cases(func, runs: int = 50, kwargs: typing.Dict[str, typing.Any] = None) -> None:
    if not kwargs:
        kwargs = {}
    exceptions = tuple(get_excs(func))
    params_generator = get_examples(
        func=func,
        count=runs,
        kwargs=kwargs,
    )
    for args, kwargs in params_generator:
        yield TestCase(
            args=args,
            kwargs=kwargs,
            func=func,
            exceptions=exceptions,
        )
