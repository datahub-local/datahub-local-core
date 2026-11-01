"""Create the taskboard tick job when the gateway starts.

A hook loads from HERMES_HOME/hooks/<name>/, runs inside the gateway process, and a
raising handler is logged rather than fatal. That is why this file never raises and
why it is preferred to an init container here: the job belongs to the gateway's own
state, and the gateway is the only process that reads it.

The job is created only when `jobs.json` has no job by this name, so an existing
volume keeps whatever the owner has scheduled, and a restored one is repaired.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("hooks.taskboard-tick")

HERMES = "/opt/hermes/.venv/bin/hermes"
JOB = "taskboard-tick"
PROMPT = "Follow the taskboard-loop skill for one tick. Report only what changed."
SCHEDULE = "10m"


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or "/opt/data")


def job_exists(jobs_path: Path) -> bool:
    """True when the tick is already scheduled, or the file cannot be read.

    An unreadable `jobs.json` is treated as "present": writing into a file we could
    not parse would drop the owner's other jobs, and a missing tick is recoverable.
    """
    try:
        data = json.loads(jobs_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return False
    except (OSError, ValueError) as exc:
        logger.warning("taskboard-tick: cannot read %s (%s); leaving it alone", jobs_path, exc)
        return True
    jobs = data.get("jobs") if isinstance(data, dict) else None
    return any(job.get("name") == JOB for job in jobs or [] if isinstance(job, dict))


def create(home: Path) -> bool:
    command = [
        HERMES,
        "cron",
        "create",
        SCHEDULE,
        PROMPT,
        "--name",
        JOB,
        "--skill",
        "taskboard-loop",
        "--deliver",
        "local",
    ]
    env = {**os.environ, "HERMES_HOME": str(home), "HOME": str(home)}
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=120)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
        logger.warning("taskboard-tick: create failed (%s): %s", result.returncode, " | ".join(tail))
        return False
    logger.info("taskboard-tick: scheduled every %s", SCHEDULE)
    return True


async def handle(event_type: str, context: dict) -> None:
    if event_type != "gateway:startup":
        return
    home = hermes_home()
    jobs_path = home / "cron" / "jobs.json"
    if job_exists(jobs_path):
        logger.info("taskboard-tick: already scheduled")
        return
    # subprocess blocks, so keep it off the gateway's event loop.
    await asyncio.to_thread(create, home)
