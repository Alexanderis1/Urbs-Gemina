"""Long requests: answer within a fixed wait, otherwise hand back a job id to poll.

Modal web endpoints cut a request at about 150 s and answer with a redirect that
has no CORS headers, so a browser sees a network error. A request that is still
running after ``wait_s`` seconds keeps running in the background; the caller gets
``202 {"status": "running", "job_id": ..., "poll": "/jobs/<id>"}`` and polls.

Finished jobs are also written to a shared store (a Modal Dict on Modal) so a poll
that lands on another container still finds the result.
"""
from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable, MutableMapping

from fastapi.encoders import jsonable_encoder

log = logging.getLogger("urbs.api.jobs")


class Jobs:
    def __init__(self, wait_s: float, store: MutableMapping[str, Any] | None = None, workers: int = 8) -> None:
        self.wait_s = wait_s
        self._store = store
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="urbs-job")
        self._local: dict[str, Future[Any]] = {}
        self._lock = threading.Lock()

    def run(self, fn: Callable[[], Any]) -> tuple[bool, Any]:
        """``(True, result)`` when ``fn`` ends within the wait, else ``(False, job_id)``. Errors re-raise."""
        if self.wait_s <= 0:
            return True, fn()
        future = self._pool.submit(fn)
        try:
            return True, future.result(timeout=self.wait_s)
        except FutureTimeout:
            job_id = uuid.uuid4().hex
            with self._lock:
                self._local[job_id] = future
            future.add_done_callback(lambda f: self._publish(job_id, f))
            return False, job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            future = self._local.get(job_id)
        if future is not None:
            return {"status": "running", "job_id": job_id} if not future.done() else _outcome(job_id, future)
        if self._store is not None:
            try:
                found = self._store.get(job_id)
            except Exception:  # noqa: BLE001 - shared store down: report unknown, the caller retries
                log.exception("job store read failed")
                return None
            return dict(found) if isinstance(found, dict) else None
        return None

    def _publish(self, job_id: str, future: Future[Any]) -> None:
        if self._store is None:
            return
        try:
            self._store[job_id] = _outcome(job_id, future)
        except Exception:  # noqa: BLE001 - the local copy still answers polls on this container
            log.exception("job store write failed")


def _outcome(job_id: str, future: Future[Any]) -> dict[str, Any]:
    error = future.exception()
    if error is None:
        return {"status": "done", "job_id": job_id, "result": jsonable_encoder(future.result())}
    code = int(getattr(error, "status_code", 0) or (400 if type(error).__name__ == "ToolError" else 500))
    detail = getattr(error, "detail", None) or str(error)
    return {"status": "error", "job_id": job_id, "status_code": code, "error": str(detail)}


def modal_store(name: str) -> MutableMapping[str, Any] | None:
    """A Modal Dict shared by all containers of the app, or ``None`` outside Modal."""
    try:
        import modal
        store: MutableMapping[str, Any] = modal.Dict.from_name(name, create_if_missing=True)  # type: ignore[assignment]
        return store
    except Exception:  # noqa: BLE001 - no Modal: jobs stay per process
        log.warning("job store '%s' not available; jobs are per container", name)
        return None
