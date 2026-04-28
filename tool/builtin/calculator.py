"""内置计算器工具。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tool.base import BaseTool, ToolException


class CalculatorArgs(BaseModel):
    """计算器输入参数。"""

    model_config = ConfigDict(extra="forbid")

    expression: str = Field(..., description="算术表达式，如 '(1 + 2) * 3 / 4'")


class CalculatorTool(BaseTool):
    """执行基础算术表达式（支持 + - * / 和括号）。"""

    name = "calculator"
    description = "执行数学表达式计算，支持 + - * /、括号和一元正负号。"
    args_schema = CalculatorArgs

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        expression = str(kwargs.get("expression", "")).strip()
        if not expression:
            raise ToolException("表达式不能为空", suggestion="请传入 expression 参数。")

        try:
            result = eval(expression)
        except ZeroDivisionError as exc:
            raise ToolException("除数不能为 0") from exc
        except Exception as exc:
            raise ToolException("表达式执行失败", suggestion="请检查表达式格式。") from exc

        if not isinstance(result, (int, float)):
            raise ToolException("只支持数值计算表达式")

        return {
            "content": f"计算结果: {result}",
            "data": {"expression": expression, "result": result},
        }
