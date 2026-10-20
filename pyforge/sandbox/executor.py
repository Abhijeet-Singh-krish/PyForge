"""Hardened Disposable Sandbox Execution Engine & Error Explainer (Sections 14-20, 29)."""
import ast
import json
import os
import re
import resource
import signal
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Tuple

ALLOWED_MODULES = {
    "math", "json", "re", "random", "datetime", "collections",
    "itertools", "functools", "typing", "dataclasses", " decimal", "fractions"
}

FORBIDDEN_BUILTINS = {
    "eval", "exec", "compile", "open", "__import__", "breakpoint",
    "getattr", "setattr", "delattr", "globals", "locals", "vars",
    "exit", "quit", "help", "memoryview"
}

FORBIDDEN_DUNDERS = {
    "__subclasses__", "__bases__", "__mro__", "__globals__",
    "__code__", "__builtins__", "__loader__", "__spec__", "__dict__"
}

ERROR_LESSON_MAP = {
    "SyntaxError": ("l0-1", "What Is a Computer & How Does Code Work?"),
    "IndentationError": ("l1-5", "Conditions — Making Decisions with if, elif, and else"),
    "NameError": ("l1-2", "Variables — Storing & Naming Information"),
    "TypeError": ("l1-3", "Numbers, Booleans, Operators & Type Conversion"),
    "ValueError": ("l3-1", "Exceptions, Defensive Coding & File/JSON Handling"),
    "ZeroDivisionError": ("l3-1", "Exceptions, Defensive Coding & File/JSON Handling"),
    "IndexError": ("l2-1", "Lists & Slicing — Ordered Collections of Data"),
    "KeyError": ("l2-2", "Dictionaries, Tuples & Sets — Fast Key-Value Lookup"),
    "AttributeError": ("l4-1", "Object-Oriented Programming — Classes, __init__, self & Dunder Methods"),
    "PermissionError": ("l6-security", "Defensive Security — Input Sanitization, Password Policy & Cryptography Basics"),
    "MemoryError": ("l4-2", "CPython Internals, Memory Management, GIL & Asyncio"),
    "TimeoutError": ("l1-6", "Loops — Repeating Actions with for, while & range()"),
}

def explain_python_error(error_type: str, raw_stderr: str) -> Dict[str, str]:
    lesson_id, lesson_title = ERROR_LESSON_MAP.get(error_type, ("l1-7", "Basic Debugging — Reading Error Messages Like a Pro"))
    explanations = {
        "SyntaxError": (
            "Python could not understand the structure of your code.",
            "A quotation mark, parenthesis, or colon ':' at the end of an if/for/def line is missing or mismatched.",
            "Check the line number shown in the error and make sure all quotes and parentheses close properly."
        ),
        "IndentationError": (
            "Your code indentation (spaces at the start of a line) did not match what Python expected.",
            "Every line inside an if, else, for, while, def, or class block must be indented by 4 spaces.",
            "Add 4 spaces at the beginning of the line right after the colon ':'."
        ),
        "NameError": (
            "You used a variable or function name that Python does not recognize yet.",
            "The variable might be misspelled, used before it was assigned, or text was written without quotation marks.",
            "Check your variable spelling or wrap literal text inside double quotes."
        ),
        "TypeError": (
            "You tried to combine values that Python cannot combine in that way.",
            "One value is text (str) and the other is a number (int/float), or you indexed a list with a string.",
            "Convert text numbers using int() or float() before doing math, or use str() when joining text."
        ),
        "KeyError": (
            "You tried to look up a key in a dictionary that does not exist.",
            "Direct bracket lookup d['key'] raises KeyError if 'key' is missing.",
            "Check the key spelling or use d.get('key', default_value) for safe lookups."
        ),
        "IndexError": (
            "You tried to access a list index that is outside the valid range of the list.",
            "Python lists are 0-indexed: a list of 3 items only has indices 0, 1, and 2.",
            "Check len(your_list) and use indices between 0 and len(your_list) - 1 (or -1 for the last item)."
        ),
        "ValueError": (
            "A function received an argument of the right type, but with an invalid value.",
            "For example, int('abc') fails because 'abc' cannot be parsed as a base-10 integer.",
            "Validate input strings before converting, or catch invalid inputs using try / except ValueError."
        ),
        "ZeroDivisionError": (
            "Your program attempted to divide a number by zero.",
            "Division or modulo by 0 is mathematically undefined.",
            "Check if the denominator is 0 before dividing, or handle ZeroDivisionError in a try/except block."
        ),
        "PermissionError": (
            "Your code attempted a restricted system, file, network, or process operation.",
            "For security, the execution sandbox blocks filesystem traversal, network sockets, and OS subprocesses.",
            "Use standard in-memory data structures and approved Python standard library modules."
        ),
        "MemoryError": (
            "Your program exceeded the sandbox memory limit.",
            "Allocating giant lists, strings, or unbounded recursion exhausted the memory quota.",
            "Use generators (yield) or bounded ranges instead of allocating millions of items in RAM."
        ),
        "TimeoutError": (
            "Your program took too long to finish and was stopped by the sandbox timeout guard.",
            "A while loop condition never became False, or an algorithm had excessive nested loops.",
            "Ensure your loop variable updates on every iteration so the termination condition is reached."
        ),
    }
    what, why, try_this = explanations.get(
        error_type,
        (
            f"Your program stopped with {error_type}.",
            "An unexpected runtime exception occurred while executing your code.",
            "Inspect the line number in the traceback and test smaller expressions step by step."
        ),
    )
    return {
        "error_type": error_type,
        "what_happened": what,
        "why": why,
        "try_this": try_this,
        "relevant_lesson_id": lesson_id,
        "relevant_lesson_title": lesson_title,
    }

def inspect_code_safety(source_code: str) -> Tuple[bool, str]:
    """Static AST security analyzer (Section 15 & 16).
    Blocks dangerous imports, builtins, dunder escapes, and huge literal bombs before process spawn."""
    if len(source_code) > 32768:
        return False, "Source code exceeds maximum allowed length (32 KB)."

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        # Let Python report standard SyntaxError with exact line info during execution
        return True, "OK"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_mod = alias.name.split(".")[0]
                if root_mod not in ALLOWED_MODULES:
                    return False, f"PermissionError: Import of module '{root_mod}' is blocked by sandbox security policy."
        elif isinstance(node, ast.ImportFrom):
            root_mod = (node.module or "").split(".")[0]
            if root_mod not in ALLOWED_MODULES:
                return False, f"PermissionError: Import from module '{root_mod}' is blocked by sandbox security policy."
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_BUILTINS:
                return False, f"PermissionError: Built-in '{node.func.id}()' is blocked by sandbox security policy."
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_DUNDERS:
                return False, f"PermissionError: Access to internal attribute '{node.attr}' is blocked by sandbox policy."
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_DUNDERS:
                return False, f"PermissionError: Access to '{node.id}' is blocked by sandbox policy."
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            # Guard against huge integer power bombs like 999999 ** 999999
            if isinstance(node.right, ast.Constant) and isinstance(node.right.value, (int, float)) and node.right.value > 10000:
                return False, "MemoryError: Exponent exceeds safe sandbox computation bounds."
            if isinstance(node.op, ast.Pow) and isinstance(node.right, ast.BinOp):
                return False, "MemoryError: Chained exponentiation exceeds safe sandbox bounds."

    return True, "OK"

SANDBOX_WRAPPER_TEMPLATE = r"""
import builtins
import sys

ALLOWED_IMPORTS = {"math", "json", "re", "random", "datetime", "collections", "itertools", "functools", "typing", "dataclasses", "decimal", "fractions", "_strptime", "time"}
_orig_import = builtins.__import__

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".")[0]
    if root not in ALLOWED_IMPORTS:
        raise PermissionError(f"Import of '{name}' is blocked by PyForge Sandbox Policy")
    return _orig_import(name, globals, locals, fromlist, level)

def _blocked_op(*args, **kwargs):
    raise PermissionError("Operation blocked by PyForge Sandbox Security Policy")

builtins.__import__ = _safe_import
builtins.open = _blocked_op
builtins.eval = _blocked_op
builtins.exec = _blocked_op
builtins.compile = _blocked_op
builtins.breakpoint = _blocked_op

# Execute learner script
__name__ = "__main__"
with _orig_import("builtins").__dict__.get("open", _blocked_op) if False else open_user_code:
    pass
"""

def _apply_child_rlimits(memory_mb: int) -> None:
    # 1. CPU time limit (seconds)
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    # 2. Address space / virtual memory limit
    mem_bytes = max(32, memory_mb) * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except Exception:
        pass
    # 3. File size write limit (8 KB max to prevent disk exhaustion)
    resource.setrlimit(resource.RLIMIT_FSIZE, (8192, 8192))
    # 4. Open file descriptors cap
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
    except Exception:
        pass

def execute_in_disposable_sandbox(
    source_code: str,
    stdin_text: str = "",
    timeout_sec: float = 2.0,
    memory_mb: int = 64,
    max_output_bytes: int = 8192,
) -> Dict[str, Any]:
    """Executes untrusted Python code inside an isolated, ephemeral workspace with strict resource limits."""
    start_t = time.perf_counter()
    safe, reason = inspect_code_safety(source_code)
    if not safe:
        err_type = "MemoryError" if reason.startswith("MemoryError") else "PermissionError"
        return {
            "status": "failed",
            "stdout": "",
            "stderr": reason + "\n",
            "exit_code": 1,
            "duration_ms": round((time.perf_counter() - start_t) * 1000, 2),
            "error_explanation": explain_python_error(err_type, reason),
        }

    with tempfile.TemporaryDirectory(prefix="pyforge_sbx_") as tmpdir:
        os.chmod(tmpdir, 0o700)
        user_code_path = os.path.join(tmpdir, "user_main.py")
        runner_path = os.path.join(tmpdir, "_runner.py")

        with open(user_code_path, "w", encoding="utf-8") as f:
            f.write(source_code)

        runner_script = f"""import builtins, sys
ALLOWED = {{"math", "json", "re", "random", "datetime", "collections", "itertools", "functools", "typing", "dataclasses", "decimal", "fractions", "_strptime", "time"}}
_real_import = builtins.__import__
_real_open = builtins.open
_real_exec = builtins.exec
with _real_open({user_code_path!r}, "r", encoding="utf-8") as _uf:
    _user_src = _uf.read()
_compiled = builtins.compile(_user_src, "main.py", "exec")

def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".")[0]
    if root not in ALLOWED:
        raise PermissionError(f"Import of '{{name}}' is blocked by sandbox policy")
    return _real_import(name, globals, locals, fromlist, level)

def _blocked(*a, **kw):
    raise PermissionError("System/filesystem operation blocked by sandbox policy")

builtins.__import__ = _guarded_import
builtins.open = _blocked
builtins.eval = _blocked
builtins.exec = _blocked
builtins.compile = _blocked
builtins.breakpoint = _blocked

_g = {{"__name__": "__main__", "__builtins__": builtins}}
_real_exec(_compiled, _g, _g)
"""
        with open(runner_path, "w", encoding="utf-8") as f:
            f.write(runner_script)

        # Completely scrubbed environment: no secrets, no host env leakage
        clean_env = {
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
        }

        proc = subprocess.Popen(
            ["python3", "-I", "-B", runner_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=tmpdir,
            env=clean_env,
            start_new_session=True,
            preexec_fn=lambda: _apply_child_rlimits(memory_mb),
        )

        timed_out = False
        try:
            stdout_bytes, stderr_bytes = proc.communicate(
                input=(stdin_text or "").encode("utf-8"),
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
            stdout_bytes, stderr_bytes = proc.communicate()

        duration_ms = round((time.perf_counter() - start_t) * 1000, 2)

        # Enforce strict output size limit (Section 15 & 16)
        truncated_out = False
        if len(stdout_bytes) > max_output_bytes:
            stdout_bytes = stdout_bytes[:max_output_bytes]
            truncated_out = True
        if len(stderr_bytes) > max_output_bytes:
            stderr_bytes = stderr_bytes[:max_output_bytes]

        stdout_str = stdout_bytes.decode("utf-8", errors="replace")
        if truncated_out:
            stdout_str += "\n[Output truncated: exceeded sandbox limit]"
        stderr_str = stderr_bytes.decode("utf-8", errors="replace")

        if timed_out:
            return {
                "status": "timed_out",
                "stdout": stdout_str,
                "stderr": "TimeoutError: Execution exceeded time limit (" + str(timeout_sec) + "s).\n",
                "exit_code": 124,
                "duration_ms": duration_ms,
                "error_explanation": explain_python_error("TimeoutError", "Execution timed out"),
            }

        exit_code = proc.returncode if proc.returncode is not None else 1
        if exit_code != 0:
            # Detect MemoryError or RLIMIT kill signal (-9 / -6)
            err_type = "RuntimeError"
            if exit_code < 0 or "MemoryError" in stderr_str:
                err_type = "MemoryError"
                if not stderr_str:
                    stderr_str = "MemoryError: Process exceeded sandbox memory/CPU resource limits.\n"
            else:
                m = re.findall(r"([A-Za-z]+Error):", stderr_str)
                if m:
                    err_type = m[-1]
            return {
                "status": "failed",
                "stdout": stdout_str,
                "stderr": stderr_str,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "error_explanation": explain_python_error(err_type, stderr_str),
            }

        return {
            "status": "completed",
            "stdout": stdout_str,
            "stderr": stderr_str,
            "exit_code": 0,
            "duration_ms": duration_ms,
            "error_explanation": None,
        }

def evaluate_single_test(source_code: str, test_case: Dict[str, Any], default_stdin: str = "Sagar") -> Dict[str, Any]:
    """Runs a single visible or hidden test inside the disposable sandbox without leaking hidden inputs."""
    t_type = test_case.get("type") or test_case.get("test_type")
    expected = test_case.get("expected")
    stdin_to_use = test_case.get("stdin") if test_case.get("stdin") is not None else (test_case.get("stdin_text") or default_stdin)

    harnessed_code = source_code
    if t_type == "var_equals":
        var_name = test_case.get("var") or test_case.get("var_name")
        harnessed_code = source_code + f"\nimport json as __json\nprint('__PYFORGE_VAR__:' + __json.dumps({var_name}))\n"
    elif t_type == "fn_call":
        fn_name = test_case.get("fn") or test_case.get("fn_name")
        args = test_case.get("args")
        if args is None and test_case.get("args_json"):
            args = json.loads(test_case["args_json"])
        args_repr = ", ".join(repr(a) for a in (args or []))
        harnessed_code = source_code + f"\nimport json as __json\nprint('__PYFORGE_RET__:' + __json.dumps({fn_name}({args_repr})))\n"

    res = execute_in_disposable_sandbox(harnessed_code, stdin_text=str(stdin_to_use))
    if res["status"] != "completed":
        return {
            "passed": False,
            "status": res["status"],
            "category": test_case.get("category", "runtime_error"),
            "conceptual_hint": test_case.get("conceptual_hint") or (res.get("error_explanation") or {}).get("try_this", ""),
            "stdout": res["stdout"],
            "stderr": res["stderr"],
            "error_explanation": res.get("error_explanation"),
        }

    stdout = res["stdout"]
    passed = False
    if t_type == "stdout_contains":
        passed = str(expected) in stdout
    elif t_type == "stdout_lines":
        lines = [ln.strip() for ln in stdout.splitlines() if ln.strip() and not ln.startswith("__PYFORGE_")]
        passed = lines == list(expected)
    elif t_type == "stdin_stdout":
        passed = str(expected) in stdout
    elif t_type == "var_equals":
        marker = "__PYFORGE_VAR__:"
        for ln in stdout.splitlines():
            if ln.startswith(marker):
                actual = json.loads(ln[len(marker):])
                passed = actual == expected
    elif t_type == "fn_call":
        marker = "__PYFORGE_RET__:"
        for ln in stdout.splitlines():
            if ln.startswith(marker):
                actual = json.loads(ln[len(marker):])
                passed = actual == expected

    return {
        "passed": passed,
        "status": "passed" if passed else "failed",
        "category": test_case.get("category", "core_correctness"),
        "conceptual_hint": test_case.get("conceptual_hint", "Verify your logic on edge-case inputs."),
        "stdout": "\n".join(ln for ln in stdout.splitlines() if not ln.startswith("__PYFORGE_")),
        "stderr": res["stderr"],
        "error_explanation": None,
    }
