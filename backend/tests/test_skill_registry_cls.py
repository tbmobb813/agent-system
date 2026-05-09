"""Keyword classification for skill registry."""

from app.agent.skill_registry import classify_query


def test_classify_coding():
    assert classify_query("Fix the python bug in my unittest") == "coding"


def test_classify_automation():
    assert classify_query("automate this webhook cron pipeline") == "automation"


def test_classify_general_fallback():
    assert classify_query("random words") == "general"


def test_classify_research_before_general():
    assert classify_query("explain quantum physics briefly") == "research"
