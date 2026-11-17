"""Image jobs: a generation keeps running when the client stops waiting for it.

A client may cancel a tool call after a fixed time (60 s in several) whatever the
server does. If the generation lived in that call, the cancellation would kill it and
the agent would only see a generic timeout. Here the generation lives in a thread of
the server: calls wait for it a bounded time and then report that it is still running.
Only `cancel` stops a job.

The state of every job is also written to `config.JOBS_FILE`, so that a job whose
server died is reported as interrupted, not as unknown.
"""

import json
import os
import threading
import time
import uuid

from imagehearth_mcp.engine import config, progress
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.platform import files, processes

log = get_logger("jobs")

RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"
INTERRUPTED = "interrupted"

ACTIVE = (RUNNING,)

_lock = threading.RLock()
_jobs = {}


def _owner():
    pid = os.getpid()
    return pid, processes.create_time(pid)


def _owner_alive(pid, created):
    if not pid:
        return False

    current = processes.create_time(pid)

    if current is None:
        return False

    return created is None or abs(current - created) <= processes.CREATE_TIME_TOLERANCE


class Job:
    def __init__(self, kind, include_image=False):
        self.id = uuid.uuid4().hex[:8]
        self.kind = kind  # "single" or "batch"
        self.include_image = include_image
        self.status = RUNNING
        self.tracker = progress.Tracker()
        self.started = time.time()
        self.finished_at = None
        self.result = None
        self.error = None
        self.exception = None
        self.done = threading.Event()
        self.pid, self.created = _owner()

    @property
    def stage(self):
        return self.tracker.stage

    @property
    def elapsed(self):
        return int((self.finished_at or time.time()) - self.started)

    def record(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "stage": self.stage,
            "started": self.started,
            "finished": self.finished_at,
            "result": None if self.result is None else str(self.result),
            "error": self.error,
            "pid": self.pid,
            "created": self.created,
        }


def _read_file():
    try:
        data = json.loads(config.JOBS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

    return data if isinstance(data, dict) else {}


def _save(job):
    """Best effort: a job never fails because its state could not be written."""
    try:
        with _lock:
            data = _read_file()
            data[job.id] = job.record()
            finished = sorted(
                (key for key, value in data.items() if value.get("status") != RUNNING),
                key=lambda key: data[key].get("started") or 0,
            )

            for key in finished[: max(0, len(finished) - config.JOBS_KEPT)]:
                del data[key]

            config.JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary = config.JOBS_FILE.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_text(json.dumps(data), encoding="utf-8")
            files.replace(temporary, config.JOBS_FILE)
    except OSError as error:
        log.warning("Could not save the state of job %s: %s", job.id, error)


def start(function, kind, include_image=False, **arguments):
    """Run `function(**arguments)` in the background and return its Job."""
    job = Job(kind, include_image)

    def work():
        try:
            with progress.tracking(job.tracker):
                result = function(**arguments)

            job.result = result

            # A batch ends normally when cancelled: its finished images are in the result.
            job.status = CANCELLED if job.tracker.cancelled.is_set() else COMPLETED
        except progress.GenerationCancelled as error:
            job.status = CANCELLED
            job.error = str(error)
            job.exception = error
        except BaseException as error:
            log.exception("Job %s failed", job.id)
            job.status = FAILED
            job.error = str(error) or type(error).__name__
            job.exception = error
        finally:
            job.finished_at = time.time()
            _save(job)
            job.done.set()

    with _lock:
        _jobs[job.id] = job

    _save(job)
    threading.Thread(target=work, name=f"image-job-{job.id}", daemon=True).start()
    return job


def _from_record(record):
    """A job of this or another server process, known only by its saved state."""
    job = Job(record.get("kind", "single"))
    job.id = record["id"]
    job.status = record.get("status", RUNNING)
    job.tracker.stage = record.get("stage") or job.tracker.stage
    job.started = record.get("started") or job.started
    job.finished_at = record.get("finished")
    job.result = record.get("result")
    job.error = record.get("error")
    job.pid = record.get("pid")
    job.created = record.get("created")

    if job.status == RUNNING and not _owner_alive(job.pid, job.created):
        job.status = INTERRUPTED
        job.finished_at = time.time()

    if job.status != RUNNING:
        job.done.set()

    return job


def get(job_id=""):
    """The job with that id; with no id, the most recent one. None if unknown."""
    with _lock:
        if job_id:
            if job_id in _jobs:
                return _jobs[job_id]

            record = _read_file().get(job_id)
            return _from_record({**record, "id": job_id}) if record else None

        candidates = [job.record() for job in _jobs.values()]
        candidates += [
            {**record, "id": key}
            for key, record in _read_file().items()
            if key not in _jobs
        ]

    if not candidates:
        return None

    latest = max(candidates, key=lambda record: record.get("started") or 0)
    return get(latest["id"])


def known_ids():
    with _lock:
        return sorted({*_jobs, *_read_file()})


def active():
    """The jobs being generated now, in this server or any other."""
    with _lock:
        found = {job_id: job for job_id, job in _jobs.items() if job.status == RUNNING}

        for key, record in _read_file().items():
            if key in found or key in _jobs:
                continue

            job = _from_record({**record, "id": key})

            if job.status == RUNNING:
                found[key] = job

    return sorted(found.values(), key=lambda job: job.started)


def cancel(job):
    """Ask a running job to stop. It ends by itself once it has cleaned the session."""
    if job.status != RUNNING:
        return False

    if job.id in _jobs:
        job.tracker.cancelled.set()
        return True

    return False


def describe(job):
    """The facts of a job for status reports."""
    return {
        "id": job.id,
        "status": job.status,
        "stage": job.stage,
        "elapsed_seconds": job.elapsed,
    }
