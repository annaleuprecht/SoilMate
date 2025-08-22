# utils/safe_eval.py
import ast, operator as op

_ALLOWED = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.Pow: op.pow, ast.USub: op.neg, ast.UAdd: op.pos, ast.Mod: op.mod
}

def eval_expr(expr: str, names: dict):
    """Evaluate a math expression with names from `names` safely."""
    def _eval(node):
        if isinstance(node, ast.Num):         # 3.14
            return node.n
        if isinstance(node, ast.Constant):    # py3.11+
            return node.value
        if isinstance(node, ast.Name):        # variables
            return float(names.get(node.id, 0.0))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
            return _ALLOWED[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
            return _ALLOWED[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.Expr):
            return _eval(node.value)
        raise ValueError("Unsupported expression element")
    tree = ast.parse(expr, mode='eval')
    return _eval(tree.body)
