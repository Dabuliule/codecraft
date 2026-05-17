from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

import jsonschema
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class ToolException(Exception):
    """工具执行时可抛出的异常，Agent 可据此决定下一步动作。"""

    def __init__(self, message: str, suggestion: str = ""):
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class ToolResult(BaseModel):
    """统一的工具返回结果。"""

    success: bool = Field(..., description="工具是否执行成功")
    content: str = Field(default="", description="提供给 LLM 的文本结果")
    data: Any = Field(default=None, description="原始结构化数据")
    error: Optional[str] = Field(default=None, description="错误信息")
    suggestion: Optional[str] = Field(default=None, description="修复建议")

    @classmethod
    def from_value(cls, value: Any) -> "ToolResult":
        """智能包装各种返回值。"""

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
    """工具基类：只负责‘定义’和‘执行’，不侵入任何工作流框架。

    使用方式：子类必须提供 `name`, `description`, `args_schema` 并实现 `_run`。
    """

    # 工具标识
    name: str
    description: str

    # 输入 Schema（只接受 Pydantic v2 模型 或 JSON Schema 字典）
    args_schema: Type[BaseModel] | Dict[str, Any]

    # 执行配置
    timeout: float = 60.0
    max_retries: int = 0

    # 严格模式开关（若为 True 且 args_schema 为 dict，则用 jsonschema 强校验）
    strict: bool = True

    # 子类可以覆盖此属性，以允许某些错误被‘吞掉’并返回友好消息给模型
    handle_validation_error: bool = True
    handle_tool_error: bool = True

    @abstractmethod
    def _run(self, **kwargs: Any) -> Any:
        """同步执行逻辑（子类实现）。返回任意值，会被包装为 ToolResult。"""
        ...

    # 异步版本：默认使用线程池执行同步 _run，子类可以重写以实现真正的异步
    async def _arun(self, **kwargs: Any) -> Any:
        return await asyncio.to_thread(self._run, **kwargs)

    def tool_schema(self) -> Dict[str, Any]:
        """返回标准的 function 工具描述字典。"""
        if isinstance(self.args_schema, dict):
            params = self.args_schema
        else:
            params = self.args_schema.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
            "strict": self.strict,
        }

    def _validate_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """根据 args_schema 校验参数字典，并返回可执行参数。"""
        if self.args_schema is None:
            return params
        if isinstance(self.args_schema, dict):
            if self.strict:
                jsonschema.validate(instance=params, schema=self.args_schema)
            return params

        validated = self.args_schema.model_validate(params)
        # 使用模型输出，确保类型转换/默认值生效
        return validated.model_dump()

    def run(self, params: Dict[str, Any]) -> ToolResult:
        """执行工具，封装：验证、重试、异常处理、结果标准化。"""
        params = params or {}

        try:
            validated_params = self._validate_input(params)
        except (ValidationError, jsonschema.ValidationError) as e:
            if self.handle_validation_error:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"参数校验失败: {e}",
                    suggestion="请根据函数描述修正参数后重试。",
                )
            raise

        # 2. 执行（同步路径不强制超时）
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                raw_result = self._run(**validated_params)
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
            except Exception as e:
                last_exc = e
                if attempt < self.max_retries:
                    logger.warning("工具 '%s' 异常: %s，正在重试...", self.name, e)
                    continue
                break

        return ToolResult(
            success=False,
            content="",
            error=f"执行失败: {last_exc}",
            suggestion="请稍后重试或检查工具状态。",
        )

    async def arun(self, params: Dict[str, Any]) -> ToolResult:
        """异步执行工具。"""
        params = params or {}

        try:
            validated_params = self._validate_input(params)
        except (ValidationError, jsonschema.ValidationError) as e:
            if self.handle_validation_error:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"参数校验失败: {e}",
                    suggestion="请根据函数描述修正参数后重试。",
                )
            raise

        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                async with asyncio.timeout(self.timeout):
                    raw_result = await self._arun(**validated_params)
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
                last_exc = TimeoutError(f"工具执行超时 ({self.timeout}s)")
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
            suggestion="请稍后重试或检查工具状态。",
        )
