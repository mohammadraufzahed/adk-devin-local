"""Persist schedule definitions and validate/preview them with APScheduler triggers."""
from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.base import BaseTrigger

from .stateful import StatefulTools


class CronTools(StatefulTools):
    @staticmethod
    def _trigger(spec: str) -> BaseTrigger:
        now = datetime.now(timezone.utc)
        if spec.startswith("every:") or spec.startswith("in:"):
            is_interval = spec.startswith("every:")
            value = spec.split(":", 1)[1]
            match = re.fullmatch(r"(\d+)([smh]?)", value)
            if not match:
                raise ValueError("Use an integer duration, such as every:15m or in:30.")
            amount = int(match.group(1))
            unit = match.group(2) or "m"
            seconds = amount * {"s": 1, "m": 60, "h": 3600}[unit]
            if seconds <= 0:
                raise ValueError("Schedule duration must be positive.")
            if is_interval:
                return IntervalTrigger(seconds=seconds, start_date=now + timedelta(seconds=seconds), timezone=timezone.utc)
            return DateTrigger(run_date=now + timedelta(seconds=seconds), timezone=timezone.utc)
        if spec.startswith("daily:"):
            value = spec.removeprefix("daily:")
            if not re.fullmatch(r"\d{2}:\d{2}", value):
                raise ValueError("Use daily:HH:MM in 24-hour time.")
            hour, minute = map(int, value.split(":"))
            if hour > 23 or minute > 59:
                raise ValueError("Daily time is outside the valid clock range.")
            return CronTrigger(hour=hour, minute=minute, timezone=timezone.utc)
        if spec.startswith("once:"):
            value = spec.removeprefix("once:")
            if not re.fullmatch(r"\d{9,}", value):
                raise ValueError("Use once:<unix-timestamp>.")
            run_at = datetime.fromtimestamp(int(value), tz=timezone.utc)
            if run_at <= now:
                raise ValueError("One-time schedule must be in the future.")
            return DateTrigger(run_date=run_at, timezone=timezone.utc)
        if spec.startswith("cron:"):
            expression = spec.removeprefix("cron:").strip()
            try:
                return CronTrigger.from_crontab(expression, timezone=timezone.utc)
            except ValueError as exc:
                raise ValueError(f"Invalid cron expression: {exc}") from exc
        raise ValueError("Use every:<duration>, in:<duration>, daily:HH:MM, once:<unix-ts>, or cron:<5-field expression>.")

    @classmethod
    def _next_run(cls, spec: str) -> str:
        trigger = cls._trigger(spec)
        now = datetime.now(timezone.utc)
        next_run = trigger.get_next_fire_time(None, now)
        if next_run is None:
            raise ValueError("Schedule has no upcoming run time.")
        return next_run.isoformat()

    def cron_add(self, spec: str, prompt: str, soul: str = "", silent: bool = True, times: int = 0, project: str = "") -> str:
        """Record a validated schedule with its next run preview (no scheduler daemon is started)."""
        try:
            next_run = self._next_run(spec)
        except (ValueError, OverflowError) as exc:
            return str(exc)
        jobs = self._load("cron.json", [])
        row = {"id": uuid.uuid4().hex[:12], "spec": spec, "prompt": prompt[:8000], "soul": soul[:100], "silent": silent, "project": project[:200], "times": max(0, times), "paused": False, "created": time.time(), "next_run": next_run}
        jobs.append(row)
        self._save("cron.json", jobs)
        return f"Recorded schedule {row['id']} (next run {next_run}). Note: this package stores schedules but does not execute them; configure a host scheduler."

    def cron_list(self, all: bool = True) -> list[dict[str, Any]]:
        """List recorded schedule definitions (paused included when all=true)."""
        jobs = self._load("cron.json", [])
        return jobs if all else [job for job in jobs if not job.get("paused")]

    def cron_edit(self, job_id: str, spec: str = "", prompt: str = "") -> str:
        """Edit a recorded schedule and recompute its next-run preview."""
        jobs = self._load("cron.json", [])
        for job in jobs:
            if job.get("id") == job_id:
                if spec:
                    try:
                        next_run = self._next_run(spec)
                    except (ValueError, OverflowError) as exc:
                        return str(exc)
                    job["spec"] = spec
                    job["next_run"] = next_run
                if prompt:
                    job["prompt"] = prompt[:8000]
                self._save("cron.json", jobs)
                return "Schedule updated (host scheduler remains external to this package)."
        return "Schedule not found."

    def cron_pause(self, job_id: str, paused: bool = True) -> str:
        """Pause or resume a recorded schedule."""
        jobs = self._load("cron.json", [])
        for job in jobs:
            if job.get("id") == job_id:
                job["paused"] = paused
                self._save("cron.json", jobs)
                return "Schedule paused." if paused else "Schedule resumed."
        return "Schedule not found."

    def cron_remove(self, job_id: str) -> str:
        """Remove a schedule definition."""
        jobs = self._load("cron.json", [])
        kept = [job for job in jobs if job.get("id") != job_id]
        if len(jobs) == len(kept):
            return "Schedule not found."
        self._save("cron.json", kept)
        return "Schedule removed."
