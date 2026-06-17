import pytest

@pytest.fixture(scope="module")
def preWork():
    print("I setup module instance")
    return "pass" # this return value get stored in the perwork variable in the test function

@pytest.fixture(scope="function")
def secondWork():
    print("i setup function instance")
    yield # pause here and goes to test funciton
    print("tear down validation") # after finishing test function, it came back here

def test_initialCheck(preWork, secondWork):
    print("This is first test")
    assert preWork == "pass" # assert use to compare the return statement, the return from the prework is being stored in preWork variable

def test_secondCheck(preWork, secondWork):
    print("This is second test")
