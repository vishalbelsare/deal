# built-in
import json
from importlib import import_module
from pathlib import Path

# external
import pytest

# project
from deal.linter._contract import Category
from deal.linter._stub import StubFile, StubsManager, _get_funcs, generate_stub


def test_generate_stub(tmp_path: Path):
    root = tmp_path / 'project'
    root.mkdir()
    (root / '__init__.py').touch()
    source_path = (root / 'example.py')
    source_path.write_text("def func(): 1/0")
    stub_path = generate_stub(path=source_path)
    content = json.loads(stub_path.read_text())
    assert stub_path.name == 'example.json'
    assert stub_path.parent == root
    assert content == {'func': {'raises': ['ZeroDivisionError']}}


def test_generate_stub_bad_ext(tmp_path: Path):
    path = tmp_path / 'example.com'
    with pytest.raises(ValueError, match='invalid.* file extension.*'):
        generate_stub(path=path)


def test_do_not_dump_empty_stub(tmp_path: Path):
    root = tmp_path / 'project'
    root.mkdir()
    (root / '__init__.py').touch()
    source_path = (root / 'example.py')
    source_path.write_text("def func(): return 1")
    stub_path = generate_stub(path=source_path)
    assert not stub_path.exists()
    assert stub_path.name == 'example.json'
    assert stub_path.parent == root


def test_stub_file(tmp_path: Path):
    path = tmp_path / 'example.json'
    stub = StubFile(path=path)

    # add
    stub.add(func='fname', contract=Category.RAISES, value='TypeError')
    with pytest.raises(ValueError, match='unsupported contract'):
        stub.add(func='fname', contract=Category.POST, value='SyntaxError')
    assert stub._content == {'fname': {'raises': ['TypeError']}}

    # get
    assert stub.get(func='fname', contract=Category.RAISES) == frozenset({'TypeError'})
    with pytest.raises(ValueError, match='unsupported contract'):
        stub.get(func='fname', contract=Category.POST)
    assert stub.get(func='unknown', contract=Category.RAISES) == frozenset()

    # dump
    stub.dump()
    content = json.loads(path.read_text(encoding='utf8'))
    assert content == {'fname': {'raises': ['TypeError']}}

    # load
    stub2 = StubFile(path=path)
    stub2.load()
    assert stub2._content == {'fname': {'raises': ['TypeError']}}


@pytest.mark.parametrize('given, expected', [
    ('def f(): pass', ['f']),
    ('def f(): pass\n\ndef g(): pass', ['f', 'g']),
    ('class C:\n def f(): pass', ['C.f']),
    ('class A:\n class B:\n  def f(): pass', ['A.B.f']),
    ('nothing\n1\na = 3', []),
])
def test_get_funcs(tmp_path: Path, given: str, expected):
    path = tmp_path / 'example.py'
    path.write_text(given)
    names = [f.name for f in _get_funcs(path=path)]
    assert names == expected


def test_get_module_name(tmp_path: Path):
    root = tmp_path / 'project'
    root.mkdir()
    path = root / 'example.py'
    path.touch()
    assert StubsManager._get_module_name(path=path) == 'example'

    (root / '__init__.py').touch()
    assert StubsManager._get_module_name(path=path) == 'project.example'


@pytest.mark.parametrize('given, expected', [
    ('deal.linter', 'deal.linter.__init__'),
    ('deal._state', 'deal._state'),
    ('pytest', 'pytest.__init__'),
    ('json', 'json.__init__'),
    ('typing', 'typing'),
])
def test_get_module_name_for_real_modules(tmp_path: Path, given, expected):
    module = import_module(given)
    path = Path(module.__file__)
    assert StubsManager._get_module_name(path=path) == expected


def test_stubs_manager(tmp_path: Path):
    stubs = StubsManager()
    root = tmp_path / 'project'
    root.mkdir()
    path = root / 'example.py'

    # test create
    stubs.create(path)
    assert set(stubs._modules) == {'example'}
    assert stubs._modules['example']._content == {}

    # test get
    assert stubs.get('example') is stubs._modules['example']
    expected = {'raises': ['AssertionError', 'TypeError']}
    assert stubs.get('typing')._content['get_type_hints'] == expected

    # test do not re-create already cached stub
    old_stub = stubs.get('example')
    old_stub.dump()
    new_stub = stubs.create(path)
    assert new_stub is old_stub
    assert stubs.get('example') is old_stub

    # read already dumped stub instead of creating
    old_stub.add(func='fname', contract=Category.RAISES, value='TypeError')
    old_stub.dump()
    stubs = StubsManager()
    new_stub = stubs.create(path)
    assert new_stub is not old_stub
    assert new_stub._content == {'fname': {'raises': ['TypeError']}}
