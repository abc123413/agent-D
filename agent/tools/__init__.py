"""
工具注册表 - 管理所有可用工具

技能YAML中通过 tools 字段声明需要的工具，
ToolRegistry负责实例化并注入到Agent执行流程中。
"""

from typing import Optional
from .base import BaseTool
from .file_tools import FileReader, DirectoryLister, FileSearcher
from .git_tools import GitDiff, GitLog, GitBlame
from .shell_tools import ShellRunner
from .http_tools import HttpRequest


class ToolRegistry:
    def __init__(self, workspace: str = "."):
        self.workspace = workspace
        self._tools: dict[str, BaseTool] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register(FileReader(self.workspace))
        self.register(DirectoryLister(self.workspace))
        self.register(FileSearcher(self.workspace))
        self.register(GitDiff(self.workspace))
        self.register(GitLog(self.workspace))
        self.register(GitBlame(self.workspace))
        self.register(ShellRunner(self.workspace))
        self.register(HttpRequest())

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def get_tools_for_skill(self, tool_names: list[str]) -> list[BaseTool]:
        """根据技能声明的tool列表返回对应工具实例"""
        return [self._tools[n] for n in tool_names if n in self._tools]

    def get_function_schemas(self, tool_names: list[str] = None) -> list[dict]:
        """获取OpenAI function calling格式的schema"""
        if tool_names:
            tools = self.get_tools_for_skill(tool_names)
        else:
            tools = list(self._tools.values())
        return [t.to_function_schema() for t in tools]

    def list_all(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]
