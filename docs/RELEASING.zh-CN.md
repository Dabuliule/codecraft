# 发布 CodeCraft

[English](RELEASING.md)

CodeCraft 使用 PEP 440 包版本和与之匹配的 Git tag。Alpha 版本使用
`0.1.0a3` 这样的版本号，以及 `v0.1.0a3` 这样的 tag。

## 准备

1. 从干净的 `develop` 分支开始，并将它变基到最新的 `main`。
2. 更新 `pyproject.toml` 中的 `project.version`，然后运行 `uv lock`。
3. 在 `CHANGELOG.md` 和 `CHANGELOG.zh-CN.md` 中加入面向用户的变更，
   再创建 `docs/releases/vX.Y.Z.md` 与
   `docs/releases/vX.Y.Z.zh-CN.md` 两份发布说明。英文版是 GitHub Release
   正文的权威来源，并且必须链接到中文版。
4. 运行本地发布门禁：

   ```zsh
   uv run ruff format --check .
   uv run ruff check .
   uv run pytest
   uv build
   uvx twine check dist/*
   ```

5. 使用 `chore(release): prepare vX.Y.Z` 提交发布准备，并推送 `develop`。
6. 等待 `develop` CI 通过。

## 发布

1. 将 `develop` 合入 `main`，推送 `main` 并等待 CI 通过。
2. 在 `main` 上手动运行 Release workflow，完成包构建 dry-run。
3. 在验证过的 `main` commit 上创建 annotated tag：

   ```zsh
   git tag -a vX.Y.Z -m "CodeCraft vX.Y.Z"
   git push origin vX.Y.Z
   ```

4. 等待 tag 触发的 Release workflow 通过。
5. 确认 GitHub Release 同时包含 wheel 和 source distribution；PEP 440
   预发布版本必须在 GitHub 上标记为 Pre-release。
6. 将 `develop` 变基到已发布的 `main` 并推送。

当版本号与 tag 不匹配、中英文发布说明缺失或为空，或者 tag 对应 commit
不在 `origin/main` 中时，Release workflow 会拒绝发布。版本化英文文档是
GitHub Release 正文的权威来源；中英文 Changelog 用于维护精简的跨版本历史。
