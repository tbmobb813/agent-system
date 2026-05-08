"""Workflow YAML loading (no live LLM calls)."""

from app.agent import workflows


def test_load_example_workflow():
    data = workflows.load_workflow("example")
    assert data.get("workflow") == "example"
    assert isinstance(data.get("steps"), list)
    assert len(data["steps"]) >= 1


def test_invalid_workflow_name_rejected():
    try:
        workflows.load_workflow("../etc/passwd")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
