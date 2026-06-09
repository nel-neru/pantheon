"""CodebaseExplorerAgent / CodebaseSnapshot の回帰テスト。

回帰防止: CodebaseSnapshot は CodebaseIndexer オブジェクトを受け取る（build() の戻り値 dict を
渡すと get_index() で AttributeError になる、という過去のクラッシュ）。
"""

from __future__ import annotations

import asyncio

from core.intelligence.codebase_indexer import CodebaseIndexer
from core.intelligence.codebase_snapshot import CodebaseSnapshot


def _make_repo(tmp_path):
    (tmp_path / "app.py").write_text(
        "class Foo:\n    def bar(self):\n        return 1\n", encoding="utf-8"
    )
    (tmp_path / "util.py").write_text("def helper():\n    return 2\n", encoding="utf-8")
    return tmp_path


def test_snapshot_accepts_indexer_and_generates(tmp_path):
    _make_repo(tmp_path)
    indexer = CodebaseIndexer(tmp_path)
    indexer.build()
    snapshot = CodebaseSnapshot(indexer)  # indexer オブジェクトを渡す
    text = snapshot.generate(mode="exploration", max_tokens=500)
    assert "コードベーススナップショット" in text


def test_explorer_agent_explore_does_not_crash(tmp_path):
    """explore() が CodebaseSnapshot に indexer を渡し、最後まで走る（過去はここでクラッシュ）。"""
    from agents.codebase_explorer_agent import CodebaseExplorerAgent

    _make_repo(tmp_path)
    agent = (
        CodebaseExplorerAgent.create()
        if hasattr(CodebaseExplorerAgent, "create")
        else CodebaseExplorerAgent()
    )
    result = asyncio.run(
        agent.explore(str(tmp_path), mode="exploration", max_tokens=500, auto_save_results=False)
    )
    assert "index_stats" in result
    assert result["index_stats"].get("total_files", 0) >= 1
