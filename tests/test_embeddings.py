"""C5: セマンティックリコールの ranking コア（vendored BM25 + 任意埋め込み）のテスト。

決定論・offline（外部モデルや claude CLI を呼ばない）。fastembed が無い既定状態で
``rank_scores`` が BM25 にフォールバックすることを含めて検証する。
"""

from __future__ import annotations

from core.intelligence.embeddings import bm25_scores, rank_scores


def test_bm25_ranks_matching_doc_highest():
    docs = [
        "X集客のコツ: 短文と画像で伸ばす",
        "note有料記事の構成と価格設計",
        "YouTube Shorts のサムネ最適化",
    ]
    scores = bm25_scores("note 有料記事 価格", docs)
    assert len(scores) == 3
    # 「note 有料記事 価格」に最も語が重なる doc[1] が最高スコア。
    assert scores[1] == max(scores)
    assert scores[1] > 0.0


def test_bm25_empty_docs_returns_empty():
    assert bm25_scores("anything", []) == []


def test_bm25_is_deterministic():
    docs = ["alpha beta gamma", "beta gamma delta", "delta epsilon"]
    a = bm25_scores("beta gamma", docs)
    b = bm25_scores("beta gamma", docs)
    assert a == b  # 同一入力 → 同一出力（決定論）


def test_bm25_no_overlap_scores_zero():
    docs = ["完全に無関係な内容", "これも別の話題"]
    scores = bm25_scores("xyzzy フーバー 量子", docs)
    assert scores == [0.0, 0.0]  # 語が一切重ならなければ全て 0


def test_bm25_cjk_bigram_signal():
    """空白の無い日本語でも文字 bigram で関連シグナルが出る。"""
    docs = ["セマンティック検索の実装", "天気予報の話"]
    scores = bm25_scores("セマンティック検索", docs)
    assert scores[0] > scores[1]
    assert scores[0] > 0.0


def test_bm25_halfwidth_katakana_signal():
    """半角カタカナ（U+FF66–FF9F）も bigram 化され関連シグナルになる。"""
    docs = ["ﾃﾞｰﾀ分析の手順", "天気の話題"]
    scores = bm25_scores("ﾃﾞｰﾀ分析", docs)
    assert scores[0] > scores[1]
    assert scores[0] > 0.0


def test_rank_scores_falls_back_to_bm25_by_default(monkeypatch):
    """PANTHEON_EMBEDDINGS 未設定なら rank_scores == bm25_scores（モデル不要）。"""
    monkeypatch.delenv("PANTHEON_EMBEDDINGS", raising=False)
    docs = ["foo bar baz", "lorem ipsum dolor"]
    assert rank_scores("foo bar", docs) == bm25_scores("foo bar", docs)


def test_rank_scores_empty_docs():
    assert rank_scores("q", []) == []
