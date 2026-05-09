import pytest

from app.agent import workflows
from app.agent.workflows import run_named_workflow


class _FakeTools:
    async def call(self, name: str, **kwargs):
        if name == "boom":
            raise ValueError("tool fail")
        return {"name": name, "kwargs": kwargs}


class _FakeOrchFailRun:
    def __init__(self):
        self.tools = _FakeTools()

    async def run(self, **kwargs):
        raise RuntimeError("agent fail")


class _FakeOrchGood:
    def __init__(self):
        self.tools = _FakeTools()

    async def run(self, **kwargs):
        return "hello", kwargs.get("conversation_id") or "c1"


@pytest.mark.asyncio
async def test_run_named_workflow_invalid_steps_raises(monkeypatch):
    monkeypatch.setattr(
        workflows, "load_workflow", lambda _n: {"workflow": "bad", "steps": "no"}
    )
    with pytest.raises(ValueError, match="steps"):
        await run_named_workflow(_FakeOrchGood(), "any", user_id=None)


@pytest.mark.asyncio
async def test_run_named_workflow_tools_and_agent_paths(monkeypatch):
    monkeypatch.setattr(
        workflows,
        "load_workflow",
        lambda _: {
            "workflow": "w",
            "steps": [
                {"tool": "echo", "args": {"z": 1}},
                {"query": "q", "conversation_id": "prev"},
                {"not": "a dict step"},
                {"name": "skipme"},
                {"query": "q2"},
            ],
        },
    )
    orch = _FakeOrchGood()
    rep = await run_named_workflow(orch, "fake", user_id="u1")
    assert rep["workflow"] == "w"
    assert rep["steps"]["skipme"]["skipped"] is True
    assert rep["steps"]["step_4"]["result"] == "hello"


@pytest.mark.asyncio
async def test_run_named_workflow_tool_and_agent_errors(monkeypatch):
    monkeypatch.setattr(
        workflows,
        "load_workflow",
        lambda _: {
            "workflow": "w",
            "steps": [
                {"name": "t_fail", "tool": "boom"},
                {"name": "a_fail", "query": "x"},
            ],
        },
    )
    orch = _FakeOrchFailRun()
    rep = await run_named_workflow(orch, "fake", user_id=None)
    assert "error" in rep["steps"]["t_fail"]
    assert "error" in rep["steps"]["a_fail"]
