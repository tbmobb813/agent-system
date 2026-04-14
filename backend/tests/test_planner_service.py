from app.agent.planner import TaskPlanner


def test_generate_plan_always_starts_with_analysis_and_ends_with_synthesis():
    planner = TaskPlanner()

    plan = planner._generate_plan("Summarize this topic")

    assert len(plan) >= 2
    assert plan[0].action == "think"
    assert "Analyze" in plan[0].description
    assert plan[-1].action == "synthesize"


def test_generate_plan_adds_search_and_code_steps_when_query_requires_both():
    planner = TaskPlanner()

    plan = planner._generate_plan("Search latest Python news and write a script to parse it")

    actions = [step.action for step in plan]
    tool_names = [step.tool_name for step in plan if step.tool_name]

    assert "search" in actions
    assert "code" in actions
    assert "web_search" in tool_names
    assert "code_execution" in tool_names


async def test_plan_respects_max_steps_limit():
    planner = TaskPlanner()

    plan = await planner.plan("Search and write code and explain why", max_steps=3)

    assert len(plan) <= 3