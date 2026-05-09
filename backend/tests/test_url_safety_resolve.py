"""URL safety branches that depend on socket behavior (mocked)."""

import socket
from unittest.mock import MagicMock

import pytest

from app.utils import url_safety as us
from app.utils.url_safety import validate_agent_outbound_url


def test_literal_ip_helpers():
    assert us._literal_ip("example.com") is None
    v4 = us._literal_ip("8.8.8.8")
    assert v4 is not None and v4.version == 4


def test_host_resolve_gaierror(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        MagicMock(side_effect=socket.gaierror("fail")),
    )
    ok, msg = us._host_resolves_only_to_global_ips("ghost.invalid")
    assert ok is False
    assert "could not resolve" in msg


def test_host_resolve_empty_results(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", MagicMock(return_value=[]))
    ok, msg = us._host_resolves_only_to_global_ips("empty.invalid")
    assert ok is False
    assert "did not resolve" in msg


@pytest.mark.parametrize(
    "ip,is_ok",
    [
        ("10.0.0.5", False),
        ("151.101.1.140", True),
    ],
)
def test_host_resolve_seen_ips(monkeypatch, ip, is_ok):
    info = [(None, None, None, None, (ip, 0)), (None, None, None, None, (ip, 0))]
    monkeypatch.setattr(socket, "getaddrinfo", MagicMock(return_value=info))

    ok, _msg = us._host_resolves_only_to_global_ips("dup.example.test")
    assert ok is is_ok


def test_validate_url_blocks_blocked_names_and_zero():
    ok, _ = validate_agent_outbound_url("http://metadata/v1/")
    assert ok is False
    ok2, _ = validate_agent_outbound_url("http://0.0.0.0:8080/")
    assert ok2 is False


@pytest.mark.parametrize("host", ["blog.example.org", "docs.python.org"])
def test_validate_dns_host_accepted_when_global(monkeypatch, host):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        MagicMock(return_value=[(None, None, None, None, ("1.1.1.1", 0))]),
    )

    ok, reason = validate_agent_outbound_url(f"https://{host}/path")
    assert ok is True
    assert reason == ""
