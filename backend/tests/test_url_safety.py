"""Unit tests for SSRF URL validation (no outbound I/O for literal-IP cases)."""

import pytest

from app.utils.url_safety import (
    validate_agent_outbound_url,
    validate_browser_automation_host,
)


@pytest.mark.parametrize(
    "url,expect_ok",
    [
        ("http://127.0.0.1/", False),
        ("https://[::1]/", False),
        ("http://10.0.0.1/", False),
        ("http://192.168.0.1/", False),
        ("http://169.254.169.254/latest/meta-data/", False),
        ("ftp://example.com/", False),
        ("http://", False),
    ],
)
def test_validate_agent_outbound_url_rejects_bad_urls(url, expect_ok):
    ok, _reason = validate_agent_outbound_url(url)
    assert ok is expect_ok


def test_validate_agent_outbound_url_accepts_public_literal_ip():
    ok, reason = validate_agent_outbound_url("http://8.8.8.8/")
    assert ok is True
    assert reason == ""


def test_validate_browser_automation_host_empty_allowlist():
    assert validate_browser_automation_host("evil.com", "") == (True, "")
    assert validate_browser_automation_host("evil.com", "  ,  ") == (True, "")


def test_validate_browser_automation_host_suffix_rules():
    rules = "wikipedia.org,example.com"
    assert validate_browser_automation_host("en.wikipedia.org", rules)[0] is True
    assert validate_browser_automation_host("wikipedia.org", rules)[0] is True
    assert validate_browser_automation_host("example.com", rules)[0] is True
    ok, msg = validate_browser_automation_host("example.org", rules)
    assert ok is False
    assert "BROWSER_AUTOMATION" in msg
