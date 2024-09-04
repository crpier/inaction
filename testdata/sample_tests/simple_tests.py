import pytest


@pytest.fixture()
def some_fixture():
    return "fixture"


def test_simple_assertion():
    assert 0 != 1


@pytest.mark.parametrize("a,b,sum", [(0, 0, 0), (1, 2, 3)])
def test_with_params(a: int, b: int, sum: int):
    assert a + b == sum

@pytest.mark.skip(reason="unconditional skip lol")
def test_skip_unconditional():
    assert 0 != 1

@pytest.mark.skipif(1 != 0, reason="conditional skip lol")
def test_skip_conditional():
    assert 0 != 1

def test_skip_dynamic():
    pytest.skip()

def test_failing_test():
    assert 0 == 1

@pytest.mark.xfail()
def test_xfailing():
    assert 0 == 1

@pytest.mark.xfail()
def test_xpassing():
    assert 0 != 1
