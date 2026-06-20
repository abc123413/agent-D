"""
告警模块 - 基于规则的告警检查与通知
"""

import time
import json
import uuid
import os
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel


class AlertRule(BaseModel):
    id: str
    name: str
    metric: str  # success_rate | avg_duration | error_count
    operator: str  # lt | gt | eq
    threshold: float
    channel: str  # feishu | email | platform
    channel_config: dict = {}
    enabled: bool = True
    created_at: float = 0


class AlertEvent(BaseModel):
    id: str
    rule_id: str
    rule_name: str
    metric: str
    current_value: float
    threshold: float
    message: str
    timestamp: float
    notified: bool = False


class AlertManager:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._rules: dict[str, AlertRule] = {}
        self._history: list[AlertEvent] = []
        self._cooldown: dict[str, float] = {}
        self._load()

    def _rules_file(self) -> Path:
        return self.data_dir / "alert_rules.json"

    def _history_file(self) -> Path:
        return self.data_dir / "alert_history.json"

    def _load(self):
        f = self._rules_file()
        if f.exists():
            for item in json.loads(f.read_text(encoding="utf-8")):
                rule = AlertRule(**item)
                self._rules[rule.id] = rule

        h = self._history_file()
        if h.exists():
            for item in json.loads(h.read_text(encoding="utf-8"))[-100:]:
                self._history.append(AlertEvent(**item))

    def _save_rules(self):
        data = [r.model_dump() for r in self._rules.values()]
        self._rules_file().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_history(self):
        data = [e.model_dump() for e in self._history[-100:]]
        self._history_file().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_rule(self, name: str, metric: str, operator: str, threshold: float, channel: str, channel_config: dict = {}) -> AlertRule:
        rule = AlertRule(
            id=str(uuid.uuid4())[:8],
            name=name,
            metric=metric,
            operator=operator,
            threshold=threshold,
            channel=channel,
            channel_config=channel_config,
            enabled=True,
            created_at=time.time(),
        )
        self._rules[rule.id] = rule
        self._save_rules()
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            self._save_rules()
            return True
        return False

    def list_rules(self) -> list[dict]:
        return [r.model_dump() for r in self._rules.values()]

    def get_history(self, limit: int = 50) -> list[dict]:
        return [e.model_dump() for e in self._history[-limit:]][::-1]

    def check_and_alert(self, stats: dict):
        """检查所有规则，触发告警"""
        now = time.time()
        metrics_map = {
            "success_rate": stats.get("success_rate", 100),
            "avg_duration": stats.get("avg_duration_seconds", 0),
            "error_count": stats.get("failed", 0),
            "total_tokens": stats.get("total_tokens", 0),
        }

        for rule in self._rules.values():
            if not rule.enabled:
                continue
            # 5分钟冷却
            if now - self._cooldown.get(rule.id, 0) < 300:
                continue

            current = metrics_map.get(rule.metric, 0)
            triggered = False

            if rule.operator == "lt" and current < rule.threshold:
                triggered = True
            elif rule.operator == "gt" and current > rule.threshold:
                triggered = True
            elif rule.operator == "eq" and current == rule.threshold:
                triggered = True

            if triggered:
                event = AlertEvent(
                    id=str(uuid.uuid4())[:8],
                    rule_id=rule.id,
                    rule_name=rule.name,
                    metric=rule.metric,
                    current_value=current,
                    threshold=rule.threshold,
                    message=f"[告警] {rule.name}: {rule.metric}={current} (阈值: {rule.operator} {rule.threshold})",
                    timestamp=now,
                )
                self._history.append(event)
                self._cooldown[rule.id] = now
                self._notify(rule, event)
                self._save_history()

    def _notify(self, rule: AlertRule, event: AlertEvent):
        """发送通知"""
        if rule.channel == "feishu":
            webhook_url = rule.channel_config.get("webhook_url", "")
            if webhook_url:
                try:
                    httpx.post(webhook_url, json={
                        "msg_type": "text",
                        "content": {"text": event.message},
                    }, timeout=5)
                    event.notified = True
                except Exception:
                    pass
        elif rule.channel == "platform":
            event.notified = True
