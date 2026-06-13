"""トレンドの重複排除とスコアランキングの純粋関数群。

既存の trend daemon / collector / scoring を一切触らず、プレーンな ``dict``
（``{"url": ..., "title": ..., "score": ...}`` 形）のリストに対して
独立に重複排除・ランキングを提供する。すべて純粋・決定論・冪等で、入力
``dict`` を破壊しない（LLM 非依存）。

- :func:`_normalize_key` — 重複判定キーの導出（url 優先、無ければ title）。
- :func:`dedupe_trends` — 同一キーは score 最大の 1 件のみ残す（入力順保持・安定）。
- :func:`rank_trends` — dedupe 後に min_score でフィルタし score 降順で返す。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = ["_normalize_key", "dedupe_trends", "rank_trends"]


def _to_score(trend: Dict[str, Any]) -> float:
    """trend の score を float で取り出す（欠落・不正は 0.0 扱い）。"""
    raw = trend.get("score", 0.0)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _normalize_key(trend: Dict[str, Any]) -> str:
    """重複判定用のキーを導出する。

    ``url`` があれば正規化（前後空白除去・小文字化・末尾スラッシュ除去）して
    使う。url が無い（または空）場合は ``title`` を小文字化し、連続する空白を
    単一スペースへ畳み込んだものをキーとする。どちらも無ければ空文字列。
    """
    url = trend.get("url")
    if isinstance(url, str):
        normalized = url.strip().lower().rstrip("/")
        if normalized:
            return normalized

    title = trend.get("title")
    if isinstance(title, str):
        return " ".join(title.lower().split())

    return ""


def dedupe_trends(trends: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """同一キーのトレンドを score 最大の 1 件だけに集約する。

    入力順は保持する（安定）。同一キーが複数あった場合、最初に出現した位置に
    score 最大の 1 件を残す。score が同点なら先に出現したものを採用する。
    score 欠落は 0 扱い。入力 ``dict`` は破壊せず、参照をそのまま返す。
    """
    best_index: Dict[str, int] = {}
    order: List[str] = []
    chosen: Dict[str, Dict[str, Any]] = {}

    for trend in trends:
        key = _normalize_key(trend)
        score = _to_score(trend)
        if key not in best_index:
            best_index[key] = len(order)
            order.append(key)
            chosen[key] = trend
        elif score > _to_score(chosen[key]):
            chosen[key] = trend

    return [chosen[key] for key in order]


def rank_trends(
    trends: List[Dict[str, Any]],
    *,
    min_score: float = 0.0,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """重複排除後に score 降順でランキングして返す。

    1. :func:`dedupe_trends` で重複排除する。
    2. ``score >= min_score`` の要素だけ残す（score 欠落は 0 扱い）。
    3. score 降順に並べる。同点は dedupe 後の入力順を保つ安定ソート。
    4. ``limit`` が指定されていれば先頭 ``limit`` 件に絞る。

    純粋・決定論・冪等で、入力 ``dict`` は破壊しない。
    """
    deduped = dedupe_trends(trends)
    filtered = [t for t in deduped if _to_score(t) >= min_score]
    ranked = sorted(filtered, key=_to_score, reverse=True)
    if limit is not None:
        if limit <= 0:
            return []
        ranked = ranked[:limit]
    return ranked
