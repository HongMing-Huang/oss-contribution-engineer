from calc import add, divide


def test_add():
    assert add(2, 3) == 5


def test_divide():
    assert divide(6, 3) == 2


def test_divide_by_zero_raises():
    try:
        divide(1, 0)
    except ZeroDivisionError:
        pass
    else:
        raise AssertionError("divide(1, 0) returned instead of raising ZeroDivisionError")
