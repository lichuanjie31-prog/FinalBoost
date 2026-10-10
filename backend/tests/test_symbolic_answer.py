"""Service boundary for B's deterministic symbolic answer checker."""
import pytest

from app.main import create_app
from app.marking.router import SymbolicAnswerIn, check_answer
from app.marking.symbolic import check_answer as compare_expressions
from app.service_auth import service_token_guard
from fastapi import HTTPException


def test_symbolic_answer_check_route_is_registered():
    app = create_app()
    operation = app.openapi()["paths"]["/api/v1/marking/check-answer"]["post"]

    assert any(parameter["name"] == "X-Service-Token" for parameter in operation["parameters"])


def test_equivalent_latex_expression_is_correct():
    result = compare_expressions("化简", r"\frac{1}{2}", "0.5")

    assert result["verdict"] == "correct"


def test_provably_different_polynomial_is_wrong():
    result = compare_expressions("比较", "x**2", "x")

    assert result["verdict"] == "wrong"


def test_sampling_coincidence_does_not_mark_nonidentical_expressions_correct():
    result = compare_expressions("比较", "sqrt(x**2)", "x")

    assert result["verdict"] == "wrong"


def test_unparseable_text_remains_uncertain():
    result = compare_expressions("解方程", "无解", "x=1")

    assert result["verdict"] == "uncertain"


def test_code_execution_syntax_is_rejected_before_sympy_parse(capsys):
    result = compare_expressions(
        "比较",
        "__import__('os').system('echo SHOULD_NOT_RUN')",
        "1",
    )

    assert result["verdict"] == "uncertain"
    assert "SHOULD_NOT_RUN" not in capsys.readouterr().out


def test_check_answer_route_wraps_the_checker_result():
    response = check_answer(
        SymbolicAnswerIn(problem="化简", studentAnswer="2x", referenceAnswer="x+x"),
        _=None,
    )

    assert response["data"]["verdict"] == "correct"


def test_service_token_is_required(monkeypatch):
    monkeypatch.delenv("SERVICE_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        service_token_guard(x_service_token="")

    assert exc.value.status_code == 503


def test_invalid_service_token_is_rejected(monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "expected-token")
    with pytest.raises(HTTPException) as exc:
        service_token_guard(x_service_token="wrong-token")

    assert exc.value.status_code == 401
