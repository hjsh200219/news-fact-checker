"""Contract tests for the network-destination policy (url_policy.py)."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
UP = SCRIPTS / "url_policy.py"

_spec = importlib.util.spec_from_file_location("url_policy", UP)
assert _spec and _spec.loader
url_policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(url_policy)  # type: ignore[union-attr]

FAKE_MAP = {
    "news.example.com": ["93.184.216.34"],
    "internal.example.com": ["10.0.0.5"],
    "meta.example.com": ["169.254.169.254"],
    "mixed.example.com": ["93.184.216.34", "127.0.0.1"],  # one bad IP → reject all
}


def fake_resolver(host, port):
    return list(FAKE_MAP.get(host, []))


def allowed(url):
    return url_policy.classify_url(url, resolver=fake_resolver)["allowed"]


def code(url):
    return url_policy.classify_url(url, resolver=fake_resolver)["code"]


class TestUrlPolicy(unittest.TestCase):
    def test_selftest(self):
        self.assertEqual(url_policy._selftest(), 0)

    # AC-7 — refused before any network request
    def test_ac7_file_scheme(self):
        self.assertFalse(allowed("file:///etc/passwd"))
        self.assertEqual(code("file:///etc/passwd"), "BAD_SCHEME")

    def test_ac7_loopback_literal(self):
        self.assertFalse(allowed("http://127.0.0.1/x"))
        self.assertEqual(code("http://127.0.0.1/x"), "UNSAFE_ADDRESS")

    def test_ac7_metadata_literal(self):
        self.assertFalse(allowed("http://169.254.169.254/latest/meta-data/"))

    def test_ipv6_loopback(self):
        self.assertFalse(allowed("http://[::1]/x"))

    def test_ipv4_mapped_ipv6(self):
        self.assertFalse(allowed("http://[::ffff:127.0.0.1]/x"))

    def test_userinfo_forbidden(self):
        self.assertFalse(allowed("http://user:pass@news.example.com/x"))
        self.assertEqual(code("http://user@news.example.com/x"), "USERINFO_FORBIDDEN")

    def test_non_http_schemes(self):
        for u in ("gopher://news.example.com/x", "ftp://news.example.com/x",
                  "data:text/html,hi", "javascript:alert(1)"):
            self.assertFalse(allowed(u), u)

    # AC-8 — DNS re-resolution to a private/metadata address
    def test_ac8_private_via_dns(self):
        self.assertFalse(allowed("http://internal.example.com/x"))
        self.assertEqual(code("http://internal.example.com/x"), "UNSAFE_ADDRESS")

    def test_ac8_metadata_via_dns(self):
        self.assertFalse(allowed("http://meta.example.com/x"))

    def test_mixed_resolution_any_bad_rejects(self):
        self.assertFalse(allowed("http://mixed.example.com/x"))

    def test_public_host_passes(self):
        self.assertTrue(allowed("https://news.example.com/article/1"))

    def test_public_ip_literal_passes(self):
        self.assertTrue(url_policy.classify_url("http://8.8.8.8/x", resolver=fake_resolver)["allowed"])

    def test_unresolvable_fails_closed(self):
        self.assertFalse(allowed("http://nonexistent.example.com/x"))
        self.assertEqual(code("http://nonexistent.example.com/x"), "RESOLVE_EMPTY")

    def test_empty_url(self):
        self.assertFalse(allowed(""))


if __name__ == "__main__":
    unittest.main()
