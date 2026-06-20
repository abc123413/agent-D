"""
Agent执行器 - 支持Tool Calling的LLM执行引擎

当技能声明了tools时，Agent执行器使用function calling模式：
LLM决定调用哪些工具 → 工具执行返回结果 → LLM基于结果生成最终回答

这使得YAML定义的技能具备真正的自动化能力。
"""

import os
import json
import time
from typing import AsyncGenerator
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

from .skill_loader import SkillConfig
from tools import ToolRegistry
from tools.base import ToolResult


@dataclass
class TraceStep:
    step_type: str  # "llm" | "tool"
    name: str
    input: str = ""
    output: str = ""
    start_time: float = 0
    end_time: float = 0
    tokens: dict = field(default_factory=dict)


@dataclass
class ExecutionResult:
    output: str
    trace: list[TraceStep] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class AgentExecutor:
    def __init__(self, model_config: dict = {}, workspace: str = "."):
        self.model_config = model_config
        self.tool_registry = ToolRegistry(workspace)
        self.max_tool_rounds = 5

    def _get_llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.model_config.get("model_name", os.getenv("MODEL_NAME", "gpt-4o-mini")),
            temperature=self.model_config.get("temperature", 0.3),
            max_tokens=self.model_config.get("max_tokens", 4096),
            base_url=os.getenv("OPENAI_API_BASE", None),
            api_key=os.getenv("OPENAI_API_KEY", "sk-placeholder"),
        )

    def _build_messages(self, skill: SkillConfig, user_input: str, history: list[dict] = []) -> list:
        system_content = skill.prompt

        # 将扩展配置(review_rules等)注入系统提示，让LLM能使用具体规则
        config_keys = {"review_rules", "decision_rules", "focus_paths", "output_template"}
        injected = {k: skill.metadata[k] for k in config_keys if k in skill.metadata}
        if injected:
            system_content += "\n\n## 配置数据（严格按此执行）\n```yaml\n"
            import yaml
            system_content += yaml.dump(injected, allow_unicode=True, default_flow_style=False)
            system_content += "```"

        messages = [SystemMessage(content=system_content)]

        for msg in history[-20:]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=user_input))
        return messages

    def _get_skill_tools(self, skill: SkillConfig) -> list[str]:
        """从技能配置中提取声明的工具名列表"""
        tools_cfg = skill.metadata.get("tools", [])
        if isinstance(tools_cfg, list):
            return [t if isinstance(t, str) else t.get("name", "") for t in tools_cfg]
        return []

    async def execute(self, skill: SkillConfig, user_input: str, history: list[dict] = []) -> ExecutionResult:
        """执行技能：如果技能声明了tools，使用function calling模式"""
        tool_names = self._get_skill_tools(skill)
        llm = self._get_llm()
        messages = self._build_messages(skill, user_input, history)
        trace: list[TraceStep] = []
        total_prompt = 0
        total_completion = 0

        if not tool_names:
            step = TraceStep(step_type="llm", name="generate", input=user_input, start_time=time.time())
            response = await llm.ainvoke(messages)
            step.end_time = time.time()
            step.output = response.content[:500]
            usage = getattr(response, "response_metadata", {}).get("token_usage", {})
            step.tokens = usage
            total_prompt += usage.get("prompt_tokens", 0)
            total_completion += usage.get("completion_tokens", 0)
            trace.append(step)
            return ExecutionResult(output=response.content, trace=trace, prompt_tokens=total_prompt, completion_tokens=total_completion)

        # Function calling模式
        function_schemas = self.tool_registry.get_function_schemas(tool_names)
        llm_with_tools = llm.bind_tools(function_schemas)

        for round_num in range(self.max_tool_rounds):
            step = TraceStep(step_type="llm", name=f"plan_round_{round_num+1}", input=f"round {round_num+1}", start_time=time.time())
            response = await llm_with_tools.ainvoke(messages)
            step.end_time = time.time()
            usage = getattr(response, "response_metadata", {}).get("token_usage", {})
            step.tokens = usage
            total_prompt += usage.get("prompt_tokens", 0)
            total_completion += usage.get("completion_tokens", 0)

            if not response.tool_calls:
                step.output = (response.content or "")[:500]
                trace.append(step)
                return ExecutionResult(output=response.content, trace=trace, prompt_tokens=total_prompt, completion_tokens=total_completion)

            step.output = f"tool_calls: {[tc['name'] for tc in response.tool_calls]}"
            trace.append(step)
            messages.append(response)

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool = self.tool_registry.get(tool_name)

                tool_step = TraceStep(step_type="tool", name=tool_name, input=json.dumps(tool_args, ensure_ascii=False)[:300], start_time=time.time())

                if tool:
                    result = await tool.execute(**tool_args)
                    result_str = json.dumps(result.data if result.success else {"error": result.error}, ensure_ascii=False, default=str)
                    tool_step.output = result_str[:500]
                else:
                    result_str = json.dumps({"error": f"工具 {tool_name} 不存在"})
                    tool_step.output = result_str

                tool_step.end_time = time.time()
                trace.append(tool_step)
                messages.append(ToolMessage(content=result_str, tool_call_id=tool_call["id"]))

        # 超过最大轮次
        messages.append(HumanMessage(content="请基于已收集的信息给出最终回答。"))
        step = TraceStep(step_type="llm", name="final_summary", input="summarize", start_time=time.time())
        final = await llm.ainvoke(messages)
        step.end_time = time.time()
        step.output = (final.content or "")[:500]
        usage = getattr(final, "response_metadata", {}).get("token_usage", {})
        step.tokens = usage
        total_prompt += usage.get("prompt_tokens", 0)
        total_completion += usage.get("completion_tokens", 0)
        trace.append(step)
        return ExecutionResult(output=final.content, trace=trace, prompt_tokens=total_prompt, completion_tokens=total_completion)

    async def execute_stream(self, skill: SkillConfig, user_input: str, history: list[dict] = []) -> AsyncGenerator[str, None]:
        """流式执行：tool calling阶段不流式，最终回答流式输出"""
        tool_names = self._get_skill_tools(skill)
        llm = self._get_llm()
        messages = self._build_messages(skill, user_input, history)

        if not tool_names:
            async for chunk in llm.astream(messages):
                if chunk.content:
                    yield chunk.content
            return

        # Tool calling阶段（非流式）
        function_schemas = self.tool_registry.get_function_schemas(tool_names)
        llm_with_tools = llm.bind_tools(function_schemas)

        for round_num in range(self.max_tool_rounds):
            response = await llm_with_tools.ainvoke(messages)

            if not response.tool_calls:
                if response.content:
                    yield response.content
                return

            messages.append(response)

            yield f"\n[正在执行工具调用 - 第{round_num + 1}轮]\n"

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool = self.tool_registry.get(tool_name)

                yield f"  → 调用 {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:100]})\n"

                if tool:
                    result = await tool.execute(**tool_args)
                    result_str = json.dumps(result.data if result.success else {"error": result.error}, ensure_ascii=False, default=str)
                    if result.success:
                        yield f"  ✓ 执行成功\n"
                    else:
                        yield f"  ✗ 执行失败: {result.error}\n"
                else:
                    result_str = json.dumps({"error": f"工具 {tool_name} 不存在"})
                    yield f"  ✗ 工具不存在\n"

                messages.append(ToolMessage(content=result_str, tool_call_id=tool_call["id"]))

        # 最终回答流式输出
        yield "\n[分析完成，生成报告]\n\n"
        messages.append(HumanMessage(content="请基于已收集的信息给出最终回答。"))
        async for chunk in llm.astream(messages):
            if chunk.content:
                yield chunk.content
