"""Minimal FetchResult mirroring the real engine's R6 contract fields.

resolve_engine.sh's smoke-test introspects these dataclass fields; keeping the
same names lets the fake engine pass the exact same contract check.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FetchResult:
    body: str = ""
    ok: bool = False
    verdict: str = ""
    grid_exhausted: bool = False
    stop_reason: str = ""
    untried_routes: list[str] = field(default_factory=list)
    must_invoke_playwright_mcp: bool = False
