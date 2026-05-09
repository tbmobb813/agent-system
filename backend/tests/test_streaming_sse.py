"""SSE formatting helpers."""

from app.utils.streaming import SSEFormat, format_sse_event, stream_sse


def test_format_sse_event_default_type_and_double_blank():
    s = format_sse_event({"content": "x"})
    assert "event: message" in s
    assert s.count("\n") >= 3


def test_stream_sse_dict_and_primitive():
    out = "".join(stream_sse([{"type": "done"}, "plain"]))
    assert "done" in out
    assert "plain" in out


def test_sse_format_helpers():
    assert "status" in SSEFormat.status("busy")
    assert "tool_search" in SSEFormat.tool_call("tool_search", {"q": "a"})
    assert '"tool_result"' in SSEFormat.tool_result("t", "ok")
    assert "Hello" in SSEFormat.text_delta("Hello")
    assert '"model"' in SSEFormat.text_delta("x", model="m")
    assert "bad" in SSEFormat.error("bad")
    assert "done" in SSEFormat.done()
    assert "cost" in SSEFormat.done(cost=1.23)
