"""
工具基类 - 所有内置工具的统一接口

每个工具实现 execute() 方法，在沙箱环境中运行。
技能YAML中通过 tools 字段声明可用工具，运行时Agent通过function calling调用。
"""

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel


class ToolParam(BaseModel):
    name: str
    type: str = "string"
    description: str = ""
    required: bool = False
    default: Any = None


class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: str = ""


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    parameters: list[ToolParam] = []

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        pass

    def to_function_schema(self) -> dict:
        """转为OpenAI function calling格式"""
        properties = {}
        required = []
        for p in self.parameters:
            properties[p.name] = {
                "type": p.type,
                "description": p.description,
            }
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
