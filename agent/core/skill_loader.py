"""
技能加载器 - 从 config/skills/*/Skill.yaml 动态加载技能

按照技能注册表(03_技能注册表.yaml)和技能目录结构加载。
新增技能只需：1. 创建目录 2. 放入Skill.yaml 3. 在注册表添加条目（或直接扫描）
"""

import glob
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


class SkillConfig(BaseModel):
    name: str
    display_name: str
    version: str = "1.0.0"
    description: str = ""
    enabled: bool = True
    prompt: str = ""
    input_schema: list[dict] = []
    output_schema: list[dict] = []
    security: dict = {}
    metadata: dict = {}


class SkillLoader:
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self.skills_dir = self.config_dir / "skills"
        self._skills: dict[str, SkillConfig] = {}
        self._registry: list[dict] = []
        self.load_all()

    def load_all(self):
        self._skills.clear()
        self._load_registry()

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "Skill.yaml"
            if skill_file.exists():
                skill = self._load_skill_file(skill_file)
                if skill:
                    self._skills[skill.name] = skill

    def _load_registry(self):
        registry_file = self.config_dir / "03_技能注册表.yaml"
        if registry_file.exists():
            with open(registry_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._registry = data.get("skills", [])

    def _load_skill_file(self, filepath: Path) -> Optional[SkillConfig]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data:
                return None

            registry_entry = next(
                (r for r in self._registry if r["name"] == data.get("name")),
                {}
            )
            enabled = registry_entry.get("enabled", data.get("enabled", True))

            metadata = data.get("metadata", {})
            # 将tools声明存入metadata供executor使用
            if "tools" in data:
                metadata["tools"] = data["tools"]

            # 将扩展配置字段(review_rules, decision_rules等)存入metadata
            standard_keys = {"name", "display_name", "version", "description", "enabled",
                           "prompt", "input_schema", "output_schema", "security", "metadata", "tools"}
            for key in data:
                if key not in standard_keys:
                    metadata[key] = data[key]

            return SkillConfig(
                name=data["name"],
                display_name=data.get("display_name", data["name"]),
                version=data.get("version", "1.0.0"),
                description=data.get("description", ""),
                enabled=enabled,
                prompt=data.get("prompt", ""),
                input_schema=data.get("input_schema", []),
                output_schema=data.get("output_schema", []),
                security=data.get("security", {}),
                metadata=metadata,
            )
        except Exception as e:
            print(f"[SkillLoader] Failed to load {filepath}: {e}")
            return None

    def get_skill(self, skill_name: str) -> Optional[SkillConfig]:
        return self._skills.get(skill_name)

    def get_enabled_skills(self) -> list[SkillConfig]:
        return [s for s in self._skills.values() if s.enabled]

    def list_skills(self) -> list[dict]:
        return [
            {
                "id": s.name,
                "name": s.display_name,
                "description": s.description,
                "enabled": s.enabled,
                "version": s.version,
                "requires_approval": s.security.get("requires_approval", False),
            }
            for s in self._skills.values()
        ]

    def reload_skill(self, skill_name: str) -> bool:
        skill_dir = self.skills_dir / skill_name
        skill_file = skill_dir / "Skill.yaml"
        if skill_file.exists():
            skill = self._load_skill_file(skill_file)
            if skill:
                self._skills[skill.name] = skill
                return True
        return False
