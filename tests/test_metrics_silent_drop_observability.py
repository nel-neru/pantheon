"""Cycle 5: metrics 層の破損 state 黙殺を観測化したことを保証する。

[[silent-drop-observability]] の核心「メトリクス母数の黙殺＝静かな指標歪み」に該当する
JSONL ローダー（growth_history / learning_curve / coevolution_graph）は、破損/不完全な行を
bare ``except: continue`` で黙殺していた。確立済みの ``warn_skipped_state_file`` で観測化する。

各テストは「正常レコードは従来どおり返る」かつ「破損行は warn シグナルを出して skip される」ことを
固定し、黙殺への回帰を防ぐ。warn は except 内で ``core.platform.state`` から遅延 import されるので、
そこをスパイすれば呼び出しを捕捉できる。
"""

from __future__ import annotations

import pytest

from core.metrics.coevolution_graph import CoevolutionGraph
from core.metrics.growth_history import GrowthHistoryRecorder
from core.metrics.learning_curve import LearningCurveTracker


@pytest.fixture
def warn_spy(monkeypatch):
    calls: list[tuple[str, str]] = []

    def _spy(f, exc, kind="状態"):
        calls.append((str(f), kind))

    monkeypatch.setattr("core.platform.state.warn_skipped_state_file", _spy)
    return calls


def test_growth_history_warns_on_corrupt_line(tmp_path, warn_spy):
    rec = GrowthHistoryRecorder(platform_home=tmp_path)
    rec.record("orgA", accepted_count=3)
    with rec.history_file.open("a", encoding="utf-8") as handle:
        handle.write("{ this is not valid json\n")

    out = rec.get_history("orgA")

    assert len(out) == 1  # 正常レコードは生存
    assert [kind for _, kind in warn_spy] == ["GrowthRecord"]  # 破損行は観測化


def test_learning_curve_warns_on_corrupt_line(tmp_path, warn_spy):
    tracker = LearningCurveTracker(platform_home=tmp_path)
    tracker.record_snapshot(knowledge_count=5, avg_quality=7.0, accepted=2)
    with tracker.data_file.open("a", encoding="utf-8") as handle:
        handle.write("not-json-at-all\n")

    points = tracker.get_trend()

    assert len(points) == 1
    assert [kind for _, kind in warn_spy] == ["LearningDataPoint"]


def test_coevolution_graph_warns_on_corrupt_line(tmp_path, warn_spy):
    graph = CoevolutionGraph(platform_home=tmp_path)
    graph.record_coevolution_point(org_score=80.0, developer_approval_rate=60.0)
    with graph.graph_path.open("a", encoding="utf-8") as handle:
        handle.write("{broken\n")

    org_scores, dev_rates = graph.get_both_trends()

    assert org_scores == [80.0] and dev_rates == [60.0]
    assert [kind for _, kind in warn_spy] == ["CoevolutionPoint"]


def test_valid_only_emits_no_warning(tmp_path, warn_spy):
    """破損が無ければ warn は一切出ない（既存の正常系を汚さない）。"""
    rec = GrowthHistoryRecorder(platform_home=tmp_path)
    rec.record("orgA", accepted_count=1)

    assert rec.get_history("orgA")
    assert warn_spy == []
