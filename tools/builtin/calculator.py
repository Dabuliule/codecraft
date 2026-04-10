"""内置计算器工具。"""

import ast

from pydantic import BaseModel, ConfigDict

from core.exceptions import ToolException
from tools.base import Tool


class CalculatorParams(BaseModel):
    """计算器参数。"""

    model_config = ConfigDict(extra="forbid")

    expression: str


class CalculatorTool(Tool):
    """执行四则运算与安全表达式求值。"""

    params_model = CalculatorParams

    def __init__(self):
        super().__init__(
            name="calculator",
            description="执行数学计算：支持 expression 表达式（含括号、+ - * /、× ÷）",
        )

    def _run(self, params: dict[str, object]) -> float:
        expression = str(params["expression"]).strip()
        return self._eval_expression(expression)


    def _eval_expression(self, expression: str) -> float:
        normalized = self._normalize_expression(expression)
        try:
            node = ast.parse(normalized, mode="eval")
        except SyntaxError as exc:
            raise ToolException(f"表达式语法错误: {exc}") from exc
        return float(self._eval_ast(node))

    @staticmethod
    def _normalize_expression(expression: str) -> str:
        normalized = (
            expression.replace("×", "*")
            .replace("÷", "/")
            .replace("（", "(")
            .replace("）", ")")
        )
        allowed_chars = set("0123456789+-*/(). ")
        if any(ch not in allowed_chars for ch in normalized):
            raise ToolException("表达式包含不支持的字符，仅允许数字、括号和 + - * /")
        return normalized.strip()

    def _eval_ast(self, node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return self._eval_ast(node.body)

        if isinstance(node, ast.BinOp):
            left = self._eval_ast(node.left)
            right = self._eval_ast(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ToolException("除数不能为 0")
                return left / right
            raise ToolException("表达式中包含不支持的运算符")

        if isinstance(node, ast.UnaryOp):
            value = self._eval_ast(node.operand)
            if isinstance(node.op, ast.UAdd):
                return value
            if isinstance(node.op, ast.USub):
                return -value
            raise ToolException("表达式中包含不支持的一元运算")

        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)

        raise ToolException("表达式中包含不安全或不支持的语法")

