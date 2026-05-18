"""
Pydantic models for the AI agent system.
"""

from pydantic import BaseModel, Field, field_validator
from datetime import UTC, datetime
from typing import Optional, Literal
from enum import Enum


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class EventType(str, Enum):
    """Types of events streamed from agent."""

    STATUS = "status"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TEXT_DELTA = "text_delta"
    # Model/vendor reasoning stream (OpenRouter reasoning_details / delta.reasoning); not orchestrator plan.
    REASONING_DELTA = "reasoning_delta"
    THINKING = "thinking"
    ERROR = "error"
    DONE = "done"
    CONTEXT = "context"


class WorkflowRunRequest(BaseModel):
    """Optional context for executing a named YAML workflow."""

    user_id: Optional[str] = Field(
        None, description="Passed through to agent/tool steps"
    )


class McpServerCreate(BaseModel):
    """Add a server entry under tools.mcp.servers in agent_pillars.yaml."""

    name: str = Field(..., min_length=1, max_length=80)
    transport: Literal["http_json", "sse", "stdio"] = Field(default="http_json")
    url: Optional[str] = Field(default=None, max_length=2000)
    command: Optional[str] = Field(default=None, max_length=300)
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None


class McpServerUpdate(BaseModel):
    """Update an existing MCP server entry in tools.mcp.servers."""

    transport: Literal["http_json", "sse", "stdio"] = Field(default="http_json")
    url: Optional[str] = Field(default=None, max_length=2000)
    command: Optional[str] = Field(default=None, max_length=300)
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None


class McpServerTest(BaseModel):
    """Validate and probe an MCP server config without persisting it."""

    transport: Literal["http_json", "sse", "stdio"] = Field(default="http_json")
    url: Optional[str] = Field(default=None, max_length=2000)
    command: Optional[str] = Field(default=None, max_length=300)
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None


class ScheduledTaskCreate(BaseModel):
    """Create a cron-driven deferred agent run."""

    cron: str = Field(
        ...,
        max_length=120,
        description="5-field cron (minute hour day month weekday), e.g. '0 9 * * *'",
    )
    prompt: str = Field(..., max_length=32_000)
    context: Optional[str] = Field(
        None, description="Optional extra context for the run"
    )
    user_id: Optional[str] = Field(None, description="Owner id (stored on task rows)")
    router_tier: Optional[str] = Field(
        None, description="Optional hint stored in task metadata for analytics"
    )
    max_iterations: int = Field(default=10, ge=1, le=50)
    enabled: bool = True


class AgentRequest(BaseModel):
    """Request to execute an agent task."""

    query: str = Field(
        ..., max_length=32_000, description="Main task/question for the agent"
    )
    context: Optional[str] = Field(None, description="Additional context")
    tools: Optional[list[str]] = Field(
        default=None, description="Specific tools to use (None = all available)"
    )
    max_iterations: int = Field(default=10, description="Max planning/execution steps")
    user_id: Optional[str] = Field(None, description="User identifier")
    conversation_id: Optional[str] = Field(
        None, description="Continue an existing conversation"
    )
    metadata: Optional[dict] = Field(
        default_factory=dict, description="Custom metadata"
    )
    images: Optional[list[str]] = Field(
        default=None,
        description="Base64 data URLs (data:image/...;base64,...) for vision input",
        max_length=4,
    )
    reasoning_effort: Optional[str] = Field(
        default=None,
        description=(
            "OpenRouter reasoning effort override: off disables extra_body; "
            "minimal|low|medium|high|xhigh|none set reasoning.effort; omit for OPENROUTER_REASONING_EFFORT env default."
        ),
    )

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def normalize_reasoning_effort(cls, v: object) -> Optional[str]:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError("reasoning_effort must be a string or null")
        s = v.strip().lower()
        if s in ("disable",):
            s = "off"
        allowed = frozenset(
            {"off", "minimal", "low", "medium", "high", "xhigh", "none"}
        )
        if s not in allowed:
            raise ValueError(
                "reasoning_effort must be one of: off, minimal, low, medium, high, xhigh, none "
                "(or omit for server env default)"
            )
        return s


class ExecutionEvent(BaseModel):
    """Single event during agent execution."""

    type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content: Optional[str] = None
    model: Optional[str] = None
    tokens: Optional[dict] = Field(None, description="{'input': int, 'output': int}")
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_result: Optional[str] = None
    error: Optional[str] = None
    conversation_id: Optional[str] = None
    context_tokens_used: Optional[int] = None
    context_tokens_max: Optional[int] = None
    context_percent: Optional[float] = None


class AgentResponse(BaseModel):
    """Response from agent execution."""

    query: str
    result: str
    status: TaskStatus
    cost: float = Field(description="Cost in USD")
    model_used: Optional[str] = None
    tokens: Optional[dict] = None
    execution_time: float = Field(default=0.0, description="Seconds")
    conversation_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CostStatus(BaseModel):
    """Budget and cost status."""

    budget: float = Field(description="Monthly budget in USD")
    spent_month: float = Field(description="Total spent this month")
    spent_today: float = Field(description="Total spent today")
    remaining: float = Field(description="Remaining budget")
    percent_used: float = Field(description="0-100%")
    status: Literal["ok", "warning", "exceeded"]
    reset_date: str = Field(description="ISO datetime of next reset")


class Settings(BaseModel):
    """User settings and preferences."""

    display_name: Optional[str] = Field(
        default=None,
        max_length=80,
        description="First name or nickname for dashboard greetings.",
    )
    preferred_model: Optional[str] = None
    max_monthly_cost: float = Field(default=30.0)
    enable_notifications: bool = Field(default=True)
    auto_save_results: bool = Field(default=True)
    context_window_target_percent: float = Field(default=0.75)
    default_tools: Optional[list[str]] = None
    timezone: str = Field(default="UTC")
    agent_persona_enabled: bool = Field(default=True)
    agent_persona_path: str = Field(default="data/persona")
    agent_show_thinking_while_streaming: bool = Field(
        default=True,
        description="When true, show planning/status/thinking before the assistant reply in the chat transcript.",
    )
    metadata: dict = Field(default_factory=dict)


class ToolDefinition(BaseModel):
    """Definition of an available tool."""

    name: str
    description: str
    input_schema: dict
    output_type: str
    enabled: bool = True
    requires_auth: bool = False


class TaskRecord(BaseModel):
    """Stored task record."""

    id: str
    user_id: Optional[str] = None
    query: str
    result: Optional[str] = None
    status: TaskStatus
    cost: float
    model_used: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    execution_time: Optional[float] = None


class TaskStep(BaseModel):
    """Single step in task execution."""

    step_number: int
    action: str
    tool_used: Optional[str] = None
    input: Optional[dict] = None
    output: Optional[str] = None
    status: TaskStatus
    timestamp: datetime


class Memory(BaseModel):
    """Long-term memory entry."""

    id: str
    user_id: str
    category: str  # "preference", "fact", "pattern", "context"
    content: str
    embedding: Optional[list[float]] = None
    created_at: datetime
    accessed_at: datetime
    relevance_score: float = Field(default=1.0)


class ApiKey(BaseModel):
    """API key for authentication."""

    key: str
    user_id: str
    created_at: datetime
    last_used: Optional[datetime] = None
    is_active: bool = True
    name: Optional[str] = None
