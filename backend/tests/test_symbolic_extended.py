import pytest
import multiprocessing
import time

from app.marking.symbolic import check_answer


def _burn_cpu_for_test():
    started = time.process_time()
    while time.process_time() - started < 2.5:
        pass


@pytest.mark.parametrize(
    ("student", "reference", "verdict"),
    [
        ("{1, 2}", "{2, 1}", "correct"),
        ("{1, 2}", "{1, 3}", "wrong"),
        ("{1, 2}", "(1, 2)", "wrong"),
        ("(1, 2)", "(1, 2)", "correct"),
        ("(1, 2)", "[1, 2]", "wrong"),
        ("[1, 2)", "(1, 2]", "wrong"),
        ("x/3", "x*0.333333", "wrong"),
    ],
)
def test_collections_intervals_and_exact_algebra(student, reference, verdict):
    assert check_answer("比较", student, reference)["verdict"] == verdict


def test_numeric_tolerance_applies_only_to_pure_numbers():
    assert check_answer("比较", "0.00001", "0")["verdict"] == "correct"
    assert check_answer("比较", "0.000011", "0")["verdict"] == "wrong"
    assert check_answer("比较", "x + 1.000001", "x + 1")["verdict"] == "wrong"


def test_sqrt_square_is_not_equal_for_all_real_values():
    assert check_answer("比较", "sqrt(x**2)", "x")["verdict"] == "wrong"


def test_real_domain_assumption_does_not_assume_variable_is_nonnegative():
    assert check_answer("比较", "sqrt(x**2)", "abs(x)")["verdict"] == "correct"


def test_malformed_collection_remains_uncertain():
    assert check_answer("比较", "{1,", "{1}")["verdict"] == "uncertain"


def test_worker_is_terminated_after_two_seconds_of_cpu():
    import app.marking.symbolic as symbolic

    class FakeProcess:
        exitcode = None
        terminated = False
        joins = 0

        def is_alive(self):
            return not self.terminated and self.joins < 3

        def join(self, _timeout):
            self.joins += 1

        def terminate(self):
            self.terminated = True

    readings = iter((0.2, 1.2, 2.01))
    process = FakeProcess()

    assert symbolic._wait_for_worker(process, lambda _process: next(readings)) is False
    assert process.terminated is True


def test_real_cpu_bound_worker_is_terminated():
    import app.marking.symbolic as symbolic

    process = multiprocessing.Process(target=_burn_cpu_for_test)
    process.start()

    assert symbolic._wait_for_worker(process) is False
    assert process.is_alive() is False


def test_equivalent_irrational_expressions_are_symbolically_equal():
    assert check_answer("比较", "sqrt(8)/2", "sqrt(2)")["verdict"] == "correct"
