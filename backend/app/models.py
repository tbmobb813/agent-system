"""
Pydantic models for the AI agent system.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any, Literal
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
    THINKING = "thinking"
    ERROR = "error"
    DONE = "done"
    CONTEXT = "context"


class AgentRequest(BaseModel):
    """Request to execute an agent task."""
    query: str = Field(..., description="Main task/question for the agent")
    context: Optional[str] = Field(None, description="Additional context")
    tools: Optional[list[str]] = Field(
        default=None,
        description="Specific tools to use (None = all available)"
    )
    max_iterations: int = Field(default=10, description="Max planning/execution steps")
    user_id: Optional[str] = Field(None, description="User identifier")
    conversation_id: Optional[str] = Field(None, description="Continue an existing conversation")
    metadata: Optional[dict] = Field(default_factory=dict, description="Custom metadata")


class ExecutionEvent(BaseModel):
    """Single event during agent execution."""
    type: EventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    content: Optional[str] = None
    model: Optional[str] = None
    tokens: Optional[dict] = Field(
        None,
        description="{'input': int, 'output': int}"
    )
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
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    preferred_model: Optional[str] = None
    max_monthly_cost: float = Field(default=30.0)
    enable_notifications: bool = Field(default=True)
    auto_save_results: bool = Field(default=True)
    context_window_target_percent: float = Field(default=0.75)
    default_tools: Optional[list[str]] = None
    timezone: str = Field(default="UTC")
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
