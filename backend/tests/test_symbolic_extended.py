import pytest

from app.marking.symbolic import check_answer


@pytest.mark.parametrize(
    ("student", "reference", "verdict"),
    [
        ("{1, 2}", "{2, 1}", "correct"),
        ("{1, 2}", "{1, 3}", "wrong"),
        ("(1, 2)", "(1, 2)", "correct"),
        ("(1, 2)", "[1, 2]", "wrong"),
        ("[1, 2)", "(1, 2]", "wrong"),
        ("x/3", "x*0.333333", "wrong"),
    ],
)
def test_collections_intervals_and_exact_algebra(student, reference, verdict):
    assert check_answer("比较", student, reference)["verdict"] == verdict


def test_numeric_tolerance_applies_only_to_pure_numbers():
    assert check_answer("比较", "1.000001", "1")["verdict"] == "correct"
    assert check_answer("比较", "x + 1.000001", "x + 1")["verdict"] == "wrong"


def test_sqrt_square_is_not_equal_for_all_real_values():
    assert check_answer("比较", "sqrt(x**2)", "x")["verdict"] == "wrong"


def test_real_domain_assumption_does_not_assume_variable_is_nonnegative():
    assert check_answer("比较", "sqrt(x**2)", "abs(x)")["verdict"] == "correct"


def test_malformed_collection_remains_uncertain():
    assert check_answer("比较", "{1,", "{1}")["verdict"] == "uncertain"


def test_expensive_expression_is_bounded(monkeypatch):
    import os
    import time
    import pytest

    if os.name == "nt" or not hasattr(__import__("signal"), "SIGALRM"):
        pytest.skip("signal based timeout test runs on Unix")
    import app.marking.symbolic as symbolic

    def block(*_args):
        deadline = time.perf_counter() + 3
        while time.perf_counter() < deadline:
            pass

    monkeypatch.setattr(symbolic, "_check_answer_unbounded", block)
    assert symbolic.check_answer("比较", "1", "1")["verdict"] == "uncertain"


def test_equivalent_irrational_expressions_are_symbolically_equal():
    assert check_answer("比较", "sqrt(8)/2", "sqrt(2)")["verdict"] == "correct"
