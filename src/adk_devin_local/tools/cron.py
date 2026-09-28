"""Persist schedule definitions and validate/preview them with APScheduler triggers."""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.base import BaseTrigger

from .stateful import StatefulTools


class CronTools(StatefulTools):
    """When PI_CRON_DIR is set, cron_* operates on the host's real job
    files (jobs/<id>.json) that the pi-cron daemon executes — same schema
    as the pi-cron extension. Without it, falls back to the package-local
    cron.json store (records only, nothing executes)."""

    def _host_dir(self) -> Path | None:
        directory = self._e("PI_CRON_DIR")
        return Path(directory).expanduser() if directory else None

    def _host_jobs(self) -> list[tuple[Path, dict]]:
        base = self._host_dir()
        if base is None:
            return []
        jobs_dir = base / "jobs"
        out = []
        for f in sorted(jobs_dir.glob("*.json")):
            try:
                out.append((f, json.loads(f.read_text())))
            except (OSError, ValueError):
                continue
        return out

    @staticmethod
    def _host_find(jobs: list[tuple[Path, dict]], job_id: str):
        matches = [(f, j) for f, j in jobs if str(j.get("id", "")).startswith(job_id)]
        return matches[0] if matches else (None, None)

    @staticmethod
    def _host_write(path: Path, job: dict) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job))
        tmp.replace(path)

    def _host_add(self, spec: str, prompt: str, soul: str, silent: bool,
                times: int, project: str, dedup_key: str, report: str,
                thread: int) -> str:
        base = self._host_dir()
        assert base is not None
        jobs_dir = base / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        jobs = self._host_jobs()
        if dedup_key:
            for f, j in jobs:
                if j.get("dedup_key") == dedup_key:
                    f.unlink(missing_ok=True)
        env = self._merged_env()
        # in:N[smh] → once:<unix ts> (bare number = minutes, like pi-cron)
        if spec.startswith("in:"):
            raw = spec[3:]
            match = re.fullmatch(r"(\d+)([smh]?)", raw)
            if not match:
                return f"bad spec '{spec}' — in:N needs an integer with optional s/m/h"
            secs = int(match.group(1)) * {"s": 1, "m": 60, "h": 3600}[match.group(2) or "m"]
            spec = f"once:{int(time.time()) + secs}"
        jid = str(uuid.uuid4())
        env["PI_JOB_ID"] = jid
        if silent:
            env["PI_SILENT"] = "1"
        if report:
            env["PI_REPORT"] = report
            prompt += (f"\n\n[Execution policy — {report}: this is a SILENT background job. "
                       "Post nothing to chat unless the policy says to.]")
        elif silent:
            prompt += ("\n\n[Execution policy — on-failure: this is a SILENT background job. "
                       "Post nothing to chat unless something is wrong.]")
        job = {
            "id": jid,
            "soul": soul or self._e("PI_TEAM_FROM", "adk"),
            "env": env,
            "cwd": str(self.root),
            "spec": spec,
            "prompt": prompt[:8000],
            "chat": self._e("PI_TEAM_CHAT"),
            "thread": thread or int(self._e("PI_TEAM_THREAD") or 0) or None,
            "dedup_key": dedup_key or None,
            "silent": silent,
            "report": report or None,
            "times": times or None,
            "project": project or None,
            "next_run": 0,
            "created": int(time.time()),
        }
        self._host_write(jobs_dir / f"{jid}.json", job)
        return f"Scheduled {jid[:8]} ({spec}) — host daemon will execute it."

    def job_state(self, set: dict | None = None) -> dict[str, Any]:
        """Persistent per-job JSON memory (survives between runs of this job)."""
        jid = self._e("PI_JOB_ID", "adhoc")
        base = self._host_dir()
        states = (base / "states") if base else (self.state / "states")
        states.mkdir(parents=True, exist_ok=True)
        file = states / f"{jid}.json"
        state: dict[str, Any] = {}
        if file.exists():
            try:
                state = json.loads(file.read_text())
            except (OSError, ValueError):
                state = {}
        if set:
            state.update(set)
            file.write_text(json.dumps(state))
        return {"job": jid, "state": state}

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
            tz = timezone.utc
            if "@" in value:
                value, _, zone = value.partition("@")
                try:
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo(zone)
                except Exception:
                    tz = timezone.utc
            if not re.fullmatch(r"\d{2}:\d{2}", value):
                raise ValueError("Use daily:HH:MM in 24-hour time.")
            hour, minute = map(int, value.split(":"))
            if hour > 23 or minute > 59:
                raise ValueError("Daily time is outside the valid clock range.")
            return CronTrigger(hour=hour, minute=minute, timezone=tz)
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
            tz = timezone.utc
            if "@" in expression:
                expression, _, zone = expression.partition("@")
                try:
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo(zone)
                except Exception:
                    tz = timezone.utc
            try:
                return CronTrigger.from_crontab(expression.strip(), timezone=tz)
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

    def cron_add(self, spec: str, prompt: str, soul: str = "", silent: bool = True, times: int = 0, project: str = "", dedup_key: str = "", report: str = "", thread: int = 0) -> str:
        """Schedule a job — writes a real job file for the host pi-cron daemon when PI_CRON_DIR is set."""
        try:
            next_run = self._next_run(spec)
        except (ValueError, OverflowError) as exc:
            return str(exc)
        if self._host_dir() is not None:
            return self._host_add(spec, prompt, soul, silent, times, project, dedup_key, report, thread)
        jobs = self._load("cron.json", [])
        row = {"id": uuid.uuid4().hex[:12], "spec": spec, "prompt": prompt[:8000], "soul": soul[:100], "silent": silent, "project": project[:200], "times": max(0, times), "paused": False, "created": time.time(), "next_run": next_run}
        jobs.append(row)
        self._save("cron.json", jobs)
        return f"Recorded schedule {row['id']} (next run {next_run}). Note: this package stores schedules but does not execute them; configure a host scheduler."

    def cron_list(self, all: bool = True) -> list[dict[str, Any]]:
        """List scheduled jobs — host daemon jobs when PI_CRON_DIR is set."""
        host = self._host_jobs()
        if host:
            rows = [j for _, j in host]
            return rows if all else [j for j in rows if not j.get("paused")]
        jobs = self._load("cron.json", [])
        return jobs if all else [job for job in jobs if not job.get("paused")]

    def cron_edit(self, job_id: str, spec: str = "", prompt: str = "") -> str:
        """Edit a recorded schedule and recompute its next-run preview."""
        host = self._host_jobs()
        if host:
            f, job = self._host_find(host, job_id)
            if job is None:
                return "Schedule not found."
            if spec:
                try:
                    self._next_run(spec)
                except (ValueError, OverflowError) as exc:
                    return str(exc)
                job["spec"] = spec
                job["next_run"] = 0
            if prompt:
                job["prompt"] = prompt[:8000]
            self._host_write(f, job)
            return "Schedule updated."
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
        """Pause or resume a scheduled job."""
        host = self._host_jobs()
        if host:
            f, job = self._host_find(host, job_id)
            if job is None:
                return "Schedule not found."
            job["paused"] = paused
            self._host_write(f, job)
            return "Schedule paused." if paused else "Schedule resumed."
        jobs = self._load("cron.json", [])
        for job in jobs:
            if job.get("id") == job_id:
                job["paused"] = paused
                self._save("cron.json", jobs)
                return "Schedule paused." if paused else "Schedule resumed."
        return "Schedule not found."

    def cron_remove(self, job_id: str) -> str:
        """Remove a schedule definition."""
        host = self._host_jobs()
        if host:
            f, job = self._host_find(host, job_id)
            if job is None:
                return "Schedule not found."
            f.unlink(missing_ok=True)
            return f"removed {str(job.get('id'))[:8]}"
        jobs = self._load("cron.json", [])
        kept = [job for job in jobs if job.get("id") != job_id]
        if len(jobs) == len(kept):
            return "Schedule not found."
        self._save("cron.json", kept)
        return "Schedule removed."
