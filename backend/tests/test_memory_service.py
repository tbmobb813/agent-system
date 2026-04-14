from app.agent.memory import _classify_insight


def test_classify_insight_recognizes_preference_keywords():
    assert _classify_insight("user prefers Python to JavaScript") == "preference"
    assert _classify_insight("user likes dark mode") == "preference"
    assert _classify_insight("user wants concise answers") == "preference"


def test_classify_insight_recognizes_pattern_keywords():
    assert _classify_insight("user always uses async code") == "pattern"
    assert _classify_insight("user never works on weekends") == "pattern"
    assert _classify_insight("user usually asks for examples") == "pattern"


def test_classify_insight_recognizes_fact_keywords():
    assert _classify_insight("my project is called ReGrabber") == "fact"
    assert _classify_insight("i'm a software engineer") == "fact"
    assert _classify_insight("i am building an app") == "fact"


def test_classify_insight_defaults_to_fact_for_unknown():
    assert _classify_insight("some random text") == "fact"
    assert _classify_insight("hello world") == "fact"
