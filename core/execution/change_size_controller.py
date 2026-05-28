"""
ChangeSizeController — 変更サイズ制御 (F-09)
"""

from __future__ import annotations

import re
from itertools import zip_longest


class ChangeSizeController:
    MAX_LINES_PER_CHANGE = 100

    def estimate_change_lines(self, before: str, after: str) -> int:
        return sum(
            1
            for old, new in zip_longest(before.splitlines(), after.splitlines(), fillvalue="")
            if old != new
        )

    def should_split(self, before: str, after: str) -> bool:
        return self.estimate_change_lines(before, after) > self.MAX_LINES_PER_CHANGE

    def split_proposal_hint(self, description: str) -> list[str]:
        chunks = [chunk.strip() for chunk in description.split("\n\n") if chunk.strip()]
        if len(chunks) >= 2:
            return chunks[:3]

        sentences = [s.strip() for s in re.split(r"(?<=[。.!?])\s+", description) if s.strip()]
        if len(sentences) >= 2:
            return sentences[:3]

        text = description.strip() or "Change proposal"
        midpoint = max(1, len(text) // 2)
        split_at = text.find(" ", midpoint)
        if split_at == -1:
            split_at = midpoint
        return [text[:split_at].strip(), text[split_at:].strip() or text]
