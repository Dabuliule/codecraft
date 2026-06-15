from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codecraft.approval.policy import ApprovalPolicy
from codecraft.config.settings import RuntimeSettings
from codecraft.sandbox.policy import SandboxMode


@dataclass(frozen=True)
class ConfigOverrides:
    """命令行参数转换后的配置覆盖层。"""

    values: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_cli(
        cls,
        *,
        provider: str | None = None,
        model: str | None = None,
        approval_policy: ApprovalPolicy | None = None,
        sandbox_mode: SandboxMode | None = None,
        network_access: bool | None = None,
        codecraft_home: Path | None = None,
    ) -> ConfigOverrides:
        values: dict[str, Any] = {}
        _set_nested(values, ["model", "provider"], provider)
        _set_nested(values, ["model", "name"], model)
        _set_nested(values, ["approval", "policy"], approval_policy)
        _set_nested(values, ["sandbox", "mode"], sandbox_mode)
        _set_nested(values, ["sandbox", "network_access"], network_access)
        _set_nested(values, ["paths", "codecraft_home"], codecraft_home)
        return cls(values=values)


class ConfigLoader:
    """按默认值、全局配置、profile、项目配置和显式参数加载配置。"""

    def __init__(
        self,
        *,
        cwd: Path | None = None,
        codecraft_home: Path | None = None,
    ) -> None:
        self.cwd = (cwd or Path.cwd()).expanduser().resolve()
        self.codecraft_home = (codecraft_home or Path("~/.codecraft")).expanduser()

    def load(
        self,
        *,
        profile: str | None = None,
        config_path: Path | None = None,
        overrides: ConfigOverrides | None = None,
    ) -> RuntimeSettings:
        """合并所有配置层，并校验成 RuntimeSettings。"""
        merged = RuntimeSettings().model_dump(mode="python")
        for layer in self._config_layers(profile=profile, config_path=config_path):
            if layer.exists():
                merged = _deep_merge(merged, _read_toml(layer))

        if overrides is not None:
            merged = _deep_merge(merged, overrides.values)

        return RuntimeSettings.model_validate(merged)

    def _config_layers(
        self,
        *,
        profile: str | None,
        config_path: Path | None,
    ) -> list[Path]:
        """返回配置文件加载顺序，后面的层覆盖前面的层。"""
        layers = [
            self.codecraft_home / "config.toml",
        ]
        if profile:
            layers.append(self.codecraft_home / "profiles" / f"{profile}.toml")

        layers.append(self.cwd / ".codecraft" / "config.toml")

        if config_path:
            layers.append(config_path.expanduser())

        return layers


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"config file must contain a TOML table: {path}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """递归合并 dict，叶子值由 override 覆盖。"""
    result = dict(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = _deep_merge(current, value)
        else:
            result[key] = value
    return result


def _set_nested(values: dict[str, Any], path: list[str], value: Any) -> None:
    """把 CLI 参数写入嵌套配置 dict，None 表示不覆盖。"""
    if value is None:
        return

    target = values
    for key in path[:-1]:
        child = target.setdefault(key, {})
        if not isinstance(child, dict):
            raise ValueError(f"cannot set nested config value below {key}")
        target = child
    target[path[-1]] = value
