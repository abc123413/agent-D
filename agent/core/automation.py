"""
自动化流水线 - 将webhook事件与Agent技能串联

事件触发 → 克隆代码 → 执行技能(带工具调用) → 分析结果 → 反馈到PR
"""

import os
import shutil
import tempfile
import asyncio
from pathlib import Path

from .webhook import PREvent, TicketEvent, WebhookHandler
from .skill_loader import SkillLoader
from .executor import AgentExecutor
from .policy_engine import PolicyEngine
from .harness import HarnessEngine


class AutomationPipeline:
    """
    自动化流水线引擎。

    当webhook事件到来时：
    1. 克隆仓库到临时目录
    2. checkout到PR的source branch
    3. 用代码审核Agent执行审核（带tool calling）
    4. 根据结果自动向PR提交approve/request changes
    """

    def __init__(self, harness: HarnessEngine, executor: AgentExecutor, webhook_handler: WebhookHandler):
        self.harness = harness
        self.executor = executor
        self.webhook = webhook_handler
        self._running_tasks: dict[str, dict] = {}

    async def handle_pr_event(self, event: PREvent) -> dict:
        """处理PR事件的完整流程"""
        task_key = f"{event.repo_full_name}#{event.pr_number}"

        self._running_tasks[task_key] = {
            "status": "cloning",
            "event": event.model_dump(),
        }

        work_dir = None
        try:
            # 1. 克隆代码
            work_dir = tempfile.mkdtemp(prefix="agent_review_")
            self._running_tasks[task_key]["status"] = "cloning"

            clone_success = await self._clone_repo(event, work_dir)
            if not clone_success:
                return {"status": "error", "message": "仓库克隆失败"}

            # 2. 切换分支并获取diff
            await self._checkout_branch(event, work_dir)
            self._running_tasks[task_key]["status"] = "reviewing"

            # 3. 执行代码审核
            review_result = await self._run_review(event, work_dir)
            self._running_tasks[task_key]["status"] = "posting"

            # 4. 分析结果，决定通过/退回
            approve, comment = self._analyze_result(review_result, event)

            # 5. 提交审核结果到PR
            await self.webhook.post_review_comment(event, comment, approve)

            self._running_tasks[task_key]["status"] = "completed"
            self._running_tasks[task_key]["result"] = {
                "approved": approve,
                "comment_preview": comment[:200],
            }

            return {
                "status": "completed",
                "approved": approve,
                "pr_number": event.pr_number,
                "comment_preview": comment[:500],
            }

        except Exception as e:
            self._running_tasks[task_key]["status"] = "failed"
            self._running_tasks[task_key]["error"] = str(e)
            return {"status": "error", "message": str(e)}
        finally:
            if work_dir and os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)

    async def _clone_repo(self, event: PREvent, work_dir: str) -> bool:
        cmd = f"git clone --depth=50 --branch={event.source_branch} {event.clone_url} ."
        proc = await asyncio.create_subprocess_shell(
            cmd, cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        return proc.returncode == 0

    async def _checkout_branch(self, event: PREvent, work_dir: str):
        cmd = f"git fetch origin {event.target_branch} && git diff origin/{event.target_branch}...HEAD --stat"
        proc = await asyncio.create_subprocess_shell(
            cmd, cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)

    async def _run_review(self, event: PREvent, work_dir: str) -> str:
        """用代码审核技能执行审核"""
        skill = self.harness.skill_loader.get_skill("code_review")
        if not skill:
            return "错误：代码审核技能未加载"

        # 创建一个指向工作目录的executor
        review_executor = AgentExecutor(
            self.executor.model_config,
            workspace=work_dir,
        )

        prompt = f"""请审核这个Pull Request的代码变更：
- PR标题: {event.pr_title}
- 分支: {event.source_branch} → {event.target_branch}
- 作者: {event.author}

请使用 git_diff 工具获取代码变更，然后进行完整审核。
重点关注安全漏洞、代码质量和最佳实践。"""

        result = await review_executor.execute(skill, prompt)
        return result.output

    def _analyze_result(self, review_text: str, event: PREvent) -> tuple[bool, str]:
        """分析审核结果，决定通过或退回"""
        # 关键词判断
        critical_markers = ["critical", "严重", "安全漏洞", "SQL注入", "XSS", "不可合并", "禁止合并"]
        has_critical = any(m in review_text.lower() for m in critical_markers)

        if has_critical:
            comment = f"""## 🚫 代码审核未通过

**PR:** {event.pr_title}
**审核Agent自动审核结果：发现严重问题，请修复后重新提交。**

---

{review_text}

---
> 此审核由智能办公Agent平台自动执行。修复问题后重新push即可触发再次审核。
"""
            return False, comment
        else:
            comment = f"""## ✅ 代码审核通过

**PR:** {event.pr_title}
**审核Agent自动审核结果：代码质量良好，可以合并。**

---

{review_text}

---
> 此审核由智能办公Agent平台自动执行。
"""
            return True, comment

    def get_running_tasks(self) -> list[dict]:
        return [
            {"key": k, **v}
            for k, v in self._running_tasks.items()
        ]

    async def handle_ticket_event(self, event: TicketEvent) -> dict:
        """处理工单事件的完整流程"""
        task_key = f"ticket:{event.platform}:{event.ticket_id}"

        self._running_tasks[task_key] = {
            "status": "analyzing",
            "event": event.model_dump(),
        }

        try:
            # 1. 用客服Agent处理工单
            self._running_tasks[task_key]["status"] = "processing"
            result = await self._run_ticket_agent(event)
            self._running_tasks[task_key]["status"] = "replying"

            # 2. 解析Agent输出，提取回复内容
            reply_content, action = self._parse_ticket_result(result, event)

            # 3. 回复到工单系统
            if action != "escalate" and reply_content:
                await self.webhook.post_ticket_reply(event, reply_content)

            self._running_tasks[task_key]["status"] = "completed"
            self._running_tasks[task_key]["result"] = {
                "action": action,
                "reply_preview": reply_content[:200] if reply_content else "",
            }

            return {
                "status": "completed",
                "ticket_id": event.ticket_id,
                "action": action,
                "reply_preview": reply_content[:500] if reply_content else "",
                "full_analysis": result,
            }

        except Exception as e:
            self._running_tasks[task_key]["status"] = "failed"
            self._running_tasks[task_key]["error"] = str(e)
            return {"status": "error", "ticket_id": event.ticket_id, "message": str(e)}

    async def _run_ticket_agent(self, event: TicketEvent) -> str:
        """用客服技能处理工单"""
        skill = self.harness.skill_loader.get_skill("customer_service")
        if not skill:
            return "错误：客服技能未加载"

        prompt = f"""请处理以下工单：

工单ID: {event.ticket_id}
标题: {event.title}
内容: {event.description}
提交人: {event.author} ({event.author_email})
平台优先级: {event.priority}
提交时间: {event.created_at}

请按照规则进行分类、判定优先级、情绪检测，并生成回复。"""

        result = await self.executor.execute(skill, prompt)
        return result.output

    def _parse_ticket_result(self, result_text: str, event: TicketEvent) -> tuple[str, str]:
        """解析Agent输出，提取回复和动作"""
        import json

        # 尝试从Agent输出中提取JSON结果
        action = "auto_reply"
        reply_content = ""

        try:
            start = result_text.find("{")
            end = result_text.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(result_text[start:end])
                action = parsed.get("action", "auto_reply")
                reply_content = parsed.get("reply_content", "")
        except (json.JSONDecodeError, ValueError):
            pass

        if not reply_content:
            # 如果无法解析JSON，用整个输出作为分析，生成默认回复
            reply_content = f"""您好，感谢您的反馈！

我们已收到您的工单（编号：{event.ticket_id}）。
工程师正在处理中，预计24小时内给您回复。

如有紧急问题，请联系在线客服。"""

        # 检测是否需要升级
        escalate_markers = ["escalate", "人工", "升级", "must_escalate"]
        if any(m in result_text.lower() for m in escalate_markers):
            action = "escalate"

        return reply_content, action
