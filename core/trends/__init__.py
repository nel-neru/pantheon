"""Trend intelligence — collect, dedup, score, and surface external trends.

Pantheon ingests trends from free sources (web articles/RSS, YouTube captions,
X timeline) to fuel content jobs and new-business proposals. Collection only
fetches public HTTP and summarises via the local ``claude`` CLI — no hosted-LLM
API keys, no paid trend APIs. State lives under ``~/.pantheon/trends/``.
"""

from __future__ import annotations

from core.trends.models import TrendItem
from core.trends.store import TrendStore

__all__ = ["TrendItem", "TrendStore"]
