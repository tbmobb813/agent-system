"""
Task Planner - Decomposes user queries into executable steps.
"""

import json
import logging
from typing import Optional, List
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PlanStep(BaseModel):
    """A single step in the execution plan."""
    step_number: int
    description: str
    action: str  # "think", "search", "code", "tool_call", "synthesize"
    requires_tools: bool = False
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    depends_on: Optional[List[int]] = None  # Step numbers this depends on
    expected_output: str


class ExecutionPlan(BaseModel):
    """A complete execution plan."""
    steps: List[PlanStep]
    original_query: str
    strategy: str  # "sequential", "parallel", "mixed"


class TaskPlanner:
    """
    Plans task execution by breaking down queries into steps.
    """
    
    async def plan(
        self,
        query: str,
        context: Optional[str] = None,
        max_steps: int = 10,
    ) -> List[PlanStep]:
        """
        Create an execution plan for a query.
        
        Returns list of steps to execute.
        """
        # Placeholder implementation
        # In production, would use LLM to generate plans
        
        plan = self._generate_plan(query, context, max_steps)
        
        logger.info(f"Generated plan with {len(plan)} steps for query: {query[:100]}")
        
        return plan
    
    def _generate_plan(
        self,
        query: str,
        context: Optional[str] = None,
        max_steps: int = 10,
    ) -> List[PlanStep]:
        """
        Simple deterministic planning based on query keywords.
        In production, this would be LLM-driven.
        """
        steps = []
        step_num = 1
        
        # Analyze query to determine steps needed
        query_lower = query.lower()
        
        # Step 1: Always analyze the query
        steps.append(PlanStep(
            step_number=step_num,
            description="Analyze the user's request and create a strategy",
            action="think",
            requires_tools=False,
            expected_output="Understanding of the task requirements",
        ))
        step_num += 1
        
        # Step 2: Search if needed
        if any(word in query_lower for word in ["search", "find", "research", "look for", "current", "latest", "news"]):
            steps.append(PlanStep(
                step_number=step_num,
                description="Search for current information relevant to the query",
                action="search",
                requires_tools=True,
                tool_name="web_search",
                tool_input={"query": query, "max_results": 5},
                expected_output="Relevant search results and information",
            ))
            step_num += 1
        
        # Step 3: Code if needed
        if any(word in query_lower for word in ["code", "write", "implement", "function", "script", "program"]):
            steps.append(PlanStep(
                step_number=step_num,
                description="Write and test code to solve the problem",
                action="code",
                requires_tools=True,
                tool_name="code_execution",
                tool_input={"language": self._detect_language(query)},
                expected_output="Working code with explanation",
            ))
            step_num += 1
        
        # Step 4: Analysis if needed
        if any(word in query_lower for word in ["analyze", "compare", "explain", "how", "why", "what is"]):
            steps.append(PlanStep(
                step_number=step_num,
                description="Analyze and synthesize information to answer the question",
                action="think",
                requires_tools=False,
                expected_output="Clear analysis and explanation",
            ))
            step_num += 1
        
        # Step 5: Synthesis
        steps.append(PlanStep(
            step_number=step_num,
            description="Synthesize all results into a comprehensive final answer",
            action="synthesize",
            requires_tools=False,
            expected_output="Complete, well-structured answer to the user's query",
        ))
        
        return steps[:max_steps]  # Limit to max_steps
    
    def _detect_language(self, query: str) -> str:
        """Detect programming language from query."""
        query_lower = query.lower()
        
        languages = {
            "python": ["python", "py"],
            "javascript": ["javascript", "js", "node"],
            "typescript": ["typescript", "ts"],
            "java": ["java"],
            "cpp": ["c++", "cpp"],
            "go": ["go", "golang"],
            "rust": ["rust"],
            "sql": ["sql", "database"],
        }
        
        for lang, keywords in languages.items():
            if any(kw in query_lower for kw in keywords):
                return lang
        
        return "python"  # Default


class Plan:
    """Simpler plan representation for compatibility."""
    
    def __init__(self, steps: List[PlanStep]):
        self.steps = steps
    
    def __iter__(self):
        return iter(self.steps)
    
    def __len__(self):
        return len(self.steps)
    
    def __getitem__(self, idx):
        return self.steps[idx]
