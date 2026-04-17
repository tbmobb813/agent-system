"""
SSRF mitigation for agent-initiated outbound HTTP(S) URLs.

Used by api_call and browser_automation before connecting to a host.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata",
        "metadata.google.internal",
    }
)


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _host_resolves_only_to_global_ips(host: str) -> tuple[bool, str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return False, f"could not resolve host: {e}"
    seen: set[str] = set()
    for info in infos:
        addr = info[4]
        if not addr:
            continue
        ip_str = addr[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if not ip.is_global:
            return False, f"host resolves to non-public address: {ip_str}"
    if not seen:
        return False, "host did not resolve to any usable address"
    return True, ""


def validate_agent_outbound_url(url: str) -> tuple[bool, str]:
    """
    Return (True, "") if the URL is allowed for agent tools, else (False, reason).

    Blocks non-http(s) schemes, missing hosts, obvious metadata / loopback
    names, literal non-global IPs, and hostnames whose DNS resolves only to
    addresses where ipaddress.is_global is False.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:  # pragma: no cover - urlparse rarely fails
        return False, f"invalid URL: {e}"

    if parsed.scheme not in ("http", "https"):
        return False, "URL must start with http:// or https://"

    host = parsed.hostname
    if not host:
        return False, "URL must include a host"

    h = host.lower()
    if h in _BLOCKED_HOSTNAMES:
        return False, "host is not allowed"
    if h == "0.0.0.0":
        return False, "host is not allowed"

    lit = _literal_ip(host)
    if lit is not None:
        if not lit.is_global:
            return False, "non-public IP addresses are not allowed"
        return True, ""

    ok, msg = _host_resolves_only_to_global_ips(host)
    if not ok:
        return False, msg or "host failed SSRF checks"
    return True, ""
