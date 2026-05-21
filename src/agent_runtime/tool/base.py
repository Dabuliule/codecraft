from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

import jsonschema
from pydantic import BaseModel, Field, ValidationError

from agent_runtime.schema.policy import RiskLevel
from agent_runtime.schema.tool import ToolCall

logger = logging.getLogger(__name__)


class ToolException(Exception):
    """Tool 执行时可抛出的受控异常。"""

    def __init__(self, message: str, suggestion: str = ""):
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class ToolResult(BaseModel):
    """统一的 Tool 执行结果。"""

    success: bool = Field(..., description="Tool 是否执行成功")
    content: str = Field(default="", description="提供给 Agent 的文本结果")
    data: Any = Field(default=None, description="原始结构化数据")
    error: Optional[str] = Field(default=None, description="错误信息")
    suggestion: Optional[str] = Field(default=None, description="修复建议")

    @classmethod
    def from_value(cls, value: Any) -> "ToolResult":
        if isinstance(value, ToolResult):
            return value

        if isinstance(value, dict) and "content" in value:
            return cls(
                success=bool(value.get("success", True)),
                content=str(value.get("content", "")),
                data=value.get("data"),
                error=value.get("error"),
                suggestion=value.get("suggestion"),
            )

        try:
            content = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            content = str(value)

        return cls(success=True, content=content, data=value)


class BaseTool(ABC):
    """
    可治理的确定性执行单元。

    Tool 作为 Runtime 暴露给 LLM 的执行能力，由 Runtime 经 policy 校验后执行。
    """

    name: str
    description: str
    input_schema: Type[BaseModel] | Dict[str, Any]
    preconditions: list[str] = []
    side_effects: list[str] = []
    tags: set[str] = set()
    risk_level: RiskLevel = "low"
    generic: bool = False

    timeout: float = 60.0
    max_retries: int = 0
    strict: bool = True
    handle_validation_error: bool = True
    handle_tool_error: bool = True

    def build_args(self, request: ToolCall) -> Dict[str, Any]:
        return dict(request.args)

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        ...

    async def aexecute(self, **kwargs: Any) -> Any:
        return await asyncio.to_thread(self.execute, **kwargs)

    def tool_schema(self) -> Dict[str, Any]:
        if isinstance(self.input_schema, dict):
            params = self.input_schema
        else:
            params = self.input_schema.model_json_schema()

        return {
            "tool": self.name,
            "description": self.description,
            "input_schema": params,
            "preconditions": list(self.preconditions),
            "side_effects": list(self.side_effects),
            "tags": sorted(self.tags),
            "risk_level": self.risk_level,
            "generic": self.generic,
            "strict": self.strict,
        }

    def _validate_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.input_schema is None:
            return params
        if isinstance(self.input_schema, dict):
            if self.strict:
                jsonschema.validate(instance=params, schema=self.input_schema)
            return params

        validated = self.input_schema.model_validate(params)
        return validated.model_dump()

    async def arun(self, params: Dict[str, Any]) -> ToolResult:
        params = params or {}

        try:
            validated_params = self._validate_input(params)
        except (ValidationError, jsonschema.ValidationError) as e:
            if self.handle_validation_error:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"参数校验失败: {e}",
                    suggestion="请根据工具输入结构修正参数后重试。",
                )
            raise

        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                async with asyncio.timeout(self.timeout):
                    raw_result = await self.aexecute(**validated_params)
                return ToolResult.from_value(raw_result)
            except ToolException as e:
                if self.handle_tool_error:
                    return ToolResult(
                        success=False,
                        content="",
                        error=e.message,
                        suggestion=e.suggestion,
                    )
                raise
            except asyncio.TimeoutError:
                last_exc = TimeoutError(f"Tool 执行超时 ({self.timeout}s)")
                if attempt < self.max_retries:
                    await asyncio.sleep(1.5 ** attempt)
                    continue
                break
            except Exception as e:
                last_exc = e
                if attempt < self.max_retries:
                    await asyncio.sleep(1.5 ** attempt)
                    continue
                break

        return ToolResult(
            success=False,
            content="",
            error=f"执行失败: {last_exc}",
            suggestion="请稍后重试或检查 Tool 状态。",
        )
