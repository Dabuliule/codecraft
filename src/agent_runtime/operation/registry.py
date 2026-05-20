from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from agent_runtime.operation.base import BaseOperation


class OperationRegistry:
    """Operation 注册中心。"""

    def __init__(
            self,
            operations: Iterable[BaseOperation] | None = None,
            *,
            include_builtins: bool = True,
    ) -> None:
        self._operations: Dict[str, BaseOperation] = {}
        self._intents: Dict[str, str] = {}
        self._tags: Dict[str, set[str]] = {}

        if include_builtins:
            self.register_builtin_operations()

        for operation in operations or []:
            self.register(operation)

    def register(
            self,
            operation: BaseOperation,
            *,
            overwrite: bool = False,
    ) -> None:
        name = getattr(operation, "name", "")
        intent = getattr(operation, "intent", "")
        if not name:
            raise ValueError("Operation 必须定义非空 name。")
        if not intent:
            raise ValueError("Operation 必须定义非空 intent。")
        if not overwrite and name in self._operations:
            raise ValueError(f"Operation '{name}' 已被注册。")
        if not overwrite and intent in self._intents:
            raise ValueError(f"Intent '{intent}' 已被 Operation 绑定。")

        if overwrite and name in self._operations:
            old = self._operations[name]
            self._intents.pop(old.intent, None)
            for names in self._tags.values():
                names.discard(name)

        self._operations[name] = operation
        self._intents[intent] = name
        for tag in getattr(operation, "tags", set()) or set():
            self._tags.setdefault(tag, set()).add(name)

    def inject(
            self,
            operations: Iterable[BaseOperation],
            *,
            overwrite: bool = False,
    ) -> None:
        for operation in operations:
            self.register(operation, overwrite=overwrite)

    def register_builtin_operations(self) -> None:
        from agent_runtime.operation import builtin as builtin_module

        for class_name in getattr(builtin_module, "__all__", []):
            operation_cls = getattr(builtin_module, class_name, None)
            if not isinstance(operation_cls, type):
                continue
            if not issubclass(operation_cls, BaseOperation):
                continue
            self.register(operation_cls())

    def get(self, name: str) -> Optional[BaseOperation]:
        return self._operations.get(name)

    def get_by_intent(self, intent: str) -> Optional[BaseOperation]:
        name = self._intents.get(intent)
        if name is None:
            return None
        return self._operations.get(name)

    def list_operations(self, tag: str | None = None) -> List[BaseOperation]:
        if tag is None:
            return list(self._operations.values())
        return [
            self._operations[name]
            for name in sorted(self._tags.get(tag, set()))
        ]

    def names(self, tag: str | None = None) -> List[str]:
        if tag is None:
            return list(self._operations.keys())
        return sorted(self._tags.get(tag, set()))

    def intents(self) -> List[str]:
        return list(self._intents.keys())

    def tags(self) -> List[str]:
        return sorted(self._tags.keys())

    def operation_schemas(self) -> List[dict]:
        return [
            operation.operation_schema()
            for operation in self._operations.values()
        ]

    def __len__(self) -> int:
        return len(self._operations)

    def __contains__(self, name: str) -> bool:
        return name in self._operations
