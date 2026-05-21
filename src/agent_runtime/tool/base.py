from __future__ import annotations

import asyncio
import copy
import json
from abc import ABC
from typing import Any, Mapping

import jsonschema
from pydantic import BaseModel, Field, ValidationError

from agent_runtime.schema.policy import RiskLevel
from agent_runtime.schema.tool import ToolCall


class ToolException(Exception):
    """Tool 执行时可抛出的受控异常。"""

    def __init__(
            self,
            message: str,
            suggestion: str = "",
    ) -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class ToolResult(BaseModel):
    """统一的 Tool 执行结果。"""

    success: bool = Field(..., description="Tool 是否执行成功")
    content: str = Field(default="", description="提供给 Agent 的文本结果")
    data: Any = Field(default=None, description="原始结构化数据")
    error: str | None = Field(default=None, description="错误信息")
    suggestion: str | None = Field(default=None, description="修复建议")

    @classmethod
    def from_value(cls, value: Any) -> "ToolResult":
        """
        将 Tool 的任意返回值归一化为 ToolResult。

        支持三类返回：
        1. 已经是 ToolResult：直接返回
        2. dict 且包含 content：按 ToolResult-like 结构解析
        3. 其他任意对象：序列化成 content，同时保留原始 data
        """
        if isinstance(value, ToolResult):
            return value

        if isinstance(value, dict) and "content" in value:
            content = value.get("content", "")

            return cls(
                success=bool(value.get("success", True)),
                content="" if content is None else str(content),
                data=value.get("data", value),
                error=value.get("error"),
                suggestion=value.get("suggestion"),
            )

        try:
            content = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            content = str(value)

        return cls(
            success=True,
            content=content,
            data=value,
        )


class BaseTool(ABC):
    """
    可治理的确定性执行单元。

    Tool 是 Runtime 暴露给 Agent 的受控执行能力。
    BaseTool 负责处理单个 Tool 的执行生命周期：

    - 参数构造
    - 参数校验
    - 同步 / 异步执行适配
    - timeout
    - retry
    - 受控异常归一化
    - 返回值归一化

    Policy、权限审批、用户确认、Step 记录不应该放在这里，
    而应该放在 Executor / PolicyEngine / Runtime 层。
    """

    name: str
    description: str
    input_schema: type[BaseModel] | dict[str, Any] | None = None

    preconditions: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    risk_level: RiskLevel = "low"
    generic: bool = False
    idempotent: bool = True

    timeout: float = 60.0
    max_retries: int = 0
    retry_delay: float = 1.0
    retry_backoff: float = 1.5

    strict: bool = True
    handle_validation_error: bool = True
    handle_tool_error: bool = True

    @staticmethod
    def build_args(
            request: ToolCall,
    ) -> dict[str, Any]:
        """
        从 ToolCall 构造 Tool 入参。

        默认直接使用 request.args。
        子类可以覆盖这个方法，把 Agent 的原始参数转换成 Tool 真正需要的参数。
        """
        return dict(request.args or {})

    def execute(
            self,
            **kwargs: Any,
    ) -> Any:
        """
        同步 Tool 的执行入口。

        同步 Tool 实现这个方法即可。
        异步 Tool 可以不实现 execute，直接覆盖 aexecute。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement execute() or aexecute()."
        )

    async def aexecute(
            self,
            **kwargs: Any,
    ) -> Any:
        """
        异步 Tool 的执行入口。

        默认把同步 execute 丢到线程池里执行。
        真正的异步 Tool 应该覆盖这个方法，避免不必要的线程切换。
        """
        return await asyncio.to_thread(self.execute, **kwargs)

    def tool_schema(self) -> dict[str, Any]:
        """
        返回暴露给 Agent / Runtime 的 Tool 描述。
        """
        params = self._schema_for_display()

        return {
            "tool": self.name,
            "description": self.description,
            "input_schema": params,
            "preconditions": list(self.preconditions),
            "side_effects": list(self.side_effects),
            "tags": sorted(self.tags),
            "risk_level": self._risk_level_value(),
            "generic": self.generic,
            "idempotent": self.idempotent,
            "strict": self.strict,
        }

    def _risk_level_value(self) -> str:
        """
        兼容 RiskLevel 是 Literal[str] 或 Enum 的情况。
        """
        value = self.risk_level
        return str(getattr(value, "value", value))

    def _raw_json_schema(self) -> dict[str, Any]:
        """
        获取 Tool 的原始 JSON Schema。

        input_schema 支持三种形态：
        1. None：无参数 Tool
        2. dict：手写 JSON Schema
        3. Pydantic BaseModel：通过 model_json_schema 生成
        """
        if self.input_schema is None:
            return {
                "type": "object",
                "properties": {},
            }

        if isinstance(self.input_schema, dict):
            return copy.deepcopy(self.input_schema)

        return self.input_schema.model_json_schema()

    def _apply_strict_object_schema(
            self,
            schema: dict[str, Any],
    ) -> dict[str, Any]:
        """
        strict=True 时，禁止顶层额外参数。

        这里只处理顶层 object。
        更复杂的嵌套约束应该交给 Pydantic model_config 或手写 JSON Schema。
        """
        if self.strict and schema.get("type") == "object":
            schema.setdefault("additionalProperties", False)

        return schema

    def _schema_for_display(self) -> dict[str, Any]:
        """
        生成给 Agent 看的 schema。
        """
        schema = self._raw_json_schema()
        return self._apply_strict_object_schema(schema)

    def _schema_for_validation(self) -> dict[str, Any]:
        """
        生成运行时校验使用的 schema。
        """
        schema = self._raw_json_schema()
        return self._apply_strict_object_schema(schema)

    def _validate_input(
            self,
            params: Mapping[str, Any],
    ) -> dict[str, Any]:
        """
        校验并标准化 Tool 输入参数。
        """
        params_dict = dict(params)

        if self.input_schema is None:
            return params_dict

        if isinstance(self.input_schema, dict):
            jsonschema.validate(
                instance=params_dict,
                schema=self._schema_for_validation(),
            )
            return params_dict

        validated = self.input_schema.model_validate(params_dict)
        return validated.model_dump()

    def _effective_retries(self) -> int:
        """
        计算实际重试次数。

        非幂等 Tool 不自动 retry，避免重复副作用。
        例如 send_email / write_file / delete_file / submit_form。
        """
        if not self.idempotent:
            return 0

        return max(0, int(self.max_retries))

    async def _sleep_before_retry(
            self,
            attempt: int,
    ) -> None:
        """
        retry 间隔。

        attempt 从 0 开始。
        第一次 retry 等 retry_delay 秒，
        之后按 retry_backoff 指数退避。
        """
        if self.retry_delay <= 0:
            return

        delay = self.retry_delay * (self.retry_backoff ** attempt)
        await asyncio.sleep(delay)

    async def arun(
            self,
            params: Mapping[str, Any] | None = None,
    ) -> ToolResult:
        """
        Tool 的统一异步执行入口。

        Runtime / Executor 应该调用这个方法，而不是直接调用 execute / aexecute。
        """
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

        retries = self._effective_retries()
        last_exc: BaseException | None = None

        for attempt in range(retries + 1):
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

            except Exception as e:
                last_exc = e

            if attempt < retries:
                await self._sleep_before_retry(attempt)

        return ToolResult(
            success=False,
            content="",
            error=f"执行失败: {last_exc}",
            suggestion="请稍后重试或检查 Tool 状态。",
        )
