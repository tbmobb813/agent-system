import pytest

from app.agent.sub_agent import SubAgentRunner


@pytest.mark.asyncio
async def test_sub_agent_runner_delegates():
    captured: dict[str, object] = {}

    class _Orch:
        async def run_sub_agent(self, **kwargs):
            captured.update(kwargs)
            return {"ok": True}

    r = SubAgentRunner(_Orch(), max_depth=7)
    out = await r.run(query="hello", user_id="u1", depth=3)
    assert out["ok"] is True
    assert captured["query"] == "hello"
    assert captured["user_id"] == "u1"
    assert captured["depth"] == 3
    assert captured["max_depth"] == 7
