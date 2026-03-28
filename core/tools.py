# core/tools.py
# Safe tool implementations used by modules/toolrunner.py.
# - run_calc: evaluates a math expression without using eval() on arbitrary code
# - run_open: opens a URL in the default browser

import ast
import operator
import webbrowser

# Whitelist of safe AST node types for the calculator
_SAFE_OPS = {
    ast.Add:      operator.add,
    ast.Sub:      operator.sub,
    ast.Mult:     operator.mul,
    ast.Div:      operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod:      operator.mod,
    ast.Pow:      operator.pow,
    ast.USub:     operator.neg,
    ast.UAdd:     operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if not op_fn:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if not op_fn:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.operand))
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def run_calc(expr: str) -> str:
    """Safely evaluate a math expression and return 'expr = result'."""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
        result = _eval_node(tree.body)
        # Clean up float display: drop .0 for whole numbers, cap precision otherwise
        if isinstance(result, float):
            result = int(result) if result == int(result) else round(result, 8)
        return f"{expr.strip()} = {result}"
    except Exception as e:
        return f"[calc error: {e}]"


def run_open(url: str) -> str:
    """Open a URL in the default browser."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url} in your browser."
