from __future__ import annotations

import ast
import logging
import math
import operator
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from shared.protocol.envelope import TaskResult, TaskStatus

logger = logging.getLogger(__name__)

_ALLOWED = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
}
_ALLOWED_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "log": math.log}


def _eval_expr(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_eval_expr(node.left), _eval_expr(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_eval_expr(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = _ALLOWED_FUNCS.get(node.func.id)
        if fn is None or len(node.args) != 1:
            raise ValueError("unsupported call")
        return fn(_eval_expr(node.args[0]))
    raise ValueError("unsupported expression")


def _run_python_snippet(code: str, timeout: float) -> tuple[bool, str | None, str | None]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(
            "import math\n"
            "result = None\n"
            + code
            + "\nimport json\nprint(json.dumps({'result': result}))\n"
        )
        tmp = Path(f.name)
    try:
        p = subprocess.run(
            [sys.executable, str(tmp)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tempfile.gettempdir(),
        )
        ok = p.returncode == 0
        return ok, p.stdout.strip() or None, (p.stderr or "").strip() or None
    finally:
        tmp.unlink(missing_ok=True)


async def process_sandbox(env) -> TaskResult:
    payload = env.payload or {}
    mode = (payload.get("mode") or "math").lower()
    timeout = float(os.environ.get("SANDBOX_PYTHON_TIMEOUT", "5"))

    if mode == "python" and os.environ.get("SANDBOX_ALLOW_PYTHON", "0") == "1":
        code = payload.get("code") or payload.get("expression") or "result = 1+1"
        ok, out, err = _run_python_snippet(code, timeout)
        return TaskResult(
            job_id=env.job_id,
            service=env.service,
            status=TaskStatus.completed,
            asset_id=env.asset_id,
            data={"ok": ok, "mode": "python", "stdout": out, "stderr": err},
        )

    expr = payload.get("expression") or "1+1"
    try:
        tree = ast.parse(expr, mode="eval")
        value = _eval_expr(tree.body)
        ok = True
        err = None
    except Exception as exc:
        value = None
        ok = False
        err = str(exc)
    return TaskResult(
        job_id=env.job_id,
        service=env.service,
        status=TaskStatus.completed,
        asset_id=env.asset_id,
        data={"ok": ok, "mode": "math", "value": value, "error": err},
    )
