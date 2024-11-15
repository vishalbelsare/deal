from __future__ import annotations

import inspect
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Callable

from .._exceptions import ContractError
from .._types import ExceptionType


try:
    import vaa
except ImportError:
    vaa = None


if TYPE_CHECKING:
    Args = tuple[object, ...]
    Kwargs = dict[str, object]


@lru_cache(maxsize=16)
def _get_signature(function: Callable) -> inspect.Signature:
    return inspect.signature(function)


def _args_to_vars(
    *,
    args: Args,
    kwargs: Kwargs,
    signature: inspect.Signature | None,
    keep_result: bool = True,
) -> dict[str, object]:
    """Convert args and kwargs into dict of params based on the given function.

    For simple validators the validator is passed as function.
    """
    if signature is None:
        return kwargs

    params = kwargs.copy()
    # Do not pass argument named `result` into the function.
    # It is a hack for `deal.ensure` with `vaa` validator.
    if not keep_result and 'result' in kwargs:
        kwargs = kwargs.copy()
        del kwargs['result']

    # assign *args to real names
    for name, param in signature.parameters.items():
        params[name] = param.default
    params.update(signature.bind(*args, **kwargs).arguments)
    return params


class AttrDict(dict):
    __slots__ = ()

    def __getattr__(self, name: str):
        return self[name]


class Validator:
    __slots__ = (
        'exception',
        'signature',
        'validate',
        'validator',
        'raw_validator',
        'message',
        'function',
    )

    exception: ExceptionType
    signature: inspect.Signature | None
    validate: Any
    validator: Any
    raw_validator: Any
    message: str | None
    function: Any

    def __init__(
        self,
        validator, *,
        message: str | None = None,
        exception: ExceptionType,
    ) -> None:
        self.validate = self._init
        self.raw_validator = validator
        self.message = message
        self.exception = exception
        self.function = None
        if message and isinstance(self.exception, type):
            self.exception = self.exception(message)

    @property
    def exception_type(self) -> type[Exception]:
        if isinstance(self.exception, Exception):
            return type(self.exception)
        return self.exception

    def _exception(
        self, *,
        message: str | None = None,
        errors: Kwargs | None = None,
        params: Kwargs | None = None,
    ) -> Exception:
        exception = self.exception
        if isinstance(exception, Exception):
            if not message and exception.args:
                message = exception.args[0]
            exception = type(exception)

        # raise beautiful ContractError
        if issubclass(exception, ContractError):
            return exception(
                message=message or '',
                validator=self.validator,
                errors=errors,
                params=params,
                origin=getattr(self, 'function', None),
            )

        # raise boring custom exception
        args: list[Any] = []
        if message:
            args.append(message)
        if errors:
            args.append(errors)
        return exception(*args)

    def _wrap_vaa(self) -> Any | None:
        if vaa is None:  # pragma: no cover
            return None
        try:
            return vaa.wrap(self.raw_validator, simple=False)
        except TypeError:
            pass
        if hasattr(self.raw_validator, 'is_valid'):
            return self.raw_validator
        return None

    def init(self) -> None:
        # implicitly wrap in vaa.simple only funcs with one `_` argument.
        self.signature = None
        val_signature = _get_signature(self.raw_validator)

        # validator with a short signature
        if set(val_signature.parameters) == {'_'}:
            self.validator = self.raw_validator
            self.validate = self._short_validation
            if self.function is not None:
                self.signature = _get_signature(self.function)
            return

        vaa_validator = self._wrap_vaa()
        if vaa_validator is None:
            # vaa validator
            self.validator = self.raw_validator
            self.validate = self._explicit_validation
            self.signature = val_signature
        else:
            # validator with the same signature as the function
            self.validator = vaa_validator
            self.validate = self._vaa_validation
            if self.function is not None:
                self.signature = _get_signature(self.function)

    def _init(self, args: Args, kwargs: Kwargs, exc=None) -> None:
        """
        Called as `validator` when the function is called in the first time.
        Does some costly deferred initializations (involving `inspect`).
        Then sets more appropriate validator as `validator` and calls it.
        """
        self.init()
        self.validate(args, kwargs, exc)

    def _vaa_validation(self, args: Args, kwargs: Kwargs, exc=None) -> None:
        """Validate contract using vaa wrapped validator.
        """

        # if it is a decorator for a function, convert positional args into named ones.
        params = _args_to_vars(
            args=args,
            kwargs=kwargs,
            signature=self.signature,
            keep_result=False,
        )

        # validate
        validator = self.validator(data=params)
        if validator.is_valid():
            return

        # if no errors returned, raise the default exception
        errors = validator.errors
        if not errors:
            raise self._exception(params=params) from exc

        raise self._exception(errors=errors, params=params) from exc

    def _explicit_validation(self, args: Args, kwargs: Kwargs, exc=None) -> None:
        """Validate contract using explicit validator.

        Explicit validator is a function that has the same signature
        as the wrapped function.
        """
        validation_result = self.validator(*args, **kwargs)
        # is invalid (validator returns error message)
        if type(validation_result) is str:
            params = _args_to_vars(args=args, kwargs=kwargs, signature=self.signature)
            raise self._exception(message=validation_result, params=params) from exc
        # is valid (truely result)
        if validation_result:
            return
        # is invalid (falsy result)
        params = _args_to_vars(args=args, kwargs=kwargs, signature=self.signature)
        raise self._exception(params=params) from exc

    def _short_validation(self, args: Args, kwargs: Kwargs, exc=None) -> None:
        """Validate contract using short validator.

        Short validator is a function that has a short signature
        (accepts only one `_` argument).
        """
        params = _args_to_vars(
            args=args,
            kwargs=kwargs,
            signature=self.signature,
            keep_result=False,
        )
        validation_result = self.validator(AttrDict(params))
        # is invalid (validator returns error message)
        if type(validation_result) is str:
            raise self._exception(message=validation_result, params=params) from exc
        # is valid (truely result)
        if validation_result:
            return
        # is invalid (falsy result)
        raise self._exception(params=params) from exc


class RaisesValidator(Validator):
    __slots__ = ('exceptions', )
    exceptions: tuple[type[Exception]]

    def __init__(self, exceptions, exception, message) -> None:
        self.exceptions = exceptions
        self.validator = None
        super().__init__(validator=None, message=message, exception=exception)

    def init(self) -> None:
        self.signature = _get_signature(self.function)
        self.validate = self._validate

    def _init(self, args: Args, kwargs: Kwargs, exc=None) -> None:
        self.init()
        self.validate(args, kwargs, exc=exc)

    def _validate(self, args: Args, kwargs: Kwargs, exc: Exception | None = None) -> None:
        assert exc is not None
        exc_type = type(exc)
        if exc_type in self.exceptions:
            return
        raise self._exception() from exc_type


class ReasonValidator(Validator):
    __slots__ = ('event', )
    event: type[Exception]

    def __init__(self, event, **kwargs) -> None:
        self.event = event
        super().__init__(**kwargs)


class InvariantValidator(Validator):
    def _vaa_validation(self, args: Args, kwargs: Kwargs, exc=None) -> None:
        return super()._vaa_validation((), vars(args[0]), exc=exc)

    def _short_validation(self, args: Args, kwargs: Kwargs, exc=None) -> None:
        return super()._short_validation((), vars(args[0]), exc=exc)
