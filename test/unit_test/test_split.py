from intern.helper import split_on_first_whitespace


def test_split_normal():
    assert split_on_first_whitespace("cmd param") == ("cmd", "param")
    assert split_on_first_whitespace("cmd    param with spaces") == ("cmd", "param with spaces")
    assert split_on_first_whitespace("cmd") == ("cmd", "")
    assert split_on_first_whitespace("cmd    ") == ("cmd", "")


def test_split_empty():
    assert split_on_first_whitespace("") == ("", "")
