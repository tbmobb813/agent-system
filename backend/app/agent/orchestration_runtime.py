"""
Lightweight orchestration runtime:
- scheduled triggers
- event-driven handlers
- deferred execution queue
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from app.agent.memory import memory_manager
from app.database import execute
from app import database as _db

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class OrchestrationRuntime:
    def __init__(self, orchestrator) -> None:
        self.orchestrator = orchestrator
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._scheduler_task: asyncio.Task | None = None
        self._handlers: dict[str, list[EventHandler]] = {}
        self._jobs: list[dict[str, Any]] = []
        self._running = False

    def register_event_handler(self, event: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def emit_event(self, event: str, payload: dict[str, Any]) -> None:
        handlers = self._handlers.get(event, [])
        for handler in handlers:
            asyncio.create_task(handler(payload))

    def add_interval_job(
        self,
        *,
        name: str,
        interval_seconds: int,
        callback: Callable[[], Awaitable[None]],
    ) -> None:
        self._jobs.append(
            {
                "name": name,
                "interval_seconds": max(1, int(interval_seconds)),
                "callback": callback,
                "next_run_at": datetime.utcnow() + timedelta(seconds=max(1, int(interval_seconds))),
            }
        )

    async def enqueue_task(self, payload: dict[str, Any]) -> None:
        await self.queue.put(payload)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        # Event trigger: whenever a task completes from deferred queue.
        async def _default_completed_handler(payload: dict[str, Any]) -> None:
            logger.info("Deferred task completed: %s", payload.get("task_id", "unknown"))

        self.register_event_handler("task_completed", _default_completed_handler)

        # Scheduled trigger: periodic memory relevance decay.
        async def _decay_job() -> None:
            updated = await memory_manager.apply_relevance_decay()
            logger.debug("Memory decay job updated %s rows", updated)

        self.add_interval_job(
            name="memory_decay",
            interval_seconds=24 * 60 * 60,
            callback=_decay_job,
        )

        async def _consolidation_job() -> None:
            from app.utils.pillar_loader import get_pillar_config

            life = (get_pillar_config().get("memory") or {}).get("lifecycle") or {}
            if not life.get("consolidation_enabled"):
                return
            removed = await memory_manager.consolidate_duplicate_memories()
            logger.info("Memory consolidation removed %s duplicate row(s)", removed)

        self.add_interval_job(
            name="memory_consolidation",
            interval_seconds=7 * 24 * 60 * 60,
            callback=_consolidation_job,
        )

        self._worker_task = asyncio.create_task(self._queue_worker())
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        self._running = False
        for task in (self._worker_task, self._scheduler_task):
            if task and not task.done():
                task.cancel()
        for task in (self._worker_task, self._scheduler_task):
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._worker_task = None
        self._scheduler_task = None

    async def _queue_worker(self) -> None:
        while self._running:
            payload = await self.queue.get()
            task_id = payload.get("task_id")
            started_at = datetime.utcnow()
            try:
                if _db.db_pool and task_id:
                    await execute(
                        """
                        UPDATE tasks
                        SET status = 'running'
                        WHERE id = $1
                        """,
                        task_id,
                    )
                result, conversation_id = await self.orchestrator.run(
                    query=payload["query"],
                    context=payload.get("context"),
                    tools=payload.get("tools"),
                    user_id=payload.get("user_id"),
                    max_iterations=int(payload.get("max_iterations", 10)),
                    conversation_id=payload.get("conversation_id"),
                    reasoning_effort=payload.get("reasoning_effort"),
                )
                if _db.db_pool and task_id:
                    elapsed = (datetime.utcnow() - started_at).total_seconds()
                    await execute(
                        """
                        UPDATE tasks
                        SET status = 'completed',
                            result = $2,
                            completed_at = $3,
                            execution_time = $4
                        WHERE id = $1
                        """,
                        task_id,
                        (result or "")[:10000],
                        datetime.utcnow(),
                        elapsed,
                    )
                self.emit_event(
                    "task_completed",
                    {
                        "task_id": task_id,
                        "conversation_id": conversation_id,
                        "result_preview": (result or "")[:300],
                    },
                )
            except Exception as e:
                logger.warning("Deferred task failed: %s", e)
                if _db.db_pool and task_id:
                    elapsed = (datetime.utcnow() - started_at).total_seconds()
                    await execute(
                        """
                        UPDATE tasks
                        SET status = 'failed',
                            result = $2,
                            completed_at = $3,
                            execution_time = $4
                        WHERE id = $1
                        """,
                        task_id,
                        str(e)[:10000],
                        datetime.utcnow(),
                        elapsed,
                    )
                self.emit_event("task_failed", {"error": str(e)})
            finally:
                self.queue.task_done()

    async def _scheduler_loop(self) -> None:
        while self._running:
            now = datetime.utcnow()
            for job in self._jobs:
                if now < job["next_run_at"]:
                    continue
                try:
                    await job["callback"]()
                except Exception as e:
                    logger.warning("Scheduled job '%s' failed: %s", job["name"], e)
                finally:
                    job["next_run_at"] = now + timedelta(seconds=job["interval_seconds"])
            await asyncio.sleep(1)
