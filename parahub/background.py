"""
Shared bounded background-task pool.

Replaces the historical thread-per-event pattern (every signal/endpoint
spawning its own daemon thread). Unbounded spawning meant a burst of events
(notification storm, Neo4j outage, SOS fan-out) could open hundreds of
threads, each holding its own PostgreSQL/Neo4j connection — against
max_connections=100.

- Fixed pool of daemon worker threads per process, started lazily.
- Bounded PriorityQueue: when full, spawn() drops the task and logs an error
  — the same best-effort semantics the fire-and-forget daemon threads had
  (they died silently with the process).
- close_old_connections() around every task keeps the per-worker Django DB
  connections healthy; long-lived worker threads would otherwise hold stale
  connections across postgres restarts.
- Lower `priority` runs earlier; latency-sensitive fan-outs (SOS alerts) pass
  PRIORITY_URGENT to jump ahead of bulk sync work.
"""

import itertools
import logging
import queue
import threading

from django.db import close_old_connections

logger = logging.getLogger(__name__)

PRIORITY_URGENT = 0
PRIORITY_DEFAULT = 10

_MAX_QUEUE = 1000
_WORKERS = 4

_queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=_MAX_QUEUE)
_counter = itertools.count()  # FIFO tie-break; keeps task tuples comparable
_start_lock = threading.Lock()
_started = False


def _worker():
    while True:
        _prio, _seq, fn, args, kwargs, label = _queue.get()
        try:
            close_old_connections()
            fn(*args, **kwargs)
        except Exception:
            logger.exception(f"Background task {label} failed")
        finally:
            close_old_connections()
            _queue.task_done()


def _ensure_workers():
    global _started
    if _started:
        return
    with _start_lock:
        if _started:
            return
        for i in range(_WORKERS):
            threading.Thread(target=_worker, daemon=True, name=f'parahub-bg-{i}').start()
        _started = True


def spawn(fn, *args, priority=PRIORITY_DEFAULT, label=None, **kwargs):
    """Queue fn(*args, **kwargs) on the shared worker pool.

    Returns True if queued, False when the queue is full (task dropped,
    error logged). Callers treat this as best-effort fire-and-forget,
    exactly like the daemon threads this replaces.
    """
    _ensure_workers()
    label = label or getattr(fn, '__name__', repr(fn))
    try:
        _queue.put_nowait((priority, next(_counter), fn, args, kwargs, label))
        return True
    except queue.Full:
        logger.error(f"Background queue full ({_MAX_QUEUE}); dropped task {label}")
        return False
