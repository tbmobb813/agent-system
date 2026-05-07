"""
Sub-agent helper for agent-as-tool delegation.
"""

from __future__ import annotations

from typing import Any, Optional

from app.agent.orchestrator import AgentOrchestrator


class SubAgentRunner:
    def __init__(self, orchestrator: AgentOrchestrator, max_depth: int = 2):
        self.orchestrator = orchestrator
        self.max_depth = max_depth

    async def run(
        self,
        *,
        query: str,
        user_id: Optional[str] = None,
        depth: int = 1,
    ) -> dict[str, Any]:
        return await self.orchestrator.run_sub_agent(
            query=query,
            user_id=user_id,
            depth=depth,
            max_depth=self.max_depth,
        )
