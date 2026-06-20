"""
Webhook处理器 - 接收Git平台的事件，自动触发技能执行

支持 GitHub / GitLab 的 Pull Request / Merge Request 事件。
代码审核等自动化技能通过webhook事件触发，无需人工对话。
"""

import hmac
import hashlib
import os
import json
import httpx
from typing import Optional
from pydantic import BaseModel


class PREvent(BaseModel):
    """标准化的PR事件"""
    platform: str  # github / gitlab
    action: str  # opened / synchronize / reopened
    pr_number: int
    pr_title: str
    pr_url: str
    repo_full_name: str
    source_branch: str
    target_branch: str
    author: str
    clone_url: str
    api_base: str = ""


class TicketEvent(BaseModel):
    """标准化的工单事件"""
    platform: str  # zendesk / jira / feishu
    ticket_id: str
    title: str
    description: str
    author: str
    author_email: str = ""
    priority: str = ""
    created_at: str = ""
    api_base: str = ""
    raw_payload: dict = {}


class WebhookHandler:
    def __init__(self):
        self.github_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.gitlab_token = os.getenv("GITLAB_TOKEN", "")

    def verify_github_signature(self, payload: bytes, signature: str) -> bool:
        if not self.github_secret:
            return True  # 未配置secret则跳过验证
        expected = "sha256=" + hmac.new(
            self.github_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_github_event(self, payload: dict) -> Optional[PREvent]:
        action = payload.get("action", "")
        if action not in ("opened", "synchronize", "reopened"):
            return None

        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})

        return PREvent(
            platform="github",
            action=action,
            pr_number=pr.get("number", 0),
            pr_title=pr.get("title", ""),
            pr_url=pr.get("html_url", ""),
            repo_full_name=repo.get("full_name", ""),
            source_branch=pr.get("head", {}).get("ref", ""),
            target_branch=pr.get("base", {}).get("ref", ""),
            author=pr.get("user", {}).get("login", ""),
            clone_url=repo.get("clone_url", ""),
            api_base=f"https://api.github.com/repos/{repo.get('full_name', '')}",
        )

    def parse_gitlab_event(self, payload: dict) -> Optional[PREvent]:
        attrs = payload.get("object_attributes", {})
        action = attrs.get("action", "")
        if action not in ("open", "update", "reopen"):
            return None

        project = payload.get("project", {})

        return PREvent(
            platform="gitlab",
            action=action,
            pr_number=attrs.get("iid", 0),
            pr_title=attrs.get("title", ""),
            pr_url=attrs.get("url", ""),
            repo_full_name=project.get("path_with_namespace", ""),
            source_branch=attrs.get("source_branch", ""),
            target_branch=attrs.get("target_branch", ""),
            author=attrs.get("author_id", ""),
            clone_url=project.get("git_http_url", ""),
            api_base=project.get("web_url", "").replace("http://", "https://") + "/api/v4",
        )

    async def post_review_comment(self, event: PREvent, comment: str, approve: bool):
        """向PR/MR发送审核评论"""
        if event.platform == "github":
            await self._github_review(event, comment, approve)
        elif event.platform == "gitlab":
            await self._gitlab_review(event, comment, approve)

    async def _github_review(self, event: PREvent, comment: str, approve: bool):
        if not self.github_token:
            print(f"[Webhook] GitHub Token未配置，跳过PR评论")
            return

        url = f"{event.api_base}/pulls/{event.pr_number}/reviews"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        body = {
            "body": comment,
            "event": "APPROVE" if approve else "REQUEST_CHANGES",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code in (200, 201):
                print(f"[Webhook] GitHub PR #{event.pr_number} 审核评论已提交 ({'APPROVE' if approve else 'REQUEST_CHANGES'})")
            else:
                print(f"[Webhook] GitHub API错误: {resp.status_code} {resp.text[:200]}")

    async def _gitlab_review(self, event: PREvent, comment: str, approve: bool):
        if not self.gitlab_token:
            print(f"[Webhook] GitLab Token未配置，跳过MR评论")
            return

        url = f"{event.api_base}/projects/{event.repo_full_name.replace('/', '%2F')}/merge_requests/{event.pr_number}/notes"
        headers = {"PRIVATE-TOKEN": self.gitlab_token}
        body = {"body": comment}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code in (200, 201):
                print(f"[Webhook] GitLab MR !{event.pr_number} 评论已提交")

            if not approve:
                # GitLab: 设置MR为draft来阻止合并
                mr_url = f"{event.api_base}/projects/{event.repo_full_name.replace('/', '%2F')}/merge_requests/{event.pr_number}"
                await client.put(mr_url, headers=headers, json={"title": f"Draft: {event.pr_title}"})

    # ---- 工单系统 ----

    def parse_zendesk_event(self, payload: dict) -> Optional[TicketEvent]:
        ticket = payload.get("ticket", {})
        if not ticket:
            return None
        requester = ticket.get("requester", {})
        return TicketEvent(
            platform="zendesk",
            ticket_id=str(ticket.get("id", "")),
            title=ticket.get("subject", ""),
            description=ticket.get("description", ""),
            author=requester.get("name", ""),
            author_email=requester.get("email", ""),
            priority=ticket.get("priority", "normal"),
            created_at=ticket.get("created_at", ""),
            api_base=os.getenv("ZENDESK_API_BASE", ""),
            raw_payload=payload,
        )

    def parse_jira_event(self, payload: dict) -> Optional[TicketEvent]:
        issue = payload.get("issue", {})
        fields = issue.get("fields", {})
        if not issue:
            return None
        reporter = fields.get("reporter", {})
        return TicketEvent(
            platform="jira",
            ticket_id=issue.get("key", ""),
            title=fields.get("summary", ""),
            description=fields.get("description", ""),
            author=reporter.get("displayName", ""),
            author_email=reporter.get("emailAddress", ""),
            priority=fields.get("priority", {}).get("name", "Medium"),
            created_at=fields.get("created", ""),
            api_base=os.getenv("JIRA_API_BASE", ""),
            raw_payload=payload,
        )

    def parse_feishu_event(self, payload: dict) -> Optional[TicketEvent]:
        event = payload.get("event", {})
        ticket = event.get("ticket", {})
        if not ticket:
            return None
        return TicketEvent(
            platform="feishu",
            ticket_id=ticket.get("ticket_id", ""),
            title=ticket.get("question", ""),
            description=ticket.get("question", ""),
            author=ticket.get("user_name", ""),
            created_at=ticket.get("create_time", ""),
            api_base="https://open.feishu.cn/open-apis",
            raw_payload=payload,
        )

    async def post_ticket_reply(self, event: TicketEvent, reply: str):
        """向工单系统回复"""
        if event.platform == "zendesk":
            await self._zendesk_reply(event, reply)
        elif event.platform == "jira":
            await self._jira_reply(event, reply)
        elif event.platform == "feishu":
            await self._feishu_reply(event, reply)

    async def _zendesk_reply(self, event: TicketEvent, reply: str):
        token = os.getenv("ZENDESK_TOKEN", "")
        if not token or not event.api_base:
            print(f"[Webhook] Zendesk配置缺失，跳过回复")
            return
        url = f"{event.api_base}/api/v2/tickets/{event.ticket_id}.json"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"ticket": {"comment": {"body": reply, "public": True}}}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(url, headers=headers, json=body)
            if resp.status_code in (200, 201):
                print(f"[Webhook] Zendesk #{event.ticket_id} 回复成功")
            else:
                print(f"[Webhook] Zendesk API错误: {resp.status_code}")

    async def _jira_reply(self, event: TicketEvent, reply: str):
        token = os.getenv("JIRA_TOKEN", "")
        if not token or not event.api_base:
            print(f"[Webhook] Jira配置缺失，跳过回复")
            return
        url = f"{event.api_base}/rest/api/3/issue/{event.ticket_id}/comment"
        headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        body = {"body": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": reply}]}]}}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code in (200, 201):
                print(f"[Webhook] Jira {event.ticket_id} 回复成功")
            else:
                print(f"[Webhook] Jira API错误: {resp.status_code}")

    async def _feishu_reply(self, event: TicketEvent, reply: str):
        token = os.getenv("FEISHU_TOKEN", "")
        if not token:
            print(f"[Webhook] 飞书配置缺失，跳过回复")
            return
        url = f"https://open.feishu.cn/open-apis/helpdesk/v1/tickets/{event.ticket_id}/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"msg_type": "text", "content": json.dumps({"text": reply})}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code == 0 or resp.status_code in (200, 201):
                print(f"[Webhook] 飞书工单 {event.ticket_id} 回复成功")
            else:
                print(f"[Webhook] 飞书API错误: {resp.status_code}")
