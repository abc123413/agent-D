"""
智能办公Agent平台 - FastAPI主入口

基于Harness架构的安全隔离型智能办公平台。
技能通过YAML配置驱动，新增能力无需修改代码。
"""

import os
import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yaml
from dotenv import load_dotenv

load_dotenv()

from core.skill_loader import SkillLoader
from core.policy_engine import PolicyEngine
from core.harness import HarnessEngine
from core.executor import AgentExecutor
from core.webhook import WebhookHandler
from core.automation import AutomationPipeline
from core.scheduler import Scheduler
from core.alerting import AlertManager


BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"

skill_loader: SkillLoader = None
policy_engine: PolicyEngine = None
harness: HarnessEngine = None
executor: AgentExecutor = None
webhook_handler: WebhookHandler = None
automation: AutomationPipeline = None
scheduler: Scheduler = None
alert_manager: AlertManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global skill_loader, policy_engine, harness, executor, webhook_handler, automation, scheduler, alert_manager

    skill_loader = SkillLoader(str(CONFIG_DIR))
    policy_engine = PolicyEngine(str(CONFIG_DIR))

    harness = HarnessEngine(str(CONFIG_DIR), skill_loader, policy_engine)

    global_file = CONFIG_DIR / "00_全局配置.yaml"
    model_config = {}
    if global_file.exists():
        with open(global_file, "r", encoding="utf-8") as f:
            global_cfg = yaml.safe_load(f) or {}
            model_config = global_cfg.get("harness", {}).get("model", {})

    executor = AgentExecutor(model_config, workspace=str(BASE_DIR))

    webhook_handler = WebhookHandler()
    automation = AutomationPipeline(harness, executor, webhook_handler)

    scheduler = Scheduler(BASE_DIR / "data")
    scheduler.set_dependencies(harness, executor, skill_loader)
    scheduler.start()

    alert_manager = AlertManager(BASE_DIR / "data")

    skills = skill_loader.get_enabled_skills()
    print(f"[Agent平台] 启动完成")
    print(f"  - 已加载技能: {len(skills)} 个")
    for s in skills:
        print(f"    * {s.display_name} ({s.name}) v{s.version}")
    print(f"  - 策略引擎: 已启用")
    print(f"  - Harness引擎: 已就绪")
    print(f"  - Webhook自动化: 已就绪")
    print(f"  - 定时调度器: 已启动")
    yield


app = FastAPI(title="智能办公Agent平台", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- 认证API ----

from core.auth import (
    LoginRequest, register_user, authenticate_user,
    create_token, get_current_user, User,
)
from fastapi import Depends


@app.post("/api/auth/register")
def auth_register(req: LoginRequest):
    user = register_user(req.username, req.password)
    token = create_token(user)
    return {"token": token, "user": {"id": user.id, "username": user.username}}


@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    token = create_token(user)
    return {"token": token, "user": {"id": user.id, "username": user.username}}


@app.get("/api/auth/me")
def auth_me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username}


# ---- 审批API ----

class RejectRequest(BaseModel):
    reason: str = ""


@app.get("/api/approvals")
def get_approvals():
    """获取所有待审批任务"""
    return harness.get_pending_approvals()


@app.post("/api/approvals/{task_id}/approve")
async def approve_task(task_id: str):
    """批准任务并继续执行"""
    task = harness.approve_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在或不在待审批状态")

    skill = skill_loader.get_skill(task.skill_name)
    if not skill:
        harness.fail_task(task, "技能不存在")
        return {"task_id": task_id, "status": "failed", "error": "技能不存在"}

    try:
        task.status = "running"
        result = await executor.execute(skill, task.input_text)
        trace_dicts = [{"step_type": s.step_type, "name": s.name, "input": s.input, "output": s.output, "start_time": s.start_time, "end_time": s.end_time, "tokens": s.tokens} for s in result.trace]
        harness.complete_task(task, result.output, trace_dicts, result.prompt_tokens, result.completion_tokens)
        return {"task_id": task_id, "status": "completed", "output": result.output[:200]}
    except Exception as e:
        harness.fail_task(task, str(e))
        return {"task_id": task_id, "status": "failed", "error": str(e)}


@app.post("/api/approvals/{task_id}/reject")
def reject_task(task_id: str, req: RejectRequest):
    """拒绝任务"""
    task = harness.reject_task(task_id, req.reason)
    if not task:
        raise HTTPException(404, "任务不存在或不在待审批状态")
    return {"task_id": task_id, "status": "rejected", "reason": req.reason}


# ---- 数据模型 ----

class ChatRequest(BaseModel):
    message: str
    skill_id: str | None = None
    history: list[dict] = []


class ChatResponse(BaseModel):
    task_id: str
    skill_id: str
    skill_name: str
    response: str
    status: str
    requires_approval: bool = False


class ConfigUpdate(BaseModel):
    content: str


# ---- 对话API ----

@app.post("/api/chat")
async def chat(req: ChatRequest):
    routed_skill = harness.route_request(req.message, req.skill_id)
    skill = skill_loader.get_skill(routed_skill)
    if not skill:
        raise HTTPException(400, f"技能不存在: {routed_skill}")
    if not skill.enabled:
        raise HTTPException(400, f"技能已禁用: {skill.display_name}")

    task = harness.create_task(req.message, routed_skill)

    block_msg = harness.pre_check(task)
    if block_msg:
        return ChatResponse(
            task_id=task.task_id,
            skill_id=routed_skill,
            skill_name=skill.display_name,
            response=f"[策略拦截] {block_msg}",
            status="blocked",
        )

    if task.status == "approval_required":
        return ChatResponse(
            task_id=task.task_id,
            skill_id=routed_skill,
            skill_name=skill.display_name,
            response=f"[需要审批] {skill.display_name}需要人工确认后执行",
            status="approval_required",
            requires_approval=True,
        )

    try:
        task.status = "running"
        result = await executor.execute(skill, req.message, req.history)

        task.output_text = result.output
        post_block = harness.post_check(task)
        if post_block:
            return ChatResponse(
                task_id=task.task_id,
                skill_id=routed_skill,
                skill_name=skill.display_name,
                response=f"[输出拦截] {post_block}",
                status="blocked",
            )

        trace_dicts = [{"step_type": s.step_type, "name": s.name, "input": s.input, "output": s.output, "start_time": s.start_time, "end_time": s.end_time, "tokens": s.tokens} for s in result.trace]
        harness.complete_task(task, task.output_text, trace_dicts, result.prompt_tokens, result.completion_tokens)
        return ChatResponse(
            task_id=task.task_id,
            skill_id=routed_skill,
            skill_name=skill.display_name,
            response=task.output_text,
            status="completed",
        )
    except Exception as e:
        harness.fail_task(task, str(e))
        return ChatResponse(
            task_id=task.task_id,
            skill_id=routed_skill,
            skill_name=skill.display_name,
            response=f"[执行错误] {str(e)}",
            status="failed",
        )


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            skill_id = data.get("skill_id")
            history = data.get("history", [])

            routed_skill = harness.route_request(message, skill_id)
            skill = skill_loader.get_skill(routed_skill)
            if not skill or not skill.enabled:
                await websocket.send_json({"type": "error", "content": f"技能不可用: {routed_skill}"})
                continue

            task = harness.create_task(message, routed_skill)
            block_msg = harness.pre_check(task)
            if block_msg:
                await websocket.send_json({"type": "blocked", "content": block_msg})
                continue

            if task.status == "approval_required":
                await websocket.send_json({
                    "type": "approval_required",
                    "content": f"{skill.display_name}需要人工确认后执行",
                    "task_id": task.task_id,
                })
                continue

            task.status = "running"
            await websocket.send_json({"type": "start", "skill": skill.display_name, "task_id": task.task_id})

            try:
                full_response = ""
                async for chunk in executor.execute_stream(skill, message, history):
                    full_response += chunk
                    await websocket.send_json({"type": "chunk", "content": chunk})

                task.output_text = full_response
                post_block = harness.post_check(task)
                if post_block:
                    await websocket.send_json({"type": "blocked", "content": post_block})
                else:
                    harness.complete_task(task, task.output_text)
                    await websocket.send_json({"type": "done", "task_id": task.task_id})
            except Exception as e:
                harness.fail_task(task, str(e))
                await websocket.send_json({"type": "error", "content": str(e)})

    except WebSocketDisconnect:
        pass


# ---- 技能管理API ----

@app.get("/api/skills")
def list_skills():
    return skill_loader.list_skills()


@app.get("/api/skills/{skill_name}")
def get_skill(skill_name: str):
    skill = skill_loader.get_skill(skill_name)
    if not skill:
        raise HTTPException(404, "Skill not found")
    return skill.model_dump()


@app.post("/api/skills/{skill_name}/reload")
def reload_skill(skill_name: str):
    ok = skill_loader.reload_skill(skill_name)
    return {"success": ok}


@app.post("/api/skills/reload-all")
def reload_all_skills():
    skill_loader.load_all()
    return {"loaded": len(skill_loader.get_enabled_skills())}


# ---- 策略引擎API ----

@app.get("/api/policy/rules")
def get_policy_rules():
    return policy_engine.get_rules_summary()


@app.post("/api/policy/reload")
def reload_policy():
    policy_engine.load_rules()
    return {"success": True}


@app.get("/api/policy/violations")
def get_violations():
    return policy_engine.get_violations()


# ---- 配置管理API ----

@app.get("/api/config")
def list_config_files():
    files = []
    for f in sorted(CONFIG_DIR.iterdir()):
        if f.suffix == ".yaml" and f.is_file():
            files.append({"filename": f.name, "title": f.stem})
    return files


@app.get("/api/config/{filename}")
def get_config(filename: str):
    filepath = CONFIG_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, "Config not found")
    return {"filename": filename, "content": filepath.read_text(encoding="utf-8")}


@app.put("/api/config/{filename}")
def update_config(filename: str, body: ConfigUpdate):
    filepath = CONFIG_DIR / filename
    try:
        yaml.safe_load(body.content)
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML: {e}")
    filepath.write_text(body.content, encoding="utf-8")
    return {"success": True}


# ---- 任务/仪表盘API ----

@app.get("/api/tasks")
def get_tasks():
    return harness.get_recent_tasks()


@app.get("/api/tasks/{task_id}/trace")
def get_task_trace(task_id: str):
    """获取任务执行链路"""
    task = harness.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return {
        "task_id": task.task_id,
        "skill_name": task.skill_name,
        "status": task.status,
        "trace": task.trace,
        "prompt_tokens": task.prompt_tokens,
        "completion_tokens": task.completion_tokens,
        "duration": round(task.completed_at - task.created_at, 2) if task.completed_at else 0,
    }


@app.get("/api/dashboard/stats")
def get_stats():
    skills = skill_loader.list_skills()
    all_tasks = harness.get_recent_tasks(1000)
    today_start = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
    today_tasks = [t for t in all_tasks if t["created_at"] >= today_start]
    running_tasks = [t for t in all_tasks if t["status"] == "running"]
    return {
        "activeAgents": len(running_tasks),
        "totalSkills": len(skills),
        "enabledSkills": len([s for s in skills if s["enabled"]]),
        "todayChats": len(today_tasks),
        "completedToday": len([t for t in today_tasks if t["status"] == "completed"]),
        "failedToday": len([t for t in today_tasks if t["status"] == "failed"]),
        "blockedToday": len([t for t in today_tasks if t["status"] == "blocked"]),
        "violations": len(policy_engine.get_violations()),
    }


@app.get("/api/dashboard/recent-activity")
def get_recent_activity():
    tasks = harness.get_recent_tasks(20)
    violations = policy_engine.get_violations(10)
    activities = []
    for t in tasks:
        ts = time.strftime("%H:%M:%S", time.localtime(t["created_at"]))
        skill = skill_loader.get_skill(t["skill_name"])
        skill_name = skill.display_name if skill else t["skill_name"]
        if t["status"] == "completed":
            activities.append({"time": ts, "content": f"{skill_name}完成任务", "color": "green", "type": "task"})
        elif t["status"] == "blocked":
            activities.append({"time": ts, "content": f"{skill_name}被策略拦截: {t.get('error', '')}", "color": "red", "type": "block"})
        elif t["status"] == "failed":
            activities.append({"time": ts, "content": f"{skill_name}执行失败", "color": "orange", "type": "error"})
        elif t["status"] == "running":
            activities.append({"time": ts, "content": f"{skill_name}处理中...", "color": "blue", "type": "running"})
        elif t["status"] == "approval_required":
            activities.append({"time": ts, "content": f"{skill_name}等待人工审批", "color": "gold", "type": "approval"})
    for v in violations:
        ts = time.strftime("%H:%M:%S", time.localtime(v["timestamp"]))
        activities.append({"time": ts, "content": f"策略拦截: {v['rule_name']}", "color": "red", "type": "violation"})
    activities.sort(key=lambda x: x["time"], reverse=True)
    return activities[:20]


# ---- Webhook自动化API ----

@app.post("/api/webhook/github")
async def github_webhook(request: Request):
    """接收GitHub PR事件，自动触发代码审核"""
    body = await request.body()
    payload = await request.json()

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not webhook_handler.verify_github_signature(body, signature):
        raise HTTPException(403, "Invalid signature")

    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "pull_request":
        return {"status": "ignored", "reason": f"event type: {event_type}"}

    pr_event = webhook_handler.parse_github_event(payload)
    if not pr_event:
        return {"status": "ignored", "reason": "不相关的PR action"}

    import asyncio
    asyncio.create_task(automation.handle_pr_event(pr_event))
    return {"status": "accepted", "pr": pr_event.pr_number, "message": "代码审核已触发"}


@app.post("/api/webhook/gitlab")
async def gitlab_webhook(request: Request):
    """接收GitLab MR事件，自动触发代码审核"""
    payload = await request.json()

    token = request.headers.get("X-Gitlab-Token", "")
    expected = os.getenv("GITLAB_WEBHOOK_SECRET", "")
    if expected and token != expected:
        raise HTTPException(403, "Invalid token")

    pr_event = webhook_handler.parse_gitlab_event(payload)
    if not pr_event:
        return {"status": "ignored", "reason": "不相关的MR action"}

    import asyncio
    asyncio.create_task(automation.handle_pr_event(pr_event))
    return {"status": "accepted", "mr": pr_event.pr_number, "message": "代码审核已触发"}


@app.post("/api/webhook/test")
async def test_webhook():
    """手动触发测试：模拟一个PR事件进行代码审核"""
    from core.webhook import PREvent
    test_event = PREvent(
        platform="test",
        action="opened",
        pr_number=1,
        pr_title="Test PR",
        pr_url="http://localhost",
        repo_full_name="test/repo",
        source_branch="feature",
        target_branch="main",
        author="developer",
        clone_url="",
    )
    result = await automation.handle_pr_event(test_event)
    return result


@app.post("/api/webhook/zendesk")
async def zendesk_webhook(request: Request):
    """接收Zendesk工单事件，自动触发客服Agent"""
    payload = await request.json()
    ticket_event = webhook_handler.parse_zendesk_event(payload)
    if not ticket_event:
        return {"status": "ignored", "reason": "无法解析工单"}

    import asyncio
    asyncio.create_task(automation.handle_ticket_event(ticket_event))
    return {"status": "accepted", "ticket_id": ticket_event.ticket_id, "message": "客服Agent已触发"}


@app.post("/api/webhook/jira-service")
async def jira_service_webhook(request: Request):
    """接收Jira Service Management工单事件"""
    payload = await request.json()
    event_type = payload.get("webhookEvent", "")
    if "issue_created" not in event_type and "issue_updated" not in event_type:
        return {"status": "ignored", "reason": f"event: {event_type}"}

    ticket_event = webhook_handler.parse_jira_event(payload)
    if not ticket_event:
        return {"status": "ignored", "reason": "无法解析工单"}

    import asyncio
    asyncio.create_task(automation.handle_ticket_event(ticket_event))
    return {"status": "accepted", "ticket_id": ticket_event.ticket_id, "message": "客服Agent已触发"}


@app.post("/api/webhook/feishu-helpdesk")
async def feishu_helpdesk_webhook(request: Request):
    """接收飞书服务台工单事件"""
    payload = await request.json()

    # 飞书验证请求
    if "challenge" in payload:
        return {"challenge": payload["challenge"]}

    ticket_event = webhook_handler.parse_feishu_event(payload)
    if not ticket_event:
        return {"status": "ignored", "reason": "无法解析工单"}

    import asyncio
    asyncio.create_task(automation.handle_ticket_event(ticket_event))
    return {"status": "accepted", "ticket_id": ticket_event.ticket_id, "message": "客服Agent已触发"}


@app.post("/api/webhook/ticket-test")
async def test_ticket_webhook():
    """手动测试：模拟一个工单事件触发客服Agent"""
    from core.webhook import TicketEvent
    test_event = TicketEvent(
        platform="test",
        ticket_id="TEST-001",
        title="无法登录系统",
        description="你好，我今天早上开始就无法登录系统了，输入密码后一直提示认证失败，但我确认密码没有改过。请尽快帮我处理，急用！",
        author="张三",
        author_email="zhangsan@example.com",
        priority="high",
        created_at="2026-03-15T09:30:00Z",
    )
    result = await automation.handle_ticket_event(test_event)
    return result


@app.get("/api/webhook/tasks")
def get_webhook_tasks():
    """获取当前运行中的自动化任务"""
    return automation.get_running_tasks()


# ---- Harness信息API ----

@app.get("/api/harness/prompt")
def get_harness_prompt():
    return {"prompt": harness.get_harness_prompt()}


# ---- 工具列表API ----

@app.get("/api/tools")
def list_tools():
    return executor.tool_registry.list_all()


@app.get("/api/skills/{skill_name}/tools")
def get_skill_tools(skill_name: str):
    skill = skill_loader.get_skill(skill_name)
    if not skill:
        raise HTTPException(404, "Skill not found")
    tool_names = skill.metadata.get("tools", [])
    if isinstance(tool_names, list):
        names = [t if isinstance(t, str) else t.get("name", "") for t in tool_names]
    else:
        names = []
    available = executor.tool_registry.get_tools_for_skill(names)
    return [{"name": t.name, "description": t.description} for t in available]


# ---- Agent创建/管理API ----

class AgentCreateRequest(BaseModel):
    name: str
    display_name: str
    agent_type: str
    description: str = ""
    version: str = "1.0.0"
    tools: list[str] = []
    webhook_config: dict = {}
    rules_config: dict = {}


@app.post("/api/agents/create")
def create_agent(req: AgentCreateRequest):
    """通过表单创建新Agent，生成YAML写入文件系统"""
    import secrets as sec

    skill_dir = CONFIG_DIR / "skills" / req.name
    if skill_dir.exists():
        raise HTTPException(400, f"Agent '{req.name}' 已存在")

    skill_dir.mkdir(parents=True, exist_ok=True)

    # 生成webhook secret
    webhook_secret = req.webhook_config.get("secret") or sec.token_hex(16)

    # 构建YAML内容
    yaml_data = {
        "name": req.name,
        "display_name": req.display_name,
        "version": req.version,
        "description": req.description,
        "enabled": True,
        "metadata": {
            "author": "user",
            "category": req.agent_type,
            "tags": [req.agent_type],
        },
        "tools": req.tools,
        "security": {
            "permissions": ["read", "analyze"],
            "blocked_permissions": ["delete"],
            "requires_approval": False,
        },
    }

    # 根据类型添加特定配置
    if req.agent_type == "code_review":
        yaml_data["review_rules"] = _build_code_review_rules(req.rules_config)
        yaml_data["prompt"] = _get_code_review_prompt()
    elif req.agent_type == "customer_service":
        yaml_data["service_rules"] = _build_customer_service_rules(req.rules_config)
        yaml_data["prompt"] = _get_customer_service_prompt()
    elif req.agent_type == "resume_screening":
        yaml_data["screening_rules"] = _build_resume_rules(req.rules_config)
        yaml_data["prompt"] = _get_resume_prompt()
    else:
        yaml_data["prompt"] = f"你是{req.display_name}Agent。根据用户输入执行任务，使用可用工具完成操作。"

    # 写入YAML
    skill_file = skill_dir / "Skill.yaml"
    with open(skill_file, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 热重载
    skill_loader.load_all()

    # 构建部署信息
    host = os.getenv("DEPLOY_HOST", "http://localhost:4000")
    deploy_info = _get_deploy_info(req.name, req.agent_type, host, webhook_secret)

    return {
        "success": True,
        "agent_name": req.name,
        "webhook_secret": webhook_secret,
        "deploy_info": deploy_info,
    }


@app.delete("/api/skills/{skill_name}")
def delete_skill(skill_name: str):
    """删除Agent"""
    import shutil
    skill_dir = CONFIG_DIR / "skills" / skill_name
    if not skill_dir.exists():
        raise HTTPException(404, "Agent not found")
    shutil.rmtree(skill_dir)
    skill_loader.load_all()
    return {"success": True, "deleted": skill_name}


@app.get("/api/stats/overview")
def get_stats_overview():
    """总览统计"""
    all_tasks = harness.get_recent_tasks(1000)
    total = len(all_tasks)
    completed = len([t for t in all_tasks if t["status"] == "completed"])
    failed = len([t for t in all_tasks if t["status"] == "failed"])
    blocked = len([t for t in all_tasks if t["status"] == "blocked"])

    avg_duration = 0
    durations = []
    for t in all_tasks:
        if t.get("completed_at") and t.get("created_at") and t["completed_at"] > 0:
            durations.append(t["completed_at"] - t["created_at"])
    if durations:
        avg_duration = round(sum(durations) / len(durations), 2)

    success_rate = round((completed / total * 100), 1) if total > 0 else 100

    # 按Agent分组统计
    by_agent = {}
    total_prompt_tokens = 0
    total_completion_tokens = 0
    for t in all_tasks:
        name = t.get("skill_name", "unknown")
        by_agent[name] = by_agent.get(name, 0) + 1
        total_prompt_tokens += t.get("prompt_tokens", 0)
        total_completion_tokens += t.get("completion_tokens", 0)

    total_tokens = total_prompt_tokens + total_completion_tokens
    estimated_cost = round(total_prompt_tokens / 1000 * 0.003 + total_completion_tokens / 1000 * 0.006, 4)

    return {
        "total_executions": total,
        "completed": completed,
        "failed": failed,
        "blocked": blocked,
        "success_rate": success_rate,
        "avg_duration_seconds": avg_duration,
        "by_agent": by_agent,
        "total_tokens": total_tokens,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "estimated_cost": estimated_cost,
    }


@app.get("/api/stats/trend")
def get_stats_trend(time_range: str = Query("7d", alias="range")):
    """按时间聚合的执行趋势数据"""
    all_tasks = harness.get_recent_tasks(1000)
    now = time.time()

    if time_range == "24h":
        bucket_seconds = 3600
        total_seconds = 86400
    elif time_range == "30d":
        bucket_seconds = 86400
        total_seconds = 86400 * 30
    else:
        bucket_seconds = 86400
        total_seconds = 86400 * 7

    cutoff = now - total_seconds
    filtered = [t for t in all_tasks if t.get("created_at", 0) >= cutoff]

    # 生成时间桶
    buckets: dict[str, dict] = {}
    num_buckets = int(total_seconds / bucket_seconds)
    for i in range(num_buckets):
        bucket_start = now - (num_buckets - i) * bucket_seconds
        if time_range == "24h":
            label = time.strftime("%H:00", time.localtime(bucket_start))
        else:
            label = time.strftime("%m-%d", time.localtime(bucket_start))
        buckets[label] = {"total": 0, "failed": 0}

    # 填入数据
    for t in filtered:
        task_time = t.get("created_at", 0)
        bucket_idx = int((task_time - cutoff) / bucket_seconds)
        bucket_idx = min(bucket_idx, num_buckets - 1)
        bucket_start = now - (num_buckets - bucket_idx) * bucket_seconds
        if time_range == "24h":
            label = time.strftime("%H:00", time.localtime(bucket_start))
        else:
            label = time.strftime("%m-%d", time.localtime(bucket_start))
        if label in buckets:
            buckets[label]["total"] += 1
            if t.get("status") in ("failed", "blocked"):
                buckets[label]["failed"] += 1

    # 响应时间分布
    duration_ranges = {"0-1s": 0, "1-3s": 0, "3-5s": 0, "5-10s": 0, "10s+": 0}
    for t in all_tasks:
        if t.get("completed_at") and t.get("created_at") and t["completed_at"] > 0:
            d = t["completed_at"] - t["created_at"]
            if d <= 1:
                duration_ranges["0-1s"] += 1
            elif d <= 3:
                duration_ranges["1-3s"] += 1
            elif d <= 5:
                duration_ranges["3-5s"] += 1
            elif d <= 10:
                duration_ranges["5-10s"] += 1
            else:
                duration_ranges["10s+"] += 1

    trend = [{"date": k, "count": v["total"], "failed": v["failed"]} for k, v in buckets.items()]
    error_trend = []
    for k, v in buckets.items():
        rate = round(v["failed"] / v["total"] * 100, 1) if v["total"] > 0 else 0
        error_trend.append({"date": k, "rate": rate})

    response_dist = [{"range": k, "count": v} for k, v in duration_ranges.items()]

    return {
        "trend": trend,
        "error_trend": error_trend,
        "response_distribution": response_dist,
    }


@app.get("/api/stats/token-usage")
def get_token_usage(time_range: str = Query("7d", alias="range")):
    """按时间聚合的Token用量趋势"""
    all_tasks = harness.get_recent_tasks(1000)
    now = time.time()

    if time_range == "24h":
        bucket_seconds = 3600
        total_seconds = 86400
    elif time_range == "30d":
        bucket_seconds = 86400
        total_seconds = 86400 * 30
    else:
        bucket_seconds = 86400
        total_seconds = 86400 * 7

    cutoff = now - total_seconds
    filtered = [t for t in all_tasks if t.get("created_at", 0) >= cutoff]

    num_buckets = int(total_seconds / bucket_seconds)
    buckets: dict[str, dict] = {}
    for i in range(num_buckets):
        bucket_start = now - (num_buckets - i) * bucket_seconds
        if time_range == "24h":
            label = time.strftime("%H:00", time.localtime(bucket_start))
        else:
            label = time.strftime("%m-%d", time.localtime(bucket_start))
        buckets[label] = {"prompt": 0, "completion": 0}

    for t in filtered:
        task_time = t.get("created_at", 0)
        bucket_idx = int((task_time - cutoff) / bucket_seconds)
        bucket_idx = min(bucket_idx, num_buckets - 1)
        bucket_start = now - (num_buckets - bucket_idx) * bucket_seconds
        if time_range == "24h":
            label = time.strftime("%H:00", time.localtime(bucket_start))
        else:
            label = time.strftime("%m-%d", time.localtime(bucket_start))
        if label in buckets:
            buckets[label]["prompt"] += t.get("prompt_tokens", 0)
            buckets[label]["completion"] += t.get("completion_tokens", 0)

    token_trend = [{"date": k, "prompt_tokens": v["prompt"], "completion_tokens": v["completion"]} for k, v in buckets.items()]
    return {"token_trend": token_trend}


@app.get("/api/agents/{agent_name}/activity")
def get_agent_activity(agent_name: str):
    """获取单个Agent的活动日志"""
    all_tasks = harness.get_recent_tasks(1000)
    agent_tasks = [t for t in all_tasks if t.get("skill_name") == agent_name]
    return agent_tasks[:50]


@app.get("/api/agents/{agent_name}/deploy-info")
def get_agent_deploy_info(agent_name: str):
    """获取Agent部署信息"""
    skill = skill_loader.get_skill(agent_name)
    if not skill:
        raise HTTPException(404, "Agent not found")

    host = os.getenv("DEPLOY_HOST", "http://localhost:4000")
    # 通过名称或metadata推断类型
    agent_type = agent_name
    if "review" in agent_name or "code" in agent_name:
        agent_type = "code_review"
    elif "customer" in agent_name or "service" in agent_name:
        agent_type = "customer_service"
    deploy_info = _get_deploy_info(agent_name, agent_type, host, "")

    return {
        "agent_name": agent_name,
        "display_name": skill.display_name,
        "type": agent_type,
        "tools": skill.metadata.get("tools", []),
        "deploy_info": deploy_info,
    }


# ---- Agent沙盒测试API ----

class TestRequest(BaseModel):
    input_text: str


@app.post("/api/agents/{agent_name}/test")
async def test_agent(agent_name: str, req: TestRequest):
    """沙盒测试Agent，不计入正式统计"""
    skill = skill_loader.get_skill(agent_name)
    if not skill:
        raise HTTPException(404, "Agent not found")

    start_time = time.time()
    try:
        result = await executor.execute(skill, req.input_text)
        duration = round(time.time() - start_time, 2)
        trace_dicts = [{"step_type": s.step_type, "name": s.name, "input": s.input, "output": s.output, "start_time": s.start_time, "end_time": s.end_time, "tokens": s.tokens} for s in result.trace]
        return {
            "status": "completed",
            "output": result.output,
            "trace": trace_dicts,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "duration": duration,
        }
    except Exception as e:
        return {
            "status": "failed",
            "output": "",
            "error": str(e),
            "trace": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "duration": round(time.time() - start_time, 2),
        }


# ---- 版本管理API ----

def _save_version(skill_name: str):
    """保存当前配置为历史版本"""
    skill_dir = CONFIG_DIR / "skills" / skill_name
    skill_file = skill_dir / "Skill.yaml"
    if not skill_file.exists():
        return
    versions_dir = skill_dir / "versions"
    versions_dir.mkdir(exist_ok=True)
    ts = str(int(time.time()))
    import shutil
    shutil.copy2(str(skill_file), str(versions_dir / f"{ts}.yaml"))


@app.get("/api/agents/{agent_name}/versions")
def list_agent_versions(agent_name: str):
    """列出Agent的历史版本"""
    versions_dir = CONFIG_DIR / "skills" / agent_name / "versions"
    if not versions_dir.exists():
        return []
    versions = []
    for f in sorted(versions_dir.iterdir(), reverse=True):
        if f.suffix == ".yaml":
            ts = int(f.stem)
            versions.append({
                "timestamp": ts,
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
                "filename": f.name,
            })
    return versions[:20]


@app.get("/api/agents/{agent_name}/versions/{ts}")
def get_agent_version(agent_name: str, ts: str):
    """获取某个历史版本内容"""
    version_file = CONFIG_DIR / "skills" / agent_name / "versions" / f"{ts}.yaml"
    if not version_file.exists():
        raise HTTPException(404, "Version not found")
    return {"timestamp": int(ts), "content": version_file.read_text(encoding="utf-8")}


@app.post("/api/agents/{agent_name}/versions/{ts}/rollback")
def rollback_agent_version(agent_name: str, ts: str):
    """回滚到指定版本"""
    version_file = CONFIG_DIR / "skills" / agent_name / "versions" / f"{ts}.yaml"
    if not version_file.exists():
        raise HTTPException(404, "Version not found")

    skill_file = CONFIG_DIR / "skills" / agent_name / "Skill.yaml"
    # 先保存当前版本
    _save_version(agent_name)
    # 用历史版本覆盖
    import shutil
    shutil.copy2(str(version_file), str(skill_file))
    # 热重载
    skill_loader.load_all()
    return {"success": True, "rolled_back_to": int(ts)}


# ---- 告警API ----

class AlertRuleCreate(BaseModel):
    name: str
    metric: str
    operator: str
    threshold: float
    channel: str = "platform"
    channel_config: dict = {}


@app.get("/api/alerts/rules")
def list_alert_rules():
    return alert_manager.list_rules()


@app.post("/api/alerts/rules")
def create_alert_rule(req: AlertRuleCreate):
    rule = alert_manager.create_rule(req.name, req.metric, req.operator, req.threshold, req.channel, req.channel_config)
    return rule.model_dump()


@app.delete("/api/alerts/rules/{rule_id}")
def delete_alert_rule(rule_id: str):
    if not alert_manager.delete_rule(rule_id):
        raise HTTPException(404, "Rule not found")
    return {"success": True}


@app.get("/api/alerts/history")
def get_alert_history():
    return alert_manager.get_history()


@app.post("/api/alerts/check")
def trigger_alert_check():
    """手动触发告警检查"""
    stats = get_stats_overview()
    alert_manager.check_and_alert(stats)
    return {"checked": True}


# ---- 定时任务API ----

class CronCreateRequest(BaseModel):
    agent_name: str
    cron_expr: str
    input_text: str = ""


@app.get("/api/cron")
def list_cron_jobs():
    return scheduler.list_jobs()


@app.post("/api/cron")
def create_cron_job(req: CronCreateRequest):
    skill = skill_loader.get_skill(req.agent_name)
    if not skill:
        raise HTTPException(404, "Agent not found")
    job = scheduler.create_job(req.agent_name, req.cron_expr, req.input_text)
    return job.model_dump()


@app.delete("/api/cron/{job_id}")
def delete_cron_job(job_id: str):
    if not scheduler.delete_job(job_id):
        raise HTTPException(404, "Job not found")
    return {"success": True}


@app.put("/api/cron/{job_id}/toggle")
def toggle_cron_job(job_id: str):
    job = scheduler.toggle_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.model_dump()


# ---- 辅助函数 ----

def _get_deploy_info(agent_name: str, agent_type: str, host: str, secret: str) -> dict:
    info = {"host": host, "secret": secret}

    if agent_type == "code_review":
        info["webhook_url"] = f"{host}/api/webhook/github"
        info["supported_platforms"] = ["GitHub", "GitLab", "Gitee"]
        info["trigger_events"] = ["pull_request.opened", "pull_request.synchronize", "pull_request.reopened"]
        info["setup_guide"] = (
            "1. 进入仓库 Settings → Webhooks → Add webhook\n"
            f"2. Payload URL: {host}/api/webhook/github\n"
            "3. Content type: application/json\n"
            f"4. Secret: {secret}\n"
            "5. 选择事件: Pull requests\n"
            "6. 保存"
        )
    elif agent_type == "customer_service":
        info["webhook_urls"] = {
            "zendesk": f"{host}/api/webhook/zendesk",
            "jira": f"{host}/api/webhook/jira-service",
            "feishu": f"{host}/api/webhook/feishu-helpdesk",
        }
        info["setup_guide"] = (
            "Zendesk: Admin → Extensions → HTTP Target → 配置URL\n"
            "Jira: Settings → Webhooks → 添加URL，事件选 issue_created\n"
            "飞书: 服务台设置 → 事件订阅 → 添加webhook URL"
        )
    else:
        info["webhook_url"] = f"{host}/api/webhook/custom/{agent_name}"
        info["setup_guide"] = f"向 {host}/api/webhook/custom/{agent_name} 发送POST请求触发Agent"

    return info


def _build_code_review_rules(config: dict) -> dict:
    pass_score = config.get("pass_score", 70)
    security_checks = config.get("security_checks", [
        "sql_injection", "xss", "hardcoded_secrets", "command_injection",
        "ssrf", "insecure_deserialization"
    ])
    quality_checks = config.get("quality_checks", ["function_length", "cyclomatic_complexity"])
    standards_checks = config.get("standards_checks", ["naming_convention", "error_handling"])

    return {
        "thresholds": {"max_score": 100, "pass_score": pass_score, "critical_auto_reject": True},
        "security": {"weight": 40, "enabled": True, "checks": security_checks},
        "quality": {"weight": 30, "enabled": True, "checks": quality_checks},
        "standards": {"weight": 20, "enabled": True, "checks": standards_checks},
        "linters": {"weight": 10, "enabled": True},
    }


def _build_customer_service_rules(config: dict) -> dict:
    return {
        "categories": config.get("categories", [
            {"id": "bug_report", "name": "Bug报告", "priority": "high", "sla_hours": 4},
            {"id": "feature_request", "name": "功能需求", "priority": "low", "sla_hours": 72},
            {"id": "account_issue", "name": "账户问题", "priority": "high", "sla_hours": 2},
        ]),
        "auto_reply": config.get("auto_reply", True),
        "escalate_rules": config.get("escalate_rules", ["用户要求人工", "连续3次未解决"]),
        "sentiment_detection": {"enabled": config.get("sentiment_detection", True)},
    }


def _build_resume_rules(config: dict) -> dict:
    return {
        "scoring_dimensions": config.get("dimensions", [
            {"id": "core_skills", "name": "核心技能", "weight": 35},
            {"id": "experience", "name": "相关经验", "weight": 25},
            {"id": "education", "name": "教育背景", "weight": 15},
            {"id": "project_quality", "name": "项目质量", "weight": 15},
            {"id": "growth_potential", "name": "成长潜力", "weight": 10},
        ]),
        "pass_score": config.get("pass_score", 70),
        "anti_bias": config.get("anti_bias", True),
    }


def _get_code_review_prompt() -> str:
    return """你是一个自动化代码审核Agent。严格按照review_rules中的规则执行审核。
步骤：1.获取diff 2.安全审计 3.质量检查 4.规范检查 5.运行linter 6.计算总分 7.输出报告。
发现critical问题直接退回PR。"""


def _get_customer_service_prompt() -> str:
    return """你是智能客服Agent。按照service_rules处理工单。
步骤：1.解析工单 2.分类 3.判定优先级 4.情绪检测 5.决定处理方式 6.生成回复。
无法判断时标记为需人工处理。"""


def _get_resume_prompt() -> str:
    return """你是简历筛选Agent。按照screening_rules的维度评分。
步骤：1.提取JD要求 2.逐维度评分 3.反歧视检查 4.生成结论。
评分必须基于简历事实，不可推测。"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=4000, reload=True)
