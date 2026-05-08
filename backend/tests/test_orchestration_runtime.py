import asyncio
import sys
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

import app.agent.orchestration_runtime as rt_mod
from app.agent.orchestration_runtime import OrchestrationRuntime


class _NoopOrchestrator:
    async def run(self, **kwargs):
        return "ok", kwargs.get("conversation_id")


class _FailingOrchestrator:
    async def run(self, **kwargs):
        raise RuntimeError("boom")


class _FakeRedis:
    def __init__(self):
        self.lpush_calls: list[tuple[str, str]] = []
        self.llen_value = 0

    async def lpush(self, key: str, value: str):
        self.lpush_calls.append((key, value))

    async def llen(self, key: str):
        return self.llen_value


class _CronStub:
    def __init__(self, expr: str, base: datetime):
        self.expr = expr
        self.base = base

    def get_next(self, _typ):
        if self.expr == "bad":
            raise ValueError("invalid cron")
        return self.base


@pytest.mark.asyncio
async def test_enqueue_task_uses_asyncio_queue_when_redis_disabled():
    runtime = OrchestrationRuntime(_NoopOrchestrator())
    payload = {"task_id": str(uuid.uuid4()), "query": "hello"}

    await runtime.enqueue_task(payload)

    queued = await asyncio.wait_for(runtime.queue.get(), timeout=0.1)
    assert queued == payload


@pytest.mark.asyncio
async def test_enqueue_task_uses_redis_when_available():
    runtime = OrchestrationRuntime(_NoopOrchestrator())
    fake = _FakeRedis()
    runtime._redis = fake
    runtime._redis_key = "agent:deferred_tasks:test"

    await runtime.enqueue_task({"task_id": str(uuid.uuid4()), "query": "hello"})

    assert len(fake.lpush_calls) == 1
    key, value = fake.lpush_calls[0]
    assert key == "agent:deferred_tasks:test"
    assert '"query": "hello"' in value


@pytest.mark.asyncio
async def test_pending_queue_size_reads_redis_when_available():
    runtime = OrchestrationRuntime(_NoopOrchestrator())
    fake = _FakeRedis()
    fake.llen_value = 7
    runtime._redis = fake
    runtime._redis_key = "agent:deferred_tasks:test"

    size = await runtime.pending_queue_size()

    assert size == 7


@pytest.mark.asyncio
async def test_queue_worker_persists_failed_task_when_dead_letter_enabled(monkeypatch):
    runtime = OrchestrationRuntime(_FailingOrchestrator())
    runtime._running = True
    runtime._redis = object()  # skip asyncio queue.task_done() path in finally
    payload = {"task_id": str(uuid.uuid4()), "query": "explode"}

    calls: list[tuple[str, tuple]] = []

    async def _fake_execute(query: str, *args):
        calls.append((query, args))
        return "OK"

    async def _next_payload_once():
        runtime._running = False
        return payload

    events: list[tuple[str, dict]] = []

    def _emit(event: str, data: dict):
        events.append((event, data))

    monkeypatch.setattr(rt_mod, "execute", _fake_execute)
    monkeypatch.setattr(rt_mod._db, "db_pool", object())
    monkeypatch.setattr(runtime, "_next_payload", _next_payload_once)
    monkeypatch.setattr(runtime, "_dead_letter_enabled", lambda: True)
    monkeypatch.setattr(runtime, "emit_event", _emit)

    await runtime._queue_worker()

    assert any("UPDATE tasks" in q and "status = 'running'" in q for q, _ in calls)
    assert any("UPDATE tasks" in q and "status = 'failed'" in q for q, _ in calls)
    assert any("INSERT INTO failed_tasks" in q for q, _ in calls)
    assert any(evt == "task_failed" for evt, _ in events)


@pytest.mark.asyncio
async def test_dispatch_due_scheduled_tasks_no_db_pool_noop(monkeypatch):
    runtime = OrchestrationRuntime(_NoopOrchestrator())
    monkeypatch.setattr(rt_mod._db, "db_pool", None)

    await runtime._dispatch_due_scheduled_tasks()


@pytest.mark.asyncio
async def test_dispatch_due_scheduled_tasks_enqueues_and_updates(monkeypatch):
    runtime = OrchestrationRuntime(_NoopOrchestrator())
    monkeypatch.setattr(rt_mod._db, "db_pool", object())
    monkeypatch.setitem(sys.modules, "croniter", SimpleNamespace(croniter=_CronStub))

    sid = uuid.uuid4()
    uid = str(uuid.uuid4())
    rows = [
        {
            "id": sid,
            "user_id": uid,
            "cron_expr": "*/5 * * * *",
            "prompt": "daily brief",
            "context": "ctx",
            "max_iterations": 6,
            "router_tier": "simple",
        }
    ]

    async def _fake_fetch(_query: str):
        return rows

    calls: list[tuple[str, tuple]] = []

    async def _fake_execute(query: str, *args):
        calls.append((query, args))
        return "OK"

    enqueued: list[dict] = []

    async def _fake_enqueue(payload: dict):
        enqueued.append(payload)

    monkeypatch.setattr(rt_mod, "fetch", _fake_fetch)
    monkeypatch.setattr(rt_mod, "execute", _fake_execute)
    monkeypatch.setattr(runtime, "enqueue_task", _fake_enqueue)

    await runtime._dispatch_due_scheduled_tasks()

    assert len(enqueued) == 1
    assert enqueued[0]["query"] == "daily brief"
    assert enqueued[0]["user_id"] == uid
    assert any("INSERT INTO tasks" in q for q, _ in calls)
    assert any("UPDATE scheduled_tasks" in q for q, _ in calls)


@pytest.mark.asyncio
async def test_dispatch_due_scheduled_tasks_skips_invalid_cron(monkeypatch):
    runtime = OrchestrationRuntime(_NoopOrchestrator())
    monkeypatch.setattr(rt_mod._db, "db_pool", object())
    monkeypatch.setitem(sys.modules, "croniter", SimpleNamespace(croniter=_CronStub))

    rows = [
        {
            "id": uuid.uuid4(),
            "user_id": str(uuid.uuid4()),
            "cron_expr": "bad",
            "prompt": "daily brief",
            "context": None,
            "max_iterations": 6,
            "router_tier": "simple",
        }
    ]

    async def _fake_fetch(_query: str):
        return rows

    calls: list[tuple[str, tuple]] = []

    async def _fake_execute(query: str, *args):
        calls.append((query, args))
        return "OK"

    monkeypatch.setattr(rt_mod, "fetch", _fake_fetch)
    monkeypatch.setattr(rt_mod, "execute", _fake_execute)

    await runtime._dispatch_due_scheduled_tasks()

    assert calls == []
