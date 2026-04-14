"""
Streaming utilities for Server-Sent Events (SSE).
"""

import json
from typing import Any, Dict


def format_sse_event(data: Dict[str, Any]) -> str:
    """
    Format data as SSE event.
    
    Format:
    event: {event_type}
    data: {json_data}
    
    (blank line)
    """
    
    # Get event type for the SSE event: header
    event_type = data.get("type", "message")

    # Keep full data (including type) in the JSON payload so clients can read it
    lines = [
        f"event: {event_type}",
        f"data: {json.dumps(data)}",
        "",
        "",  # Double blank line — required by SSE spec to terminate event
    ]

    return "\n".join(lines)


def stream_sse(events):
    """
    Generator that yields SSE-formatted events.
    """
    for event in events:
        if isinstance(event, dict):
            yield format_sse_event(event)
        else:
            yield format_sse_event({"type": "message", "data": str(event)})


class SSEFormat:
    """
    Utility class for creating SSE events.
    """
    
    @staticmethod
    def status(message: str) -> str:
        """Status update event."""
        return format_sse_event({
            "type": "status",
            "message": message,
        })
    
    @staticmethod
    def tool_call(tool_name: str, tool_input: Dict) -> str:
        """Tool call event."""
        return format_sse_event({
            "type": "tool_call",
            "tool_name": tool_name,
            "tool_input": tool_input,
        })
    
    @staticmethod
    def tool_result(tool_name: str, result: str) -> str:
        """Tool result event."""
        return format_sse_event({
            "type": "tool_result",
            "tool_name": tool_name,
            "result": result,
        })
    
    @staticmethod
    def text_delta(content: str, model: str = None) -> str:
        """Text chunk event."""
        data = {
            "type": "text_delta",
            "content": content,
        }
        if model:
            data["model"] = model
        return format_sse_event(data)
    
    @staticmethod
    def error(error: str) -> str:
        """Error event."""
        return format_sse_event({
            "type": "error",
            "error": error,
        })
    
    @staticmethod
    def done(cost: float = None) -> str:
        """Completion event."""
        data = {"type": "done"}
        if cost is not None:
            data["cost"] = cost
        return format_sse_event(data)


# Test event generation
if __name__ == "__main__":
    # Test SSE formatting
    events = [
        {"type": "status", "message": "starting"},
        {"type": "text_delta", "content": "Hello "},
        {"type": "text_delta", "content": "world!"},
        {"type": "done", "cost": 0.05},
    ]
    
    for event in events:
        print(format_sse_event(event))
        print()
