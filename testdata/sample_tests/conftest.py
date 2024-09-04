import pytest


@pytest.fixture(autouse=True)
def test_function(record_property, request: pytest.FixtureRequest):
    if request.node.get_closest_marker("xfail") is not None:
        record_property("xfail", True)
    assert True
