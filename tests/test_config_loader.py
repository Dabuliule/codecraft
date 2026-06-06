from __future__ import annotations

from codecraft.config import ConfigLoader, ConfigOverrides


def test_config_loader_applies_precedence_order(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "workspace"
    home.mkdir()
    cwd.mkdir()
    (home / "profiles").mkdir()
    (cwd / ".codecraft").mkdir()

    (home / "config.toml").write_text(
        """
[model]
provider = "openai"
name = "gpt-user"

[approval]
policy = "never"

[sandbox]
network_access = false
""",
        encoding="utf-8",
    )
    (home / "profiles" / "fast.toml").write_text(
        """
[model]
name = "qwen-fast"
""",
        encoding="utf-8",
    )
    (cwd / ".codecraft" / "config.toml").write_text(
        """
[model]
provider = "qwen"

[sandbox]
network_access = true

[instructions]
user = "Always answer in Chinese."
""",
        encoding="utf-8",
    )
    explicit = tmp_path / "explicit.toml"
    explicit.write_text(
        """
[approval]
policy = "untrusted"
""",
        encoding="utf-8",
    )

    settings = ConfigLoader(cwd=cwd, codecraft_home=home).load(
        profile="fast",
        config_path=explicit,
        overrides=ConfigOverrides.from_cli(model="qwen-cli"),
    )

    assert settings.model.provider == "qwen"
    assert settings.model.name == "qwen-cli"
    assert settings.approval.policy == "untrusted"
    assert settings.sandbox.network_access is True
    assert settings.instructions.user == "Always answer in Chinese."


def test_config_loader_uses_builtin_defaults_when_files_are_missing(tmp_path):
    settings = ConfigLoader(cwd=tmp_path, codecraft_home=tmp_path / "home").load()

    assert settings.model.provider == "qwen"
    assert settings.model.name == "qwen-plus"
    assert settings.model.api_key_env is None
    assert settings.approval.policy == "on_request"
    assert settings.sandbox.mode == "workspace_write"
    assert settings.sandbox.network_access is False
    assert settings.instructions.user is None
