"""
策略引擎 - 基于02_策略引擎规则.yaml的安全拦截层

支持：
- 技能权限控制（allowed/blocked actions）
- 敏感信息拦截与脱敏
- 输出审计（危险命令拦截）
- 热重载
"""

import re
import time
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


class PolicyViolation(BaseModel):
    rule_name: str
    level: str  # block | mask | audit
    content: str
    action_taken: str
    timestamp: float
    skill_name: str = ""


class PolicyEngine:
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self._skill_permissions: dict = {}
        self._sensitive_patterns: list[dict] = []
        self._blocked_outputs: list[str] = []
        self._violations: list[PolicyViolation] = []
        self._enabled = True
        self.load_rules()

    def load_rules(self):
        rules_file = self.config_dir / "02_策略引擎规则.yaml"
        if not rules_file.exists():
            return
        with open(rules_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self._skill_permissions = data.get("skill_permissions", {})
        self._sensitive_patterns = data.get("sensitive_patterns", [])
        audit = data.get("output_audit", {})
        self._blocked_outputs = audit.get("blocked_outputs", [])

    def check_permission(self, skill_name: str, action: str) -> Optional[PolicyViolation]:
        perms = self._skill_permissions.get(skill_name)
        if not perms:
            return None

        blocked = perms.get("blocked_actions", [])
        if action in blocked:
            v = PolicyViolation(
                rule_name=f"技能权限拦截",
                level="block",
                content=f"技能 {skill_name} 不允许执行 {action} 操作",
                action_taken="已拦截",
                timestamp=time.time(),
                skill_name=skill_name,
            )
            self._violations.append(v)
            return v
        return None

    def check_input(self, content: str, skill_name: str = "") -> Optional[PolicyViolation]:
        for blocked in self._blocked_outputs:
            if blocked.lower() in content.lower():
                v = PolicyViolation(
                    rule_name="危险输入拦截",
                    level="block",
                    content=f"检测到危险内容: {blocked}",
                    action_taken="已拦截",
                    timestamp=time.time(),
                    skill_name=skill_name,
                )
                self._violations.append(v)
                return v
        return None

    def check_output(self, content: str, skill_name: str = "") -> Optional[PolicyViolation]:
        for blocked in self._blocked_outputs:
            if blocked.lower() in content.lower():
                v = PolicyViolation(
                    rule_name="输出审计拦截",
                    level="block",
                    content=f"输出包含危险内容: {blocked}",
                    action_taken="已拦截",
                    timestamp=time.time(),
                    skill_name=skill_name,
                )
                self._violations.append(v)
                return v
        return None

    def mask_sensitive(self, content: str) -> str:
        for pattern_cfg in self._sensitive_patterns:
            pattern = pattern_cfg.get("pattern", "")
            if not pattern:
                continue
            try:
                content = re.sub(pattern, "***", content)
            except re.error:
                pass
        return content

    def requires_approval(self, skill_name: str) -> bool:
        perms = self._skill_permissions.get(skill_name, {})
        return perms.get("requires_approval", False)

    def get_violations(self, limit: int = 50) -> list[dict]:
        return [v.model_dump() for v in self._violations[-limit:]]

    def get_rules_summary(self) -> dict:
        return {
            "skill_permissions": self._skill_permissions,
            "sensitive_patterns": [
                {"pattern": p.get("pattern"), "description": p.get("description", ""), "action": p.get("action")}
                for p in self._sensitive_patterns
            ],
            "blocked_outputs": self._blocked_outputs,
        }
