from __future__ import annotations

import pytest

from codecraft.tool.builtin.filesystem import (
    FileExistsTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)


@pytest.mark.anyio
async def test_filesystem_tools_resolve_relative_paths_inside_workspace(tmp_path):
    note = tmp_path / "notes" / "note.txt"

    write_result = await WriteFileTool(workspace_root=tmp_path).arun(
        {
            "path": "notes/note.txt",
            "content": "hello workspace",
        }
    )
    read_result = await ReadFileTool(workspace_root=tmp_path).arun(
        {
            "path": "notes/note.txt",
        }
    )

    assert write_result.success is True
    assert write_result.data["path"] == str(note)
    assert note.read_text(encoding="utf-8") == "hello workspace"
    assert read_result.success is True
    assert read_result.content == "hello workspace"
    assert read_result.data["path"] == str(note)


@pytest.mark.anyio
async def test_filesystem_tools_allow_absolute_paths_inside_workspace(tmp_path):
    note = tmp_path / "note.txt"
    note.write_text("inside", encoding="utf-8")

    result = await ReadFileTool(workspace_root=tmp_path).arun(
        {
            "path": str(note),
        }
    )

    assert result.success is True
    assert result.content == "inside"


@pytest.mark.anyio
async def test_filesystem_tools_reject_parent_escape(tmp_path):
    result = await ReadFileTool(workspace_root=tmp_path).arun(
        {
            "path": "../outside.txt",
        }
    )

    assert result.success is False
    assert result.error == "路径超出 workspace"
    assert result.suggestion == f"请使用 {tmp_path.resolve()} 下的路径。"


@pytest.mark.anyio
async def test_filesystem_tools_reject_absolute_escape(tmp_path):
    outside = tmp_path.parent / "outside.txt"

    result = await WriteFileTool(workspace_root=tmp_path).arun(
        {
            "path": str(outside),
            "content": "should not write",
        }
    )

    assert result.success is False
    assert result.error == "路径超出 workspace"
    assert not outside.exists()


@pytest.mark.anyio
async def test_file_exists_reports_missing_path_inside_workspace(tmp_path):
    result = await FileExistsTool(workspace_root=tmp_path).arun(
        {
            "path": "missing.txt",
        }
    )

    assert result.success is True
    assert result.data == {
        "path": str(tmp_path / "missing.txt"),
        "exists": False,
    }


@pytest.mark.anyio
async def test_list_dir_returns_workspace_entries(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "folder").mkdir()

    result = await ListDirTool(workspace_root=tmp_path).arun({"path": "."})

    assert result.success is True
    assert result.data["path"] == str(tmp_path)
    assert result.data["items"] == [
        {"name": "a.txt", "is_dir": False},
        {"name": "folder", "is_dir": True},
    ]
