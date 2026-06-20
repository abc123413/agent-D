# 智能办公Agent平台

基于 **Harness 安全隔离架构** 的智能办公平台——技能通过 YAML 配置驱动，新增能力无需修改代码。

## 技术栈

**后端** `agent/`
- FastAPI + LangChain + LangGraph
- Harness 安全沙箱引擎
- 策略引擎（Policy Engine）细粒度权限控制
- 多智能体编排（Multi-Agent Orchestration）
- WebSocket 实时通信
- 定时任务调度 + 告警通知

**前端** `frontend/`
- React 18 + TypeScript + Vite
- 状态管理（Zustand）
- 页面：仪表盘、智能体管理、审批流、登录、设置

## 快速开始

### 1. 后端

```bash
cd agent
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env         # 编辑 .env 填入 API Key
python main.py
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

## 项目结构

```
agent/
├── config/           # YAML 配置驱动（全局配置、引擎提示词、策略规则、技能注册、编排提示词）
├── core/             # 核心引擎（Harness、策略、编排、调度、告警、Webhook）
├── tools/            # 技能工具（文件、Git、HTTP、Shell）
└── main.py           # FastAPI 入口

frontend/
└── src/
    ├── pages/        # Dashboard / Agents / Approvals / Settings / Login
    ├── components/   # 通用组件（Layout）
    ├── store/        # Zustand 状态管理
    ├── services/     # API 调用层
    └── types/        # TypeScript 类型定义
```

## 核心特性

- **YAML 驱动技能注册** — 新增能力不改代码，只加配置
- **多层安全策略** — Harness 沙箱 + Policy Engine 双重隔离
- **多智能体编排** — LangGraph 驱动的 Agent 协作
- **自动化管道** — Webhook 触发 → 策略校验 → 执行 → 通知
