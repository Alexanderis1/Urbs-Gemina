"""Long requests answer 202 with a job id instead of hitting Modal's ~150 s web limit."""
from __future__ import annotations

import time
from typing import Any

import pytest

from twin.api.jobs import Jobs


def test_fast_work_answers_directly() -> None:
    assert Jobs(wait_s=5).run(lambda: {"x": 1}) == (True, {"x": 1})


def test_disabled_wait_runs_inline() -> None:
    assert Jobs(wait_s=0).run(lambda: 3) == (True, 3)


def test_slow_work_becomes_a_job_and_lands_in_the_shared_store() -> None:
    store: dict[str, Any] = {}
    jobs = Jobs(wait_s=0.05, store=store)
    finished, job_id = jobs.run(lambda: (time.sleep(0.3), {"ok": True})[1])
    assert not finished
    assert jobs.get(job_id) == {"status": "running", "job_id": job_id}
    for _ in range(50):
        if store.get(job_id):
            break
        time.sleep(0.05)
    assert store[job_id]["status"] == "done"
    assert store[job_id]["result"] == {"ok": True}
    # another container: only the shared store knows the job
    assert Jobs(wait_s=1, store=store).get(job_id) == store[job_id]


def test_failed_job_reports_the_error() -> None:
    jobs = Jobs(wait_s=0.01)

    def boom() -> None:
        time.sleep(0.1)
        raise ValueError("bad input")

    finished, job_id = jobs.run(boom)
    assert not finished
    time.sleep(0.3)
    out = jobs.get(job_id)
    assert out is not None and out["status"] == "error" and "bad input" in out["error"]


def test_errors_within_the_wait_raise_normally() -> None:
    with pytest.raises(ValueError):
        Jobs(wait_s=1).run(lambda: (_ for _ in ()).throw(ValueError("x")))


def test_unknown_job_is_404() -> None:
    from fastapi.testclient import TestClient

    from twin.api.app import create_app

    client = TestClient(create_app())
    assert client.get("/jobs/nope").status_code == 404


def test_model_tables_found_from_any_working_directory(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """On Modal the process does not start in the repo root; tables on data/processed must still be found."""
    from twin.beliefs import landuse

    assert all(d.is_absolute() for d in landuse.SEARCH_DIRS)
    monkeypatch.chdir(tmp_path)
    assert landuse.SEARCH_DIRS[1] == landuse.ROOT / "data" / "processed"
