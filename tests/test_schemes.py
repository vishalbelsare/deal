from __future__ import annotations

import pytest

import deal


try:
    import vaa
except ImportError:
    vaa = None

MarshMallowScheme: object | None
if vaa is None:
    MarshMallowScheme = None
else:
    import marshmallow

    @vaa.marshmallow
    class MarshMallowScheme(marshmallow.Schema):
        name = marshmallow.fields.Str()
        kwargs = marshmallow.fields.Dict(required=False)


class CustomScheme(deal.Scheme):
    def is_valid(self) -> bool:
        if not isinstance(self.data['name'], str):
            self.errors = vaa.Error.parse({'name': ['Not a valid string.']})
            return False
        return True


if MarshMallowScheme:
    SCHEMES = (MarshMallowScheme, CustomScheme)
else:
    SCHEMES = (CustomScheme, )


@pytest.mark.skipif(vaa is None, reason='vaa is not installed')
@pytest.mark.parametrize('scheme', SCHEMES)
def test_scheme_string_validation_args_correct(scheme):
    @deal.pre(scheme)
    def func(name):
        return name * 2

    assert func('Chris') == 'ChrisChris'

    with pytest.raises(deal.PreContractError):
        func(123)

    try:
        func(123)
    except deal.PreContractError as e:
        assert e.args[0] == [vaa.Error(field='name', message='Not a valid string.')]


@pytest.mark.skipif(vaa is None, reason='vaa is not installed')
@pytest.mark.parametrize('scheme', SCHEMES)
def test_method_chain_decorator_with_scheme_is_fulfilled(scheme):
    @deal.pre(scheme)
    @deal.pre(lambda name: name != 'Oleg')
    def func(name):
        return name * 2

    assert func('Chris') == 'ChrisChris'

    with pytest.raises(deal.PreContractError):
        func(123)

    with pytest.raises(deal.PreContractError):
        func('Oleg')


@pytest.mark.skipif(vaa is None, reason='vaa is not installed')
@pytest.mark.parametrize('scheme', SCHEMES)
def test_scheme_contract_is_satisfied_when_setting_arg(scheme):
    @deal.inv(scheme)
    class User:
        name: str | int = ''

    user = User()

    user.name = 'Chris'

    with pytest.raises(deal.InvContractError):
        user.name = 123

    try:
        user.name = 123
    except deal.InvContractError as e:
        assert e.args[0] == [vaa.Error(field='name', message='Not a valid string.')]


@pytest.mark.skipif(vaa is None, reason='vaa is not installed')
@pytest.mark.parametrize('scheme', SCHEMES)
def test_scheme_contract_is_satisfied_within_chain(scheme):
    @deal.inv(lambda user: user.name != 'Oleg')
    @deal.inv(scheme)
    @deal.inv(lambda user: user.name != 'Chris')
    class User:
        name: str | int = ''

    user = User()
    user.name = 'Gram'

    user = User()
    with pytest.raises(deal.InvContractError):
        user.name = 'Oleg'

    user = User()
    with pytest.raises(deal.InvContractError):
        user.name = 123

    user = User()
    with pytest.raises(deal.InvContractError):
        user.name = 'Chris'


@pytest.mark.skipif(vaa is None, reason='vaa is not installed')
@pytest.mark.parametrize('scheme', SCHEMES)
def test_scheme_contract_is_satisfied_when_passing_args(scheme):
    @deal.pre(scheme)
    def func1(name):
        return name * 2

    assert func1('Chris') == 'ChrisChris'
    assert func1(name='Chris') == 'ChrisChris'

    @deal.pre(scheme)
    def func2(**kwargs):
        return kwargs['name'] * 3

    assert func2(name='Chris') == 'ChrisChrisChris'

    @deal.pre(scheme)
    def func3(name='Max'):
        return name * 2

    assert func3() == 'MaxMax'


@pytest.mark.skipif(vaa is None, reason='vaa is not installed')
@pytest.mark.parametrize('scheme', SCHEMES)
def test_scheme_errors_rewrite_message(scheme):
    @deal.pre(scheme, message='old message')
    def func(name):
        return name * 2

    try:
        func(2)
    except deal.PreContractError as exc:
        assert exc.errors == [vaa.Error(field='name', message='Not a valid string.')]
    else:
        raise AssertionError('exception was not raised')


def test_underscore_validator():
    @deal.pre(lambda _: _.a != _.b, message='actual message')
    def func(a, b=1):
        return a + b

    func(2)
    func(1, 3)
    func(a=1, b=3)
    with pytest.raises(deal.PreContractError) as exc_info:
        func(1)
    assert exc_info.value.args == ('actual message',)


def test_underscore_validator_default_message():
    @deal.pre(lambda _: _.a != _.b)
    def func(a, b=1):
        return a + b

    func(2)
    func(1, 3)
    func(a=1, b=3)
    with pytest.raises(deal.PreContractError) as exc_info:
        func(1)
    assert exc_info.value.args == tuple()


@pytest.mark.skipif(vaa is None, reason='vaa is not installed')
def test_default_error():
    """
    If no error provided by the validator, return the default one.
    """
    class CustomScheme(deal.Scheme):
        def is_valid(self) -> bool:
            return isinstance(self.data['name'], str)

    @deal.pre(CustomScheme, message='oh hi mark')
    def func(name):
        return name * 2
    func('hi')
    with pytest.raises(deal.PreContractError) as exc_info:
        func(123)
    assert exc_info.value.message == 'oh hi mark'
