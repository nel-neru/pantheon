"""Trend → 新規事業提案 への決定論変換（P2.1）。

高スコアのトレンド 1 件を「新しい収益モデル会社」を起こすための提案ペイロード
（``dict``）へ変換する純粋関数を提供する。LLM 呼び出しには依存せず、同じ入力なら
常に同じ出力を返す（決定論的・冪等）。永続化や I/O は持たない。

注意: ここで扱う ``trend`` は軽量な ``dict``（``title`` / ``score`` / ``genre`` /
``summary`` / ``url``）で、``score`` は 0..1 スケールを想定する（閾値 0.6）。
これは ``core.trends.models.TrendItem.score``（0..10 スケール）とは別物で、
本モジュールは独立した閾値・純粋関数として完結する。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

# 新規事業提案に値するとみなす最小スコア（0..1 スケール）。
BUSINESS_PROPOSAL_MIN_SCORE = 0.6

# ``TrendItem.score``（0..10）→ 本モジュールの 0..1 スケールへの換算係数（橋渡しの単一定義）。
# business_pipeline / untapped_genre が個別に ``/ 10`` を書くと 0..1↔0..10 ミスマッチで
# 閾値が静かにずれる footgun になるため、両者はここを唯一のソースとして参照する。
TREND_SCORE_SCALE = 10.0


def trend_score_to_unit(score: Any) -> float:
    """0..10 スケールのトレンドスコアを 0..1 へ橋渡しする（換算ロジックの単一ソース）。

    欠損・不正値は 0.0 扱い（``_safe_score`` と同じ安全側）。
    """
    try:
        return float(score) / TREND_SCORE_SCALE
    except (TypeError, ValueError):
        return 0.0


# 動画系ジャンルを示すトークン（genre / source title slug に含まれていれば動画系とみなす）。
_VIDEO_TOKENS = (
    "video",
    "movie",
    "film",
    "youtube",
    "vtuber",
    "streaming",
    "動画",
    "映像",
    "配信",
)

# slug 化で許可する文字（英数・アンダースコア・日本語ひらがな/カタカナ/漢字）。
# それ以外は区切り文字として扱い、語を _ で連結する。
_SLUG_ALLOWED = re.compile(r"[0-9a-z_぀-ゟ゠-ヿ一-鿿]+")

# slug が長くなりすぎないよう、先頭からこの語数だけ採用する。
_SLUG_MAX_TOKENS = 4


def _safe_score(trend: Dict[str, Any]) -> float:
    """trend[\"score\"] を安全に ``float`` 化する（欠損・不正値は 0.0 扱い）。"""
    try:
        return float(trend.get("score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _slugify(text: str) -> str:
    """テキストを kebab/snake 風の短い genre slug に正規化する（決定論的）。

    小文字化し、英数・日本語以外を区切りに語を切り出して先頭数語を ``_`` 連結する。
    抽出できる語が無ければ ``\"general\"`` を返す。
    """
    tokens = _SLUG_ALLOWED.findall((text or "").lower())
    if not tokens:
        return "general"
    return "_".join(tokens[:_SLUG_MAX_TOKENS])


def _resolve_genre(trend: Dict[str, Any]) -> str:
    """genre を確定する: 明示 genre があれば slug 化、無ければ title から推定する。"""
    explicit = str(trend.get("genre") or "").strip()
    if explicit:
        return _slugify(explicit)
    return _slugify(str(trend.get("title") or ""))


def _is_video_genre(genre: str) -> bool:
    """genre slug が動画系トークンを含むかどうか。"""
    return any(token in genre for token in _VIDEO_TOKENS)


def _suggested_divisions(genre: str) -> List[str]:
    """genre に応じた推奨 division（収益モデル会社の最小骨格）を返す。

    動画系は制作部門を含む 3 部門、それ以外は集客＋収益化の 2 部門。
    """
    if _is_video_genre(genre):
        return ["audience_development", "content_production", "monetization"]
    return ["audience_development", "monetization"]


def is_business_worthy(
    trend: Dict[str, Any], min_score: float = BUSINESS_PROPOSAL_MIN_SCORE
) -> bool:
    """トレンドが新規事業提案に値するか（score >= min_score）を判定する純粋関数。"""
    return _safe_score(trend) >= float(min_score)


def trend_to_business_proposal(trend: Dict[str, Any]) -> Dict[str, Any]:
    """高スコアのトレンド 1 件を新規事業提案ペイロード（dict）へ変換する純粋関数。

    入力例: ``{\"title\": str, \"score\": float, \"genre\": str?, \"summary\": str?, \"url\": str?}``

    スコアが ``BUSINESS_PROPOSAL_MIN_SCORE`` 未満なら ``ValueError`` を送出する
    （事業化に値しないトレンドを提案へ通さない安全弁）。閾値以上なら常に
    ``requires_human_gate=True`` を付けて返し、自動採用ではなく人手承認を前提にする。
    """
    score = _safe_score(trend)
    if not is_business_worthy(trend):
        raise ValueError(
            f"trend score {score:.3f} < BUSINESS_PROPOSAL_MIN_SCORE "
            f"({BUSINESS_PROPOSAL_MIN_SCORE}); not business-worthy"
        )

    title = str(trend.get("title") or "").strip()
    summary = str(trend.get("summary") or "").strip()
    genre = _resolve_genre(trend)

    # rationale には判断材料（score と summary）を簡潔に含める。summary が無くても壊さない。
    rationale = f"トレンドスコア {score:.2f} の高シグナル。"
    if summary:
        rationale += f" 要約: {summary[:200]}"

    return {
        "kind": "new_business",
        "genre": genre,
        "name": f"{genre} 事業",
        "rationale": rationale,
        "suggested_divisions": _suggested_divisions(genre),
        "source_trend": title,
        "requires_human_gate": True,
    }
