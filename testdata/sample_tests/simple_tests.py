import pytest


@pytest.fixture()
def some_fixture():
    return "fixture"


def test_simple_assertion():
    assert 0 != 1


@pytest.mark.parametrize("a,b,sum", [(0, 0, 0), (1, 2, 3)])
def test_with_params(a: int, b: int, sum: int):
    assert a + b == sum

@pytest.mark.skip()
def test_skipped_test():
    assert 0 != 1

def test_failing_test():
    assert 0 == 1

@pytest.mark.xfail()
def test_xfailing():
    assert 0 == 1

@pytest.mark.xfail()
def test_xpassing():
    assert 0 != 1
