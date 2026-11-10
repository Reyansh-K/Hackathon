import pytest

from exhibit_a.synth import build_demo_case


@pytest.fixture(scope="session")
def demo_case(tmp_path_factory):
    """The synthetic 'Missing Invoice' case, sealed and analyzed once per test run."""
    return build_demo_case(tmp_path_factory.mktemp("cases"))


@pytest.fixture
def fresh_demo_case(tmp_path):
    """A private copy for tests that modify the case."""
    return build_demo_case(tmp_path)
