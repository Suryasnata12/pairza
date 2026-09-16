"""
In-memory tracking for the mystery-generation background job. A single
admin panel talking to a single API process makes a lightweight
in-process tracker enough for this — the same trade-off already
documented in websockets/manager.py. Scaling to multiple API processes
would mean moving this to Redis instead; the call sites elsewhere in the
app wouldn't need to change, only this module would.
"""
import datetime as dt

_job_state: dict = {"status": "idle", "started_at": None, "finished_at": None, "report": None, "error": None}


def get_status() -> dict:
    return dict(_job_state)


def start() -> bool:
    """Returns False (and does nothing) if a job is already running —
    callers should treat that as a 409, not silently queue a second run."""
    if _job_state["status"] == "running":
        return False
    _job_state.update(status="running", started_at=dt.datetime.now(dt.timezone.utc).isoformat(), finished_at=None, report=None, error=None)
    return True


def finish(report: list[dict]) -> None:
    _job_state.update(status="done", finished_at=dt.datetime.now(dt.timezone.utc).isoformat(), report=report)


def fail(error: str) -> None:
    _job_state.update(status="failed", finished_at=dt.datetime.now(dt.timezone.utc).isoformat(), error=error)
