"""
Sub-Agent编排器 - 基于LangGraph实现多Agent协作

将复杂任务拆解为多个子任务，分发给不同技能Agent，
确保中间产物上下文隔离不污染主流程。
"""

from typing import Optional
from dataclasses import dataclass, field

from core.skill_loader import SkillLoader, SkillConfig
from core.executor import AgentExecutor
from core.policy_engine import PolicyEngine


@dataclass
class SubTask:
    skill_id: str
    input_text: str
    output: str = ""
    status: str = "pending"
    depends_on: list[str] = field(default_factory=list)


@dataclass
class OrchestrationPlan:
    task_description: str
    sub_tasks: list[SubTask] = field(default_factory=list)
    final_output: str = ""
    status: str = "pending"


class MultiAgentOrchestrator:
    """
    多Agent编排器。
    支持将一个复杂请求拆解为多个子Agent任务，
    按依赖关系顺序执行，最后聚合结果。

    示例：合同审核拆解为
      1. document_parse（解析合同文档）
      2. clause_extract（提取关键条款）
      3. risk_evaluate（风险评级）
      4. report_generate（生成报告）
    """

    def __init__(self, skill_loader: SkillLoader, executor: AgentExecutor, policy_engine: PolicyEngine):
        self.skill_loader = skill_loader
        self.executor = executor
        self.policy_engine = policy_engine

    async def execute_plan(self, plan: OrchestrationPlan) -> OrchestrationPlan:
        plan.status = "running"
        context_accumulator = []

        for sub_task in plan.sub_tasks:
            if sub_task.depends_on:
                dep_outputs = [
                    t.output for t in plan.sub_tasks
                    if t.skill_id in sub_task.depends_on and t.status == "completed"
                ]
                enriched_input = f"{sub_task.input_text}\n\n上下文参考:\n" + "\n---\n".join(dep_outputs)
            else:
                enriched_input = sub_task.input_text

            skill = self.skill_loader.get_skill(sub_task.skill_id)
            if not skill:
                sub_task.status = "failed"
                sub_task.output = f"技能不存在: {sub_task.skill_id}"
                continue

            violation = self.policy_engine.check(enriched_input, skill_id=sub_task.skill_id)
            if violation:
                sub_task.status = "blocked"
                sub_task.output = f"策略拦截: {violation.rule_name}"
                continue

            try:
                sub_task.status = "running"
                output = await self.executor.execute(skill, enriched_input)
                sub_task.output = output
                sub_task.status = "completed"
                context_accumulator.append(output)
            except Exception as e:
                sub_task.status = "failed"
                sub_task.output = str(e)

        completed = [t for t in plan.sub_tasks if t.status == "completed"]
        if completed:
            plan.final_output = completed[-1].output
            plan.status = "completed"
        else:
            plan.status = "failed"
            plan.final_output = "所有子任务均未成功完成"

        return plan

    def create_contract_review_plan(self, contract_text: str) -> OrchestrationPlan:
        """预置编排方案：合同审核全流程"""
        return OrchestrationPlan(
            task_description="合同审核全流程",
            sub_tasks=[
                SubTask(skill_id="contract_review", input_text=f"请解析以下合同的基本信息和关键条款:\n{contract_text}"),
                SubTask(skill_id="information_retrieval", input_text="查询相关法规对违约金比例和合同终止的规定", depends_on=["contract_review"]),
                SubTask(skill_id="contract_review", input_text=f"综合以上分析，生成完整审核报告:\n{contract_text}", depends_on=["information_retrieval"]),
            ],
        )
