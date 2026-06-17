"""Cross-org playbook propagation (C6).

A play that earned a high ``usefulness_score`` in one org is proposed for orgs that
lack it, so a win in org A can lift orgs B/C. Two clean halves:

- :func:`propose_propagations` — **read-only**: ranks each named org's top plays and
  emits a candidate for every other org that doesn't already have that (title, category).
- :func:`apply_propagation` / :func:`apply_propagations` — **gated + idempotent** write
  via :meth:`MemoryBank.capture` (dedupes on title/category/org, so re-applying is a no-op).

The default flow is dry-run (``propose`` only); writing requires an explicit human action
(the CLI ``--apply`` flag) — the Human-in-the-Loop gate kept for cross-boundary writes.
A propagated copy is created at ``usefulness_score=0`` (capture→add default), so it falls
below ``min_usefulness`` and is never itself re-propagated — propagation converges.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from core.intelligence.playbook import PlaybookStore

logger = logging.getLogger(__name__)


def _norm_title(title: str) -> str:
    # Match MemoryBank.capture's idempotency key (it compares str(title).strip()).
    return str(title).strip()


@dataclass
class PropagationCandidate:
    title: str
    content: str
    category: str
    source_org: str
    target_org: str
    usefulness_score: float

    def to_dict(self) -> dict:
        return asdict(self)


def propose_propagations(
    *,
    platform_home: Optional[Path] = None,
    min_usefulness: float = 1.0,
    top_per_org: int = 5,
) -> List[PropagationCandidate]:
    """Read-only: high-usefulness plays present in one named org but missing from another.

    Only NAMED orgs participate (``org_name == ""`` global plays are neither source nor
    target). Deterministic ordering (usefulness desc, then target/title).
    """
    store = PlaybookStore(platform_home)
    entries = store.list_entries()

    by_org: dict[str, list] = {}
    for e in entries:
        if e.org_name:  # skip unnamed/global plays
            by_org.setdefault(e.org_name, []).append(e)

    # (org, category, normalized-title) the org already has — mirrors capture's dedupe key.
    have = {(e.org_name, e.category, _norm_title(e.title)) for e in entries if e.org_name}
    orgs = list(by_org.keys())

    candidates: List[PropagationCandidate] = []
    seen: set = set()
    for src_org, plays in by_org.items():
        ranked = sorted(plays, key=lambda e: e.usefulness_score, reverse=True)
        promoted = [e for e in ranked if e.usefulness_score >= min_usefulness][
            : max(0, top_per_org)
        ]
        for e in promoted:
            for tgt_org in orgs:
                if tgt_org == src_org:
                    continue
                key = (tgt_org, e.category, _norm_title(e.title))
                if key in have or key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    PropagationCandidate(
                        title=e.title,
                        content=e.content,
                        category=e.category,
                        source_org=src_org,
                        target_org=tgt_org,
                        usefulness_score=e.usefulness_score,
                    )
                )

    candidates.sort(key=lambda c: (-c.usefulness_score, c.target_org, c.title))
    return candidates


def apply_propagation(candidate: PropagationCandidate, *, platform_home: Optional[Path] = None):
    """Gated write: add the play into the target org (idempotent; records provenance)."""
    from core.intelligence.memory_bank import MemoryBank

    mb = MemoryBank(platform_home)
    content = f"{candidate.content}\n\n[伝播元 org: {candidate.source_org}]"
    return mb.capture(
        candidate.title,
        content,
        category=candidate.category,
        org_name=candidate.target_org,
    )


def apply_propagations(
    candidates: List[PropagationCandidate], *, platform_home: Optional[Path] = None
) -> int:
    """Apply a list of candidates; returns the count applied. Best-effort per item —
    a single failure does not abort the batch, but failures are OBSERVED (logged), not
    silently dropped (repo convention: silent drops skew metrics — make them a signal)."""
    applied = 0
    skipped = 0
    for candidate in candidates:
        try:
            apply_propagation(candidate, platform_home=platform_home)
            applied += 1
        except Exception as exc:
            skipped += 1
            logger.warning(
                "playbook propagation skipped %s→%s '%s': %s",
                candidate.source_org,
                candidate.target_org,
                candidate.title,
                exc,
            )
    if skipped:
        logger.warning("playbook propagation: %d of %d candidates failed", skipped, len(candidates))
    return applied
