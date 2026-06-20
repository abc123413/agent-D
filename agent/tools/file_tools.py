"""
文件操作工具 - 读取文件、列出目录、搜索文件内容
"""

import os
import glob as globlib
from pathlib import Path

from .base import BaseTool, ToolParam, ToolResult


class FileReader(BaseTool):
    name = "file_reader"
    description = "读取指定文件的内容。支持文本文件、代码文件等。"
    parameters = [
        ToolParam(name="path", type="string", description="文件路径", required=True),
        ToolParam(name="start_line", type="integer", description="起始行号(从1开始)", required=False),
        ToolParam(name="end_line", type="integer", description="结束行号", required=False),
    ]

    def __init__(self, workspace: str = "."):
        self.workspace = Path(workspace)

    async def execute(self, **kwargs) -> ToolResult:
        path = kwargs.get("path", "")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")

        filepath = self.workspace / path
        if not filepath.exists():
            return ToolResult(success=False, error=f"文件不存在: {path}")
        if not filepath.is_file():
            return ToolResult(success=False, error=f"不是文件: {path}")

        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            if start_line or end_line:
                s = (start_line or 1) - 1
                e = end_line or len(lines)
                lines = lines[s:e]
                content = "\n".join(lines)

            if len(content) > 50000:
                content = content[:50000] + "\n... [截断，文件过大]"

            return ToolResult(success=True, data={"content": content, "lines": len(lines), "path": path})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class DirectoryLister(BaseTool):
    name = "list_directory"
    description = "列出目录下的文件和子目录"
    parameters = [
        ToolParam(name="path", type="string", description="目录路径", required=True),
        ToolParam(name="pattern", type="string", description="glob匹配模式，如 *.py", required=False),
        ToolParam(name="recursive", type="boolean", description="是否递归搜索", required=False),
    ]

    def __init__(self, workspace: str = "."):
        self.workspace = Path(workspace)

    async def execute(self, **kwargs) -> ToolResult:
        path = kwargs.get("path", ".")
        pattern = kwargs.get("pattern", "*")
        recursive = kwargs.get("recursive", False)

        dirpath = self.workspace / path
        if not dirpath.exists():
            return ToolResult(success=False, error=f"目录不存在: {path}")

        try:
            if recursive:
                files = list(dirpath.rglob(pattern))
            else:
                files = list(dirpath.glob(pattern))

            items = []
            for f in sorted(files)[:200]:
                rel = f.relative_to(self.workspace)
                items.append({
                    "path": str(rel),
                    "type": "dir" if f.is_dir() else "file",
                    "size": f.stat().st_size if f.is_file() else 0,
                })

            return ToolResult(success=True, data={"items": items, "total": len(files)})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FileSearcher(BaseTool):
    name = "search_files"
    description = "在文件中搜索指定内容（类似grep）"
    parameters = [
        ToolParam(name="pattern", type="string", description="搜索的文本或正则表达式", required=True),
        ToolParam(name="path", type="string", description="搜索的目录路径", required=False),
        ToolParam(name="file_pattern", type="string", description="文件名匹配，如 *.py", required=False),
    ]

    def __init__(self, workspace: str = "."):
        self.workspace = Path(workspace)

    async def execute(self, **kwargs) -> ToolResult:
        import re
        pattern = kwargs.get("pattern", "")
        path = kwargs.get("path", ".")
        file_pattern = kwargs.get("file_pattern", "*")

        dirpath = self.workspace / path
        if not dirpath.exists():
            return ToolResult(success=False, error=f"路径不存在: {path}")

        results = []
        try:
            regex = re.compile(pattern)
        except re.error:
            regex = None

        for filepath in dirpath.rglob(file_pattern):
            if not filepath.is_file():
                continue
            try:
                lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
                for i, line in enumerate(lines, 1):
                    matched = (regex.search(line) if regex else pattern in line)
                    if matched:
                        results.append({
                            "file": str(filepath.relative_to(self.workspace)),
                            "line": i,
                            "content": line.strip()[:200],
                        })
                        if len(results) >= 50:
                            return ToolResult(success=True, data={"matches": results, "truncated": True})
            except (UnicodeDecodeError, PermissionError):
                continue

        return ToolResult(success=True, data={"matches": results, "truncated": False})
