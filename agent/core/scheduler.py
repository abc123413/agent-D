"""
定时调度器 - 支持Cron表达式触发Agent
"""

import asyncio
import time
import uuid
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class CronJob(BaseModel):
    id: str
    agent_name: str
    cron_expr: str
    input_text: str = ""
    enabled: bool = True
    last_run: float = 0
    next_run: float = 0
    created_at: float = 0


class Scheduler:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, CronJob] = {}
        self._task: Optional[asyncio.Task] = None
        self._executor = None
        self._harness = None
        self._skill_loader = None
        self._load_jobs()

    def set_dependencies(self, harness, executor, skill_loader):
        self._harness = harness
        self._executor = executor
        self._skill_loader = skill_loader

    def _jobs_file(self) -> Path:
        return self.data_dir / "cron_jobs.json"

    def _load_jobs(self):
        f = self._jobs_file()
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            for item in data:
                job = CronJob(**item)
                self._jobs[job.id] = job

    def _save_jobs(self):
        data = [job.model_dump() for job in self._jobs.values()]
        self._jobs_file().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_job(self, agent_name: str, cron_expr: str, input_text: str = "") -> CronJob:
        job = CronJob(
            id=str(uuid.uuid4())[:8],
            agent_name=agent_name,
            cron_expr=cron_expr,
            input_text=input_text,
            enabled=True,
            created_at=time.time(),
            next_run=self._calc_next_run(cron_expr),
        )
        self._jobs[job.id] = job
        self._save_jobs()
        return job

    def delete_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save_jobs()
            return True
        return False

    def toggle_job(self, job_id: str) -> Optional[CronJob]:
        job = self._jobs.get(job_id)
        if job:
            job.enabled = not job.enabled
            if job.enabled:
                job.next_run = self._calc_next_run(job.cron_expr)
            self._save_jobs()
        return job

    def list_jobs(self) -> list[dict]:
        return [job.model_dump() for job in self._jobs.values()]

    def start(self):
        self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self):
        while True:
            await asyncio.sleep(30)
            now = time.time()
            for job in list(self._jobs.values()):
                if not job.enabled:
                    continue
                if job.next_run <= now:
                    await self._execute_job(job)
                    job.last_run = now
                    job.next_run = self._calc_next_run(job.cron_expr)
                    self._save_jobs()

    async def _execute_job(self, job: CronJob):
        if not self._harness or not self._executor or not self._skill_loader:
            return
        skill = self._skill_loader.get_skill(job.agent_name)
        if not skill or not skill.enabled:
            return

        task = self._harness.create_task(job.input_text or f"定时任务触发: {job.agent_name}", job.agent_name)
        task.metadata["trigger"] = "cron"
        task.metadata["cron_job_id"] = job.id

        try:
            task.status = "running"
            result = await self._executor.execute(skill, task.input_text)
            trace_dicts = [{"step_type": s.step_type, "name": s.name, "input": s.input, "output": s.output, "start_time": s.start_time, "end_time": s.end_time, "tokens": s.tokens} for s in result.trace]
            self._harness.complete_task(task, result.output, trace_dicts, result.prompt_tokens, result.completion_tokens)
        except Exception as e:
            self._harness.fail_task(task, str(e))

    def _calc_next_run(self, cron_expr: str) -> float:
        """简化cron解析：支持 */N 和具体数值"""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return time.time() + 3600

        now = time.time()
        minute, hour, dom, month, dow = parts

        if minute.startswith("*/"):
            interval_min = int(minute[2:])
            return now + interval_min * 60
        elif hour.startswith("*/"):
            interval_hr = int(hour[2:])
            return now + interval_hr * 3600

        # 具体时间：计算下一次匹配
        import datetime
        dt_now = datetime.datetime.now()
        target_min = int(minute) if minute != "*" else dt_now.minute
        target_hr = int(hour) if hour != "*" else dt_now.hour

        target = dt_now.replace(hour=target_hr, minute=target_min, second=0, microsecond=0)
        if target <= dt_now:
            target += datetime.timedelta(days=1)

        return target.timestamp()
