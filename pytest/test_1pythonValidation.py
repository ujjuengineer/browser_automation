import pytest
"""
scope = "module" : print only once 
scope = "function" : print before every test funciton 
scope = "session" : runs once per session, like only runs once across all execution
"""
@pytest.fixture(scope="module")
def preWork():
    print("I setup browser instance, (module fixture)")

def test_initialCheck(preWork):
    print("this is first test")

def test_secondTest(preWork):
    print("this is second test")