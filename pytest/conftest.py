import pytest

@pytest.fixture(scope="session")
def preWork():
    print("this is session fixture")
