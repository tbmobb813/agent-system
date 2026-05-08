"""
Lightweight orchestration runtime:
- scheduled triggers
- event-driven handlers
- deferred execution queue (asyncio or optional Redis)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Optional

from app.agent.memory import memory_manager
from app.config import settings
from app.database import execute, fetch
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
        self._redis: Any = None
        self._redis_key = "agent:deferred_tasks"

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
                "next_run_at": datetime.utcnow()
                + timedelta(seconds=max(1, int(interval_seconds))),
            }
        )

    async def enqueue_task(self, payload: dict[str, Any]) -> None:
        if self._redis is not None:
            await self._redis.lpush(self._redis_key, json.dumps(payload, default=str))
        else:
            await self.queue.put(payload)

    async def pending_queue_size(self) -> int | None:
        if self._redis is not None:
            try:
                n = await self._redis.llen(self._redis_key)
                return int(n)
            except Exception as e:
                logger.debug("Redis LLEN failed: %s", e)
                return None
        return self.queue.qsize()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        from app.utils.pillar_loader import get_pillar_config

        cfg = get_pillar_config()
        orch = cfg.get("orchestration") or {}
        mq = orch.get("message_queue") or {}
        provider = str(mq.get("provider") or "asyncio").strip().lower()
        self._redis_key = str(mq.get("redis_queue_key") or self._redis_key)
        if provider == "redis" and settings.REDIS_URL:
            try:
                import redis.asyncio as redis

                self._redis = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                )
                await self._redis.ping()
                logger.info("Orchestration queue: Redis (%s)", self._redis_key)
            except Exception as e:
                logger.warning(
                    "Redis queue unavailable (%s) — falling back to in-process asyncio queue",
                    e,
                )
                self._redis = None
        else:
            if provider == "redis" and not settings.REDIS_URL:
                logger.warning(
                    "message_queue.provider=redis but REDIS_URL unset — using asyncio queue"
                )
            self._redis = None

        # Event trigger: whenever a task completes from deferred queue.
        async def _default_completed_handler(payload: dict[str, Any]) -> None:
            logger.info(
                "Deferred task completed: %s", payload.get("task_id", "unknown")
            )

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
            life = (get_pillar_config().get("memory") or {}).get("lifecycle") or {}
            if not life.get("consolidation_enabled"):
                return
            removed = await memory_manager.consolidate_duplicate_memories()
            logger.info("Memory consolidation removed %s duplicate row(s)", removed)
            if life.get("semantic_consolidation_enabled"):
                srem = await memory_manager.consolidate_semantic_near_duplicates()
                logger.info(
                    "Semantic memory consolidation removed %s near-duplicate row(s)",
                    srem,
                )

        self.add_interval_job(
            name="memory_consolidation",
            interval_seconds=7 * 24 * 60 * 60,
            callback=_consolidation_job,
        )

        async def _user_cron_dispatch() -> None:
            await self._dispatch_due_scheduled_tasks()

        self.add_interval_job(
            name="user_cron_dispatch",
            interval_seconds=60,
            callback=_user_cron_dispatch,
        )

        trig = orch.get("triggers") or {}
        st = trig.get("scheduled_tasks") or {}
        if st.get("enabled"):
            for raw in st.get("tasks") or []:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name") or "scheduled").strip() or "scheduled"
                action = str(raw.get("action") or "").strip().lower()
                interval = int(raw.get("interval_seconds") or 0)
                if interval < 60:
                    logger.warning(
                        "Scheduled task %s skipped — interval_seconds must be >= 60",
                        name,
                    )
                    continue

                if action == "consolidate_memories":

                    async def _consolidate_named(jname: str = name) -> None:
                        life = (get_pillar_config().get("memory") or {}).get(
                            "lifecycle"
                        ) or {}
                        if not life.get("consolidation_enabled"):
                            return
                        removed = await memory_manager.consolidate_duplicate_memories()
                        logger.info(
                            "Scheduled %s: consolidation removed %s row(s)",
                            jname,
                            removed,
                        )

                    self.add_interval_job(
                        name=f"user:{name}",
                        interval_seconds=interval,
                        callback=_consolidate_named,
                    )
                    logger.info("Scheduled pillar task: %s (consolidate)", name)
                    continue

                query = str(raw.get("query") or "").strip()
                if not query:
                    logger.warning(
                        "Scheduled task %s skipped — need query or action",
                        name,
                    )
                    continue
                user_id = raw.get("user_id")
                user_id_str = str(user_id) if user_id not in (None, "") else None
                max_it = int(raw.get("max_iterations") or 10)
                sched_spec: dict[str, Any] = {
                    "query": query,
                    "context": raw.get("context"),
                    "tools": raw.get("tools"),
                    "conversation_id": raw.get("conversation_id"),
                    "reasoning_effort": raw.get("reasoning_effort"),
                }

                async def _run_enqueued(
                    jname: str = name,
                    uid: Optional[str] = user_id_str,
                    mit: int = max_it,
                    spec: dict[str, Any] = sched_spec,
                ) -> None:
                    task_id = str(uuid.uuid4())
                    q = spec["query"]
                    if _db.db_pool:
                        try:
                            await execute(
                                """
                                INSERT INTO tasks (id, user_id, query, status, cost, created_at)
                                VALUES ($1, $2, $3, 'queued', 0, $4)
                                ON CONFLICT (id) DO NOTHING
                                """,
                                task_id,
                                uid,
                                q,
                                datetime.utcnow(),
                            )
                        except Exception as e:
                            logger.warning(
                                "Scheduled task %s: could not insert task row: %s",
                                jname,
                                e,
                            )
                    await self.enqueue_task(
                        {
                            "task_id": task_id,
                            "query": q,
                            "context": spec.get("context"),
                            "tools": spec.get("tools"),
                            "user_id": uid,
                            "max_iterations": mit,
                            "conversation_id": spec.get("conversation_id"),
                            "reasoning_effort": spec.get("reasoning_effort"),
                        }
                    )
                    logger.info(
                        "Scheduled pillar task %s enqueued as %s", jname, task_id
                    )

                self.add_interval_job(
                    name=f"user:{name}",
                    interval_seconds=interval,
                    callback=_run_enqueued,
                )
                logger.info("Scheduled pillar task: %s (deferred agent run)", name)

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
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception as e:
                logger.debug("Redis close: %s", e)
            self._redis = None

    def _dead_letter_enabled(self) -> bool:
        from app.utils.pillar_loader import get_pillar_config

        eh = (get_pillar_config().get("orchestration") or {}).get(
            "error_handling"
        ) or {}
        dl = eh.get("dead_letter") or {}
        return bool(dl.get("enabled"))

    async def _persist_failed_task(self, payload: dict[str, Any], error: str) -> None:
        if not self._dead_letter_enabled() or not _db.db_pool:
            return
        task_id = payload.get("task_id")
        try:
            await execute(
                """
                INSERT INTO failed_tasks (task_id, error, payload)
                VALUES ($1::uuid, $2, $3::jsonb)
                """,
                task_id if task_id else None,
                error[:8000],
                json.dumps(payload, default=str),
            )
        except Exception as e:
            logger.warning("failed_tasks insert failed: %s", e)

    async def _next_payload(self) -> dict[str, Any] | None:
        if self._redis is not None:
            item = await self._redis.brpop(self._redis_key, timeout=1)
            if not item:
                return None
            _, raw = item
            try:
                return json.loads(raw)
            except json.JSONDecodeError as e:
                logger.warning("Bad JSON in Redis queue: %s", e)
                return None
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return None

    async def _queue_worker(self) -> None:
        while self._running:
            payload = await self._next_payload()
            if payload is None:
                continue
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
                err = str(e)
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
                        err[:10000],
                        datetime.utcnow(),
                        elapsed,
                    )
                await self._persist_failed_task(payload, err)
                self.emit_event("task_failed", {"error": err})
            finally:
                if self._redis is None:
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
                    job["next_run_at"] = now + timedelta(
                        seconds=job["interval_seconds"]
                    )
            await asyncio.sleep(1)

    async def _dispatch_due_scheduled_tasks(self) -> None:
        """Enqueue agent runs for due rows in ``scheduled_tasks`` (DB optional)."""
        if not _db.db_pool:
            return
        try:
            from croniter import croniter
        except ImportError:
            logger.warning("croniter not installed — user schedules disabled")
            return

        try:
            rows = await fetch("""
                SELECT id, user_id, cron_expr, prompt, context, max_iterations, router_tier
                FROM scheduled_tasks
                WHERE enabled = true AND next_run_at <= NOW()
                ORDER BY next_run_at ASC
                LIMIT 10
                """)
        except Exception as e:
            logger.debug("scheduled_tasks query skipped: %s", e)
            return

        now = datetime.utcnow()
        for row in rows:
            sid = row["id"]
            uid = row["user_id"]
            cron_expr = row["cron_expr"]
            prompt = row["prompt"]
            ctx = row["context"]
            max_it = int(row["max_iterations"] or 10)
            router_tier = row["router_tier"]
            try:
                next_run = croniter(cron_expr, now).get_next(datetime)
            except Exception as e:
                logger.warning("Invalid cron for schedule %s: %s", sid, e)
                continue

            task_id = str(uuid.uuid4())
            meta = {"scheduled_task_id": str(sid), "router_tier": router_tier}
            try:
                await execute(
                    """
                    INSERT INTO tasks (id, user_id, query, status, cost, created_at, metadata)
                    VALUES ($1, $2, $3, 'queued', 0, $4, $5::jsonb)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    task_id,
                    uid,
                    prompt,
                    now,
                    json.dumps(meta, default=str),
                )
            except Exception as e:
                logger.warning("Schedule %s: task insert failed: %s", sid, e)
                continue

            await self.enqueue_task(
                {
                    "task_id": task_id,
                    "query": prompt,
                    "context": ctx,
                    "tools": None,
                    "user_id": uid,
                    "max_iterations": max_it,
                    "conversation_id": None,
                    "reasoning_effort": None,
                }
            )

            try:
                await execute(
                    """
                    UPDATE scheduled_tasks
                    SET last_run_at = $2, next_run_at = $3, updated_at = NOW()
                    WHERE id = $1
                    """,
                    sid,
                    now,
                    next_run,
                )
            except Exception as e:
                logger.warning("Schedule %s: next_run update failed: %s", sid, e)
