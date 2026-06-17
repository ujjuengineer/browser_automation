# you can put the pytest_fixtures in the global file as well
# pytest first check for the pytest fixture in the current file and if it doesn't found it in current file then it search for it in the global file
# the global file name should be always "conftest.py"


def test_initialCheck(preWork):
    print("this is test from the second file")
