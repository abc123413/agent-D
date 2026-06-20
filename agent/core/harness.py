"""
Harness引擎 - 基于01_Harness引擎提示词.yaml的调度核心

职责：
- 理解用户意图，路由到对应技能
- 管理任务生命周期
- 协调策略引擎进行安全校验
- 支持多技能协作编排
"""

import time
import uuid
from typing import Optional

import yaml
from pydantic import BaseModel
from pathlib import Path

from .skill_loader import SkillLoader, SkillConfig
from .policy_engine import PolicyEngine


class TaskState(BaseModel):
    task_id: str
    skill_name: str
    status: str = "pending"  # pending | running | completed | failed | blocked | approval_required
    input_text: str = ""
    output_text: str = ""
    created_at: float = 0
    completed_at: float = 0
    error: str = ""
    metadata: dict = {}
    trace: list[dict] = []
    prompt_tokens: int = 0
    completion_tokens: int = 0


class HarnessEngine:
    def __init__(self, config_dir: str, skill_loader: SkillLoader, policy_engine: PolicyEngine):
        self.config_dir = Path(config_dir)
        self.skill_loader = skill_loader
        self.policy_engine = policy_engine
        self._tasks: dict[str, TaskState] = {}
        self._harness_prompt: str = ""
        self._routing_rules: dict[str, list[str]] = {}
        self._load_config()

    def _load_config(self):
        harness_file = self.config_dir / "01_Harness引擎提示词.yaml"
        if harness_file.exists():
            with open(harness_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._harness_prompt = data.get("prompt", "")

        self._routing_rules = {
            "resume_screening": ["简历", "候选人", "招聘", "面试", "JD", "岗位匹配", "筛选简历"],
            "contract_review": ["合同", "条款", "签约", "法务", "违约", "审核合同", "法律"],
            "schedule_management": ["日程", "会议", "安排", "提醒", "日历", "时间"],
            "code_review": ["代码", "审核代码", "review", "PR", "commit", "diff", "代码审查", "code"],
            "customer_service": ["工单", "客服", "投诉", "反馈", "售后", "退款", "用户问题", "ticket"],
            "info_retrieval": ["查询", "搜索", "制度", "规定", "流程", "报销", "查找", "总结"],
        }

    def route_request(self, user_input: str, skill_name: Optional[str] = None) -> str:
        if skill_name:
            return skill_name

        for sid, keywords in self._routing_rules.items():
            if any(kw in user_input for kw in keywords):
                return sid

        return "info_retrieval"

    def create_task(self, user_input: str, skill_name: str) -> TaskState:
        task = TaskState(
            task_id=str(uuid.uuid4())[:8],
            skill_name=skill_name,
            status="pending",
            input_text=user_input,
            created_at=time.time(),
        )
        self._tasks[task.task_id] = task
        return task

    def pre_check(self, task: TaskState) -> Optional[str]:
        violation = self.policy_engine.check_input(task.input_text, skill_name=task.skill_name)
        if violation:
            task.status = "blocked"
            task.error = f"策略拦截: {violation.rule_name} - {violation.content}"
            return task.error

        if self.policy_engine.requires_approval(task.skill_name):
            task.status = "approval_required"
            task.metadata["needs_approval"] = True

        return None

    def post_check(self, task: TaskState) -> Optional[str]:
        violation = self.policy_engine.check_output(task.output_text, skill_name=task.skill_name)
        if violation:
            task.status = "blocked"
            task.error = f"输出拦截: {violation.rule_name} - {violation.content}"
            return task.error

        task.output_text = self.policy_engine.mask_sensitive(task.output_text)
        return None

    def complete_task(self, task: TaskState, output: str, trace: list[dict] = [], prompt_tokens: int = 0, completion_tokens: int = 0):
        task.output_text = output
        task.completed_at = time.time()
        task.status = "completed"
        task.trace = trace
        task.prompt_tokens = prompt_tokens
        task.completion_tokens = completion_tokens

    def fail_task(self, task: TaskState, error: str):
        task.error = error
        task.status = "failed"
        task.completed_at = time.time()

    def get_task(self, task_id: str) -> Optional[TaskState]:
        return self._tasks.get(task_id)

    def get_pending_approvals(self) -> list[dict]:
        tasks = [t for t in self._tasks.values() if t.status == "approval_required"]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return [t.model_dump() for t in tasks]

    def approve_task(self, task_id: str) -> Optional[TaskState]:
        task = self._tasks.get(task_id)
        if not task or task.status != "approval_required":
            return None
        task.status = "pending"
        task.metadata.pop("needs_approval", None)
        return task

    def reject_task(self, task_id: str, reason: str = "") -> Optional[TaskState]:
        task = self._tasks.get(task_id)
        if not task or task.status != "approval_required":
            return None
        task.status = "rejected"
        task.error = reason or "人工拒绝"
        task.completed_at = time.time()
        return task

    def get_recent_tasks(self, limit: int = 20) -> list[dict]:
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)[:limit]
        return [t.model_dump() for t in tasks]

    def get_harness_prompt(self) -> str:
        skills_info = "\n".join(
            f"- {s.name}: {s.display_name} - {s.description}"
            for s in self.skill_loader.get_enabled_skills()
        )
        return self._harness_prompt.replace("{available_skills}", skills_info)
