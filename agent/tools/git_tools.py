"""
Git工具 - 获取代码变更、提交历史、blame等
"""

import asyncio
from pathlib import Path

from .base import BaseTool, ToolParam, ToolResult


class GitDiff(BaseTool):
    name = "git_diff"
    description = "获取git代码变更。可对比分支、查看未提交修改等。"
    parameters = [
        ToolParam(name="target", type="string", description="对比目标，如 main, HEAD~3, 或留空看未提交修改", required=False),
        ToolParam(name="file_path", type="string", description="只看某个文件的变更", required=False),
    ]

    def __init__(self, workspace: str = "."):
        self.workspace = workspace

    async def execute(self, **kwargs) -> ToolResult:
        target = kwargs.get("target", "")
        file_path = kwargs.get("file_path", "")

        cmd = ["git", "diff"]
        if target:
            cmd.append(target)
        if file_path:
            cmd.extend(["--", file_path])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=self.workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode("utf-8", errors="replace")
            if proc.returncode != 0:
                return ToolResult(success=False, error=stderr.decode("utf-8", errors="replace"))
            if len(output) > 50000:
                output = output[:50000] + "\n... [截断]"
            return ToolResult(success=True, data={"diff": output})
        except asyncio.TimeoutError:
            return ToolResult(success=False, error="git diff 超时")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitLog(BaseTool):
    name = "git_log"
    description = "获取git提交历史"
    parameters = [
        ToolParam(name="count", type="integer", description="显示最近N条提交，默认10", required=False),
        ToolParam(name="file_path", type="string", description="只看某个文件的提交历史", required=False),
    ]

    def __init__(self, workspace: str = "."):
        self.workspace = workspace

    async def execute(self, **kwargs) -> ToolResult:
        count = kwargs.get("count", 10)
        file_path = kwargs.get("file_path", "")

        cmd = ["git", "log", f"--oneline", f"-{count}", "--format=%H|%an|%ad|%s", "--date=short"]
        if file_path:
            cmd.extend(["--", file_path])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=self.workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode != 0:
                return ToolResult(success=False, error=stderr.decode("utf-8", errors="replace"))

            commits = []
            for line in stdout.decode("utf-8", errors="replace").strip().splitlines():
                parts = line.split("|", 3)
                if len(parts) == 4:
                    commits.append({"hash": parts[0][:8], "author": parts[1], "date": parts[2], "message": parts[3]})
            return ToolResult(success=True, data={"commits": commits})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitBlame(BaseTool):
    name = "git_blame"
    description = "查看文件每一行的最后修改者"
    parameters = [
        ToolParam(name="file_path", type="string", description="文件路径", required=True),
    ]

    def __init__(self, workspace: str = "."):
        self.workspace = workspace

    async def execute(self, **kwargs) -> ToolResult:
        file_path = kwargs.get("file_path", "")
        if not file_path:
            return ToolResult(success=False, error="需要指定file_path")

        cmd = ["git", "blame", "--porcelain", file_path]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=self.workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode != 0:
                return ToolResult(success=False, error=stderr.decode("utf-8", errors="replace"))
            output = stdout.decode("utf-8", errors="replace")
            if len(output) > 30000:
                output = output[:30000] + "\n... [截断]"
            return ToolResult(success=True, data={"blame": output})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
