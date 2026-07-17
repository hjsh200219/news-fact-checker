#!/usr/bin/env python3
"""url_policy.py — network-destination policy for the fetch boundary (FR-4).

The product scope is *public news URLs*. This module rejects everything that a
public news fetch has no business reaching, BEFORE any network request is made:

  * non-HTTP(S) schemes (file://, ftp://, gopher://, data:, ...)
  * URLs carrying userinfo  (http://user:pass@host, http://evil@host)
  * hosts that resolve to loopback / link-local / private / reserved / multicast
    / unspecified addresses, and the cloud metadata endpoint 169.254.169.254

Host resolution is injectable so the same policy runs against redirect targets
and DNS re-resolution, and so tests never touch the network. When an IP literal
is supplied as the host, it is checked directly with no lookup.

CLI:
  url_policy.py <url>
    stdout : JSON {allowed, reason, code, scheme, host, port, resolved_ips}
    exit   : 0 allowed · 1 rejected · 2 usage error

Library:
  classify_url(url, resolver=...) -> dict   (same shape as the CLI JSON)
"""
from __future__ import annotations

import ipaddress
import json
import socket
import sys
from typing import Any, Callable
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")

# Explicit deny even though most are covered by ipaddress properties — kept as a
# named backstop so the intent (cloud metadata, etc.) is auditable.
_EXPLICIT_DENY = {"169.254.169.254", "fd00:ec2::254"}

Resolver = Callable[[str, int | None], list[str]]


def _default_resolver(host: str, port: int | None) -> list[str]:
    infos = socket.getaddrinfo(host, port or None, proto=socket.IPPROTO_TCP)
    ips: list[str] = []
    for family, _type, _proto, _canon, sockaddr in infos:
        ip = str(sockaddr[0])
        if ip not in ips:
            ips.append(ip)
    return ips


def _ip_is_unsafe(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unparseable → treat as unsafe
    if str(addr) in _EXPLICIT_DENY:
        return True
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped  # unwrap ::ffff:127.0.0.1 style
    return bool(
        addr.is_loopback
        or addr.is_link_local
        or addr.is_private
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _result(allowed: bool, reason: str, code: str, *, scheme: str = "", host: str = "",
            port: int | None = None, resolved_ips: list[str] | None = None) -> dict[str, Any]:
    return {
        "allowed": allowed,
        "reason": reason,
        "code": code,
        "scheme": scheme,
        "host": host,
        "port": port,
        "resolved_ips": resolved_ips or [],
    }


def classify_url(url: str, resolver: Resolver | None = None) -> dict[str, Any]:
    resolver = resolver or _default_resolver
    if not isinstance(url, str) or not url.strip():
        return _result(False, "empty url", "EMPTY_URL")

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        return _result(False, f"scheme '{scheme or '(none)'}' not allowed", "BAD_SCHEME", scheme=scheme)

    if parts.username or parts.password or "@" in (parts.netloc.rsplit("@", 1)[0] if "@" in parts.netloc else ""):
        return _result(False, "userinfo in URL not allowed", "USERINFO_FORBIDDEN", scheme=scheme)

    host = parts.hostname or ""
    if not host:
        return _result(False, "missing host", "NO_HOST", scheme=scheme)

    try:
        port = parts.port
    except ValueError:
        return _result(False, "invalid port", "BAD_PORT", scheme=scheme, host=host)

    # If the host is already an IP literal, check it directly (no lookup).
    literal = host.strip("[]")
    try:
        ipaddress.ip_address(literal)
        if _ip_is_unsafe(literal):
            return _result(False, f"address {literal} is not a public destination",
                           "UNSAFE_ADDRESS", scheme=scheme, host=host, port=port,
                           resolved_ips=[literal])
        return _result(True, "ok", "OK", scheme=scheme, host=host, port=port, resolved_ips=[literal])
    except ValueError:
        pass  # not an IP literal → resolve

    try:
        ips = resolver(host, port)
    except Exception as e:  # DNS failure → fail closed (no fetch)
        return _result(False, f"host resolution failed: {type(e).__name__}",
                       "RESOLVE_FAILED", scheme=scheme, host=host, port=port)

    if not ips:
        return _result(False, "host did not resolve", "RESOLVE_EMPTY",
                       scheme=scheme, host=host, port=port)

    unsafe = [ip for ip in ips if _ip_is_unsafe(ip)]
    if unsafe:
        return _result(False, f"resolves to non-public address(es): {', '.join(unsafe)}",
                       "UNSAFE_ADDRESS", scheme=scheme, host=host, port=port, resolved_ips=ips)

    return _result(True, "ok", "OK", scheme=scheme, host=host, port=port, resolved_ips=ips)


def _selftest() -> int:
    fake_map = {
        "news.example.com": ["93.184.216.34"],       # public
        "internal.example.com": ["10.0.0.5"],        # private (SSRF via DNS)
        "meta.example.com": ["169.254.169.254"],     # cloud metadata via DNS
    }

    def fake(host: str, port: int | None) -> list[str]:
        return list(fake_map.get(host, []))

    def allow(u: str) -> bool:
        return classify_url(u, resolver=fake)["allowed"]

    # AC-7: pre-network scheme / IP-literal rejections.
    assert not allow("file:///etc/passwd"), "file:// must be rejected"
    assert not allow("http://127.0.0.1/x"), "loopback literal must be rejected"
    assert not allow("http://169.254.169.254/latest/meta-data/"), "metadata IP must be rejected"
    assert not allow("http://[::1]/x"), "IPv6 loopback must be rejected"
    assert not allow("http://user:pass@news.example.com/x"), "userinfo must be rejected"
    assert not allow("gopher://news.example.com/x"), "gopher must be rejected"
    # AC-8: allowed host that resolves to a private / metadata address.
    assert not allow("http://internal.example.com/x"), "private-resolving host must be rejected"
    assert not allow("http://meta.example.com/x"), "metadata-resolving host must be rejected"
    # Public host passes.
    assert allow("https://news.example.com/article/1"), "public host must pass"
    assert allow("https://news.example.com:443/a"), "explicit 443 must pass"

    print("url_policy.py selftest: OK")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    if len(argv) != 1:
        print(json.dumps({"allowed": False, "reason": "usage: url_policy.py <url>",
                          "code": "USAGE"}, ensure_ascii=False), file=sys.stderr)
        return 2
    res = classify_url(argv[0])
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res["allowed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
