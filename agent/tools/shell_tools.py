"""
Shell执行工具 - 在受限环境中运行命令

通过白名单机制控制可执行的命令，防止恶意操作。
技能YAML中可通过 allowed_commands 字段进一步限制。
"""

import asyncio
from pathlib import Path

from .base import BaseTool, ToolParam, ToolResult

GLOBAL_ALLOWED_COMMANDS = [
    "echo", "cat", "head", "tail", "wc", "grep", "find", "ls", "tree",
    "python", "pip", "node", "npm", "npx",
    "eslint", "pylint", "flake8", "mypy", "black", "prettier",
    "pytest", "jest", "go", "cargo",
    "curl", "jq",
]

BLOCKED_PATTERNS = [
    "rm -rf /", "rm -rf ~", "mkfs", "dd if=", ":(){", "fork bomb",
    "chmod 777", "sudo", "shutdown", "reboot", "kill -9 1",
]


class ShellRunner(BaseTool):
    name = "shell_run"
    description = "在受控环境中执行shell命令。仅允许白名单内的命令。"
    parameters = [
        ToolParam(name="command", type="string", description="要执行的命令", required=True),
        ToolParam(name="timeout", type="integer", description="超时秒数，默认30", required=False),
    ]

    def __init__(self, workspace: str = ".", allowed_commands: list[str] = None):
        self.workspace = workspace
        self.allowed_commands = allowed_commands or GLOBAL_ALLOWED_COMMANDS

    async def execute(self, **kwargs) -> ToolResult:
        command = kwargs.get("command", "")
        timeout = kwargs.get("timeout", 30)

        if not command.strip():
            return ToolResult(success=False, error="命令为空")

        for blocked in BLOCKED_PATTERNS:
            if blocked in command:
                return ToolResult(success=False, error=f"安全拦截: 命令包含危险操作 '{blocked}'")

        base_cmd = command.strip().split()[0].split("/")[-1]
        if base_cmd not in self.allowed_commands:
            return ToolResult(
                success=False,
                error=f"命令 '{base_cmd}' 不在白名单中。允许的命令: {', '.join(self.allowed_commands[:20])}"
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self.workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            output = stdout.decode("utf-8", errors="replace")
            err_output = stderr.decode("utf-8", errors="replace")

            if len(output) > 30000:
                output = output[:30000] + "\n... [输出截断]"

            return ToolResult(
                success=proc.returncode == 0,
                data={
                    "stdout": output,
                    "stderr": err_output[:5000],
                    "returncode": proc.returncode,
                },
                error=err_output[:1000] if proc.returncode != 0 else "",
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"命令执行超时 ({timeout}秒)")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
