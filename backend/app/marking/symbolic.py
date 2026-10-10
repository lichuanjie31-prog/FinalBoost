"""Conservative symbolic comparison for short mathematical expressions."""
import ast
import re

import sympy
from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)


_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)
_SAFE_FUNCTIONS = {"sqrt", "sin", "cos", "tan", "log", "ln", "abs"}
_SAFE_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.UAdd, ast.USub, ast.Call,
)


def _expand_braced_command(source, command, replacement):
    """Expand one LaTeX command whose argument is a balanced brace group."""
    while command in source:
        index = source.find(command)
        start = index + len(command)
        if start >= len(source) or source[start] != "{":
            raise ValueError("invalid LaTeX group")
        depth = 0
        end = None
        for cursor in range(start, len(source)):
            if source[cursor] == "{":
                depth += 1
            elif source[cursor] == "}":
                depth -= 1
                if depth == 0:
                    end = cursor
                    break
        if end is None:
            raise ValueError("unclosed LaTeX group")
        inner = source[start + 1:end]
        source = source[:index] + replacement.format(inner=_normalize_latex(inner)) + source[end + 1:]
    return source


def _normalize_latex(source):
    source = source.strip().strip("$")
    source = source.replace(r"\dfrac", r"\frac").replace(r"\tfrac", r"\frac")
    # Fractions need two balanced groups, so expand them separately.
    while r"\frac" in source:
        index = source.find(r"\frac")
        cursor = index + len(r"\frac")
        groups = []
        for _ in range(2):
            if cursor >= len(source) or source[cursor] != "{":
                raise ValueError("invalid fraction")
            depth = 0
            end = None
            for position in range(cursor, len(source)):
                if source[position] == "{":
                    depth += 1
                elif source[position] == "}":
                    depth -= 1
                    if depth == 0:
                        end = position
                        break
            if end is None:
                raise ValueError("unclosed fraction")
            groups.append(source[cursor + 1:end])
            cursor = end + 1
        numerator, denominator = (_normalize_latex(group) for group in groups)
        source = source[:index] + f"(({numerator})/({denominator}))" + source[cursor:]
    source = _expand_braced_command(source, r"\sqrt", "sqrt({inner})")
    replacements = {
        r"\cdot": "*", r"\times": "*", r"\div": "/", r"\pi": "pi",
        r"\theta": "theta", r"\alpha": "alpha", r"\beta": "beta",
        r"\left": "", r"\right": "", r"\,": " ", r"\;": " ",
    }
    for old, new in replacements.items():
        source = source.replace(old, new)
    source = re.sub(r"\^\{([^{}]+)\}", r"**(\1)", source)
    source = re.sub(r"\^([0-9A-Za-z]+)", r"**\1", source)
    source = re.sub(r"(?<=\d)(?=[A-Za-z])", "*", source)
    return source.strip()


class _SafeNormalizer(ast.NodeTransformer):
    def visit_Call(self, node):
        node = self.generic_visit(node)
        if node.keywords or len(node.args) != 1:
            raise ValueError("unsupported function call")
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCTIONS:
            return node
        if isinstance(node.func, (ast.Name, ast.Constant)):
            if isinstance(node.func, ast.Name) or isinstance(node.func.value, (int, float)):
                return ast.BinOp(left=node.func, op=ast.Mult(), right=node.args[0])
        raise ValueError("unsupported function call")


def _safe_source(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("unsupported literal")
        if len(str(node.value)) > 32:
            raise ValueError("numeric literal too large")
        return repr(node.value)
    if isinstance(node, ast.UnaryOp):
        operator = "+" if isinstance(node.op, ast.UAdd) else "-"
        return f"({operator}{_safe_source(node.operand)})"
    if isinstance(node, ast.BinOp):
        operators = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "**"}
        operator = operators[type(node.op)]
        if isinstance(node.op, ast.Pow):
            if not isinstance(node.right, ast.Constant) or abs(node.right.value) > 50:
                raise ValueError("power is outside supported range")
            if any(isinstance(part, ast.BinOp) and isinstance(part.op, ast.Pow)
                   for part in ast.walk(node.right)):
                raise ValueError("nested powers are unsupported")
        return f"({_safe_source(node.left)}{operator}{_safe_source(node.right)})"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return f"{node.func.id}({','.join(_safe_source(arg) for arg in node.args)})"
    raise ValueError("unsupported expression syntax")


def _parse_expression(source):
    if not source or len(source) > 512 or not source.isascii():
        raise ValueError("expression is empty, too long, or contains unsupported text")
    normalized = _normalize_latex(source)
    if "\\" in normalized:
        raise ValueError("unsupported LaTeX command")
    tree = ast.parse(normalized, mode="eval")
    tree = _SafeNormalizer().visit(tree)
    ast.fix_missing_locations(tree)
    nodes = list(ast.walk(tree))
    if len(nodes) > 128 or any(not isinstance(node, _SAFE_NODES) for node in nodes):
        raise ValueError("expression syntax is outside the supported subset")
    for node in nodes:
        if isinstance(node, ast.Name):
            if not node.id.isidentifier() or "__" in node.id:
                raise ValueError("unsupported symbol")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCTIONS:
                raise ValueError("unsupported function")
    return parse_expr(_safe_source(tree.body), transformations=_TRANSFORMATIONS)


def check_answer(problem, student_answer, reference_answer):
    """Return a conservative three-state comparison for expression answers.

    Numeric sampling is deliberately not used as proof of equivalence. When
    SymPy cannot establish equality or inequality, the result stays uncertain.
    """
    if not isinstance(student_answer, str) or not student_answer.strip():
        return {"verdict": "uncertain", "reason": "学生最终答案为空或不可用"}
    if not isinstance(reference_answer, str) or not reference_answer.strip():
        return {"verdict": "uncertain", "reason": "缺少已核实的参考答案"}
    try:
        student = _parse_expression(student_answer)
    except Exception:
        return {"verdict": "uncertain", "reason": "学生答案超出当前支持的表达式范围"}
    try:
        reference = _parse_expression(reference_answer)
    except Exception:
        return {"verdict": "uncertain", "reason": "参考答案超出当前支持的表达式范围"}
    try:
        difference = sympy.simplify(student - reference)
        if difference == 0 or difference.is_zero is True:
            return {"verdict": "correct", "reason": "两式符号化简后相等"}
        polynomial = difference.as_poly()
        if difference.is_zero is False or (polynomial is not None and not polynomial.is_zero):
            return {"verdict": "wrong", "reason": "两式可证明不等价"}
    except Exception:
        pass
    return {"verdict": "uncertain", "reason": "符号系统无法可靠证明两式相等或不等"}
