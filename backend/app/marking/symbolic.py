"""Conservative symbolic comparison for short mathematical expressions."""
import ast
import ctypes
import ctypes.wintypes
import multiprocessing
import os
import re
import signal
import time

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
_NUMERIC_TOLERANCE = 1e-5
_CHECK_TIMEOUT_SECONDS = 2
_MAX_WALL_SECONDS = 10


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
    symbols = {
        node.id: sympy.Symbol(node.id, real=True)
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id not in _SAFE_FUNCTIONS | {"pi", "E"}
    }
    return parse_expr(
        _safe_source(tree.body), transformations=_TRANSFORMATIONS, local_dict=symbols
    )


def _is_interval_source(source):
    source = source.strip()
    if len(source) < 3 or source[0] not in "([" or source[-1] not in ")]":
        return False
    depth = 0
    for index, char in enumerate(source[1:-1], 1):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            return True
    return False


def _parse_answer(source):
    stripped = source.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        body = stripped[1:-1].strip()
        if not body:
            return sympy.EmptySet
        return sympy.FiniteSet(*(_parse_expression(part) for part in _split_top_level(body)))
    if _is_interval_source(stripped):
        inner = stripped[1:-1]
        parts = _split_top_level(inner)
        if len(parts) != 2:
            raise ValueError("interval requires two endpoints")
        start, end = (_parse_expression(part) for part in parts)
        return sympy.Interval(start, end, left_open=stripped[0] == "(", right_open=stripped[-1] == ")")
    return _parse_expression(stripped)


def _split_top_level(source):
    parts = []
    start = 0
    depth = 0
    for index, char in enumerate(source):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(source[start:index].strip())
            start = index + 1
    parts.append(source[start:].strip())
    if any(not part for part in parts):
        raise ValueError("empty collection element")
    return parts


def _check_answer_unbounded(problem, student_answer, reference_answer):
    """Return a conservative three-state comparison for expression answers.

    Tolerance is limited to expressions that contain only numeric values. When
    SymPy cannot establish equality or inequality, the result stays uncertain.
    """
    if not isinstance(student_answer, str) or not student_answer.strip():
        return {"verdict": "uncertain", "reason": "学生最终答案为空或不可用"}
    if not isinstance(reference_answer, str) or not reference_answer.strip():
        return {"verdict": "uncertain", "reason": "缺少已核实的参考答案"}
    try:
        student = _parse_answer(student_answer)
    except Exception:
        return {"verdict": "uncertain", "reason": "学生答案超出当前支持的表达式范围"}
    try:
        reference = _parse_answer(reference_answer)
    except Exception:
        return {"verdict": "uncertain", "reason": "参考答案超出当前支持的表达式范围"}
    try:
        if isinstance(student, sympy.Set) or isinstance(reference, sympy.Set):
            if not isinstance(student, sympy.Set) or not isinstance(reference, sympy.Set):
                return {"verdict": "wrong", "reason": "集合或区间不能与代数表达式混比"}
            same_members = (
                sympy.simplify(student.symmetric_difference(reference)) == sympy.EmptySet
            )
            if student == reference or same_members:
                return {"verdict": "correct", "reason": "集合或区间的元素与边界相同"}
            return {"verdict": "wrong", "reason": "集合或区间的元素或边界不同"}
        difference = sympy.simplify(student - reference)
        if difference == 0 or difference.is_zero is True:
            return {"verdict": "correct", "reason": "两式符号化简后相等"}
        if student.is_number and reference.is_number:
            try:
                if abs(float(student.evalf()) - float(reference.evalf())) <= _NUMERIC_TOLERANCE:
                    return {"verdict": "correct", "reason": "纯数值差异在允许公差内"}
            except (TypeError, ValueError, OverflowError):
                pass
        polynomial = difference.as_poly()
        if difference.is_zero is False or (polynomial is not None and not polynomial.is_zero):
            return {"verdict": "wrong", "reason": "两式可证明不等价"}
    except Exception:
        pass
    return {"verdict": "uncertain", "reason": "符号系统无法可靠证明两式相等或不等"}


def _check_worker(connection, args):
    try:
        connection.send(_check_answer_unbounded(*args))
    except BaseException:
        connection.send({"verdict": "uncertain", "reason": "符号计算未能可靠完成"})
    finally:
        connection.close()


def _process_cpu_seconds(process):
    """Read child user plus kernel CPU time without counting idle waits."""
    if os.name == "nt":
        class FileTime(ctypes.Structure):
            _fields_ = (("low", ctypes.wintypes.DWORD), ("high", ctypes.wintypes.DWORD))

        creation, exit_time, kernel, user = (FileTime() for _ in range(4))
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_process_times = kernel32.GetProcessTimes
        get_process_times.argtypes = (
            ctypes.wintypes.HANDLE,
            ctypes.POINTER(FileTime), ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime), ctypes.POINTER(FileTime),
        )
        get_process_times.restype = ctypes.wintypes.BOOL
        process_handle = getattr(process, "_handle", None)
        if process_handle is None:
            process_handle = process._popen._handle
        if not get_process_times(
            ctypes.wintypes.HANDLE(process_handle),
            ctypes.byref(creation), ctypes.byref(exit_time),
            ctypes.byref(kernel), ctypes.byref(user),
        ):
            raise ctypes.WinError(ctypes.get_last_error())

        def seconds(file_time):
            ticks = (file_time.high << 32) | file_time.low
            return ticks / 10_000_000

        return seconds(kernel) + seconds(user)

    stat_path = f"/proc/{process.pid}/stat"
    if os.path.exists(stat_path):
        with open(stat_path, encoding="ascii") as stat_file:
            fields = stat_file.read().rsplit(")", 1)[1].split()
        ticks = int(fields[11]) + int(fields[12])
        return ticks / os.sysconf("SC_CLK_TCK")
    raise OSError("child CPU accounting is unavailable")


def _wait_for_worker(process, cpu_clock=_process_cpu_seconds):
    """Join a worker while enforcing CPU and secondary wall clock limits."""
    started = time.monotonic()
    while process.is_alive():
        try:
            cpu_seconds = cpu_clock(process)
        except (OSError, ValueError, IndexError):
            cpu_seconds = None
        wall_seconds = time.monotonic() - started
        if cpu_seconds is not None and cpu_seconds >= _CHECK_TIMEOUT_SECONDS:
            process.terminate()
            process.join(1)
            return False
        wall_limit = _MAX_WALL_SECONDS if cpu_seconds is not None else _CHECK_TIMEOUT_SECONDS
        if wall_seconds >= wall_limit:
            process.terminate()
            process.join(1)
            return False
        process.join(min(0.05, _MAX_WALL_SECONDS - wall_seconds))
    return process.exitcode == 0


def check_answer(problem, student_answer, reference_answer):
    """Compare supported answers under a hard per-question time bound."""
    # SIGPROF counts CPU time, preserving the warm SymPy process on Unix.
    if hasattr(signal, "SIGPROF") and multiprocessing.current_process().name == "MainProcess":
        previous_handler = signal.getsignal(signal.SIGPROF)
        previous_delay, previous_interval = signal.getitimer(signal.ITIMER_PROF)
        cpu_started = time.process_time()

        def timeout_handler(*_):
            raise TimeoutError

        signal.signal(signal.SIGPROF, timeout_handler)
        signal.setitimer(signal.ITIMER_PROF, _CHECK_TIMEOUT_SECONDS)
        try:
            return _check_answer_unbounded(problem, student_answer, reference_answer)
        except TimeoutError:
            return {"verdict": "uncertain", "reason": "符号计算超过单题资源限制"}
        finally:
            signal.setitimer(signal.ITIMER_PROF, 0)
            signal.signal(signal.SIGPROF, previous_handler)
            if previous_delay:
                elapsed = time.process_time() - cpu_started
                signal.setitimer(
                    signal.ITIMER_PROF, max(0, previous_delay - elapsed), previous_interval
                )
    parent, child = multiprocessing.Pipe(duplex=False)
    process = multiprocessing.Process(
        target=_check_worker, args=(child, (problem, student_answer, reference_answer))
    )
    process.start()
    child.close()
    completed = _wait_for_worker(process)
    if not completed:
        parent.close()
        return {"verdict": "uncertain", "reason": "符号计算超过单题资源限制"}
    try:
        return parent.recv() if parent.poll() else {
            "verdict": "uncertain", "reason": "符号计算未能可靠完成"
        }
    finally:
        parent.close()
