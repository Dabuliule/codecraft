import asyncio
import inspect
from typing import Any, Callable, Optional, Type, Union, get_type_hints, overload

from pydantic import BaseModel, create_model

from .base import BaseTool


def _create_schema_from_function(fn: Callable, model_name: str) -> Type[BaseModel]:
    """根据函数的类型注解动态创建 Pydantic 模型，作为 args_schema。

    参数：
        fn: 函数对象
        model_name: 生成的模型名称

    返回：
        Pydantic BaseModel 子类，包含与函数参数对应的字段。
    """
    sig = inspect.signature(fn)
    type_hints = get_type_hints(fn, include_extras=True)
    fields = {}

    for param in sig.parameters.values():
        # 跳过 self/cls 和返回值标注
        if param.name in ("self", "cls", "return"):
            continue

        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise TypeError(
                f"工具函数 {fn.__name__} 不支持 *args/**kwargs，请使用显式命名参数。"
            )

        if param.name not in type_hints:
            raise TypeError(
                f"工具函数 {fn.__name__} 的参数 '{param.name}' 必须提供类型注解。"
            )

        # 强制要求类型注解
        field_type = type_hints[param.name]

        # 处理默认值
        if param.default is not inspect.Parameter.empty:
            fields[param.name] = (field_type, param.default)
        else:
            fields[param.name] = (field_type, ...)

    return create_model(model_name, **fields)


@overload
def tool(func: Callable) -> BaseTool:
    """直接作为装饰器使用：@tool"""
    ...


@overload
def tool(
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        args_schema: Optional[Type[BaseModel]] = None,
) -> Callable[[Callable], BaseTool]:
    """作为装饰器工厂使用：@tool() 或 @tool(name="...")"""
    ...


def tool(
        func: Optional[Callable] = None,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        args_schema: Optional[Type[BaseModel]] = None,
) -> Union[BaseTool, Callable[[Callable], BaseTool]]:
    """将普通函数或协程转换为 BaseTool 实例。

    用法：
        @tool
        def my_tool(x: int) -> str: ...

        @tool(name="search")
        async def search(q: str) -> dict: ...
    """

    def decorator(fn: Callable) -> BaseTool:
        tool_name = name or fn.__name__
        tool_description = description or inspect.getdoc(fn) or ""

        if args_schema:
            schema = args_schema
        else:
            schema = _create_schema_from_function(fn, tool_name)

        is_async = asyncio.iscoroutinefunction(fn)

        # 动态生成工具子类并实例化
        if not is_async:
            class SyncTool(BaseTool):
                name = tool_name
                description = tool_description
                args_schema = schema

                def _run(self, **kwargs: Any) -> Any:
                    return fn(**kwargs)

            return SyncTool()

        else:
            class AsyncTool(BaseTool):
                name = tool_name
                description = tool_description
                args_schema = schema

                def _run(self, **kwargs: Any) -> Any:
                    raise RuntimeError(
                        f"工具 '{tool_name}' 仅支持异步调用，请使用 arun。"
                    )

                async def _arun(self, **kwargs: Any) -> Any:
                    return await fn(**kwargs)

            return AsyncTool()

    # 根据调用方式返回不同结果
    if func is None:
        # 带括号用法（工厂模式），返回装饰器
        return decorator
    # 无括号用法，直接装饰，返回工具实例
    return decorator(func)
