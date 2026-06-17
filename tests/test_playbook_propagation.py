"""Tests for C6 cross-org playbook propagation (read-only propose + gated idempotent apply)."""

from __future__ import annotations

from core.intelligence.playbook import PlaybookStore
from core.intelligence.playbook_propagation import (
    PropagationCandidate,
    apply_propagation,
    apply_propagations,
    propose_propagations,
)


def _seed(store, title, org, score, *, category="general"):
    e = store.add(title, f"content of {title}", category=category, org_name=org)
    for _ in range(int(score)):  # bump usefulness_score by +1.0 per success
        store.record_use(e.entry_id, success=True)
    return e


def test_propose_proposes_missing_high_usefulness(tmp_path):
    store = PlaybookStore(tmp_path)
    _seed(store, "X集客術", "OrgA", 3)
    _seed(store, "既存術", "OrgB", 2)
    triples = {
        (c.title, c.source_org, c.target_org) for c in propose_propagations(platform_home=tmp_path)
    }
    assert ("X集客術", "OrgA", "OrgB") in triples
    assert ("既存術", "OrgB", "OrgA") in triples


def test_propose_respects_min_usefulness(tmp_path):
    store = PlaybookStore(tmp_path)
    _seed(store, "low_a", "OrgA", 0)  # usefulness 0 < 1.0
    _seed(store, "low_b", "OrgB", 0)
    assert propose_propagations(platform_home=tmp_path, min_usefulness=1.0) == []


def test_propose_skips_unnamed_org(tmp_path):
    store = PlaybookStore(tmp_path)
    _seed(store, "global_play", "", 3)  # unnamed/global
    _seed(store, "a", "OrgA", 3)
    _seed(store, "b", "OrgB", 3)
    cands = propose_propagations(platform_home=tmp_path)
    assert cands  # OrgA<->OrgB candidates exist
    assert all(c.source_org in {"OrgA", "OrgB"} and c.target_org in {"OrgA", "OrgB"} for c in cands)
    assert all("global_play" != c.title for c in cands)  # unnamed play never propagated


def test_propose_does_not_write(tmp_path):
    store = PlaybookStore(tmp_path)
    _seed(store, "X", "OrgA", 3)
    _seed(store, "anchor", "OrgB", 2)
    before = len(store.list_entries())
    propose_propagations(platform_home=tmp_path)
    assert len(PlaybookStore(tmp_path).list_entries()) == before  # read-only


def test_apply_is_idempotent_and_starts_low(tmp_path):
    store = PlaybookStore(tmp_path)
    _seed(store, "X", "OrgA", 3)
    _seed(store, "anchor", "OrgB", 2)  # OrgB exists as a named org
    cand = next(
        c
        for c in propose_propagations(platform_home=tmp_path)
        if c.title == "X" and c.target_org == "OrgB"
    )
    apply_propagation(cand, platform_home=tmp_path)
    apply_propagation(cand, platform_home=tmp_path)  # applying twice must not duplicate
    xs = [
        e for e in PlaybookStore(tmp_path).list_entries() if e.title == "X" and e.org_name == "OrgB"
    ]
    assert len(xs) == 1
    assert xs[0].usefulness_score == 0.0  # propagated copy starts low -> won't re-propagate
    assert "伝播元 org: OrgA" in xs[0].content  # provenance recorded


def test_reproposal_converges_after_apply(tmp_path):
    store = PlaybookStore(tmp_path)
    _seed(store, "X", "OrgA", 3)
    _seed(store, "anchor", "OrgB", 2)
    apply_propagations(propose_propagations(platform_home=tmp_path), platform_home=tmp_path)
    cands2 = propose_propagations(platform_home=tmp_path)
    # X is now present in OrgB -> not re-proposed there (converges)
    assert not any(c.title == "X" and c.target_org == "OrgB" for c in cands2)


def test_rescored_propagated_copy_does_not_respread(tmp_path):
    # 3 orgs: X starts only in OrgA. Propagate to B & C, then RE-SCORE the copy in OrgB
    # above threshold. Re-proposing must NOT re-spread X anywhere (it exists in all orgs).
    store = PlaybookStore(tmp_path)
    _seed(store, "X", "OrgA", 3)
    _seed(store, "anchorB", "OrgB", 2)
    _seed(store, "anchorC", "OrgC", 2)
    apply_propagations(propose_propagations(platform_home=tmp_path), platform_home=tmp_path)
    # bump OrgB's propagated copy of X well above min_usefulness
    store2 = PlaybookStore(tmp_path)
    x_in_b = next(e for e in store2.list_entries() if e.title == "X" and e.org_name == "OrgB")
    for _ in range(5):
        store2.record_use(x_in_b.entry_id, success=True)
    # X now lives in A, B, C -> no org lacks it -> zero X candidates (fixed point, no runaway)
    assert not any(c.title == "X" for c in propose_propagations(platform_home=tmp_path))


def test_apply_propagations_isolates_failures(tmp_path, monkeypatch):
    import core.intelligence.playbook_propagation as pp

    attempts = {"n": 0}
    real = pp.apply_propagation

    def flaky(candidate, *, platform_home=None):
        attempts["n"] += 1
        if candidate.title == "bad":
            raise RuntimeError("boom")
        return real(candidate, platform_home=platform_home)

    monkeypatch.setattr(pp, "apply_propagation", flaky)
    cands = [
        PropagationCandidate("bad", "c", "general", "OrgA", "OrgB", 3.0),
        PropagationCandidate("good", "c", "general", "OrgA", "OrgB", 3.0),
    ]
    applied = apply_propagations(cands, platform_home=tmp_path)
    assert applied == 1 and attempts["n"] == 2  # one failed, batch not aborted
