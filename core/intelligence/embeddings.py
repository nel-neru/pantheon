"""Pluggable text ranking for semantic recall (C5).

- **Fallback (always available, ZERO new hard deps):** a small vendored BM25 over
  tokenized text — deterministic and strictly better than the prior keyword top-N.
  Tokenizes ASCII words AND CJK character-bigrams so Japanese playbooks get signal.
- **Optional (opt-in via ``PANTHEON_EMBEDDINGS=1``):** a local embedding model
  (``fastembed``, e.g. bge-small) — lazy-imported, so ABSENCE is the normal CI/dev
  state and there is never a surprise model download. If the package or model is
  missing, ranking silently falls back to BM25.

The caller (``MemoryBank.recall``) gates the whole thing behind
``PANTHEON_SEMANTIC_RECALL`` (default on; ``0`` restores pure keyword/usefulness recall).
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from typing import List, Optional

_TOKEN_RE = re.compile(r"[0-9a-z]+", re.IGNORECASE)
# Hiragana・Katakana・CJK 統合漢字に加え、半角カタカナ（U+FF66–FF9F）も拾う
# （製品名などで実際に現れ、bigram 化で日本語の BM25 シグナルになる）。
_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ]+")
_TRUTHY = {"1", "true", "yes", "on"}


def _tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    toks = _TOKEN_RE.findall(text)
    # CJK has no spaces — add character bigrams so BM25 has term signal for Japanese.
    for run in _CJK_RE.findall(text):
        if len(run) == 1:
            toks.append(run)
        else:
            toks.extend(run[i : i + 2] for i in range(len(run) - 1))
    return toks


def bm25_scores(query: str, docs: List[str], *, k1: float = 1.5, b: float = 0.75) -> List[float]:
    """Vendored BM25 relevance score per doc (pure Python, deterministic, zero-dep)."""
    n = len(docs)
    if n == 0:
        return []
    doc_tokens = [_tokenize(d) for d in docs]
    avgdl = (sum(len(t) for t in doc_tokens) / n) or 1.0
    df: dict[str, int] = {}
    for toks in doc_tokens:
        for term in set(toks):
            df[term] = df.get(term, 0) + 1
    q_terms = set(_tokenize(query))
    scores: List[float] = []
    for toks in doc_tokens:
        tf = Counter(toks)
        dl = len(toks) or 1
        score = 0.0
        for qt in q_terms:
            if qt not in tf:
                continue
            n_qt = df.get(qt, 0)
            idf = math.log(1 + (n - n_qt + 0.5) / (n_qt + 0.5))
            freq = tf[qt]
            score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avgdl))
        scores.append(score)
    return scores


# 遅延初期化のモジュールキャッシュ。並行初回呼び出しで二重構築の可能性はあるが、
# 冪等（同一モデル）かつ以降は read-mostly なので良性。重い init は二度起きない。
_MODEL = None
_MODEL_TRIED = False


def _embedding_scores(query: str, docs: List[str]) -> Optional[List[float]]:
    """Cosine similarity via an optional local model; None if unavailable."""
    global _MODEL, _MODEL_TRIED
    if not _MODEL_TRIED:
        _MODEL_TRIED = True
        try:
            from fastembed import TextEmbedding  # type: ignore

            _MODEL = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        except Exception:
            _MODEL = None
    if _MODEL is None:
        return None
    try:
        vecs = list(_MODEL.embed([query] + list(docs)))
        q, doc_vecs = vecs[0], vecs[1:]

        def _cos(a, b_) -> float:
            dot = sum(x * y for x, y in zip(a, b_))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(y * y for y in b_))
            return dot / ((na * nb) or 1.0)

        return [_cos(q, d) for d in doc_vecs]
    except Exception:
        return None


def rank_scores(query: str, docs: List[str]) -> List[float]:
    """Relevance score per doc. Uses the optional embedding model when
    ``PANTHEON_EMBEDDINGS`` is enabled AND available; otherwise vendored BM25."""
    if os.getenv("PANTHEON_EMBEDDINGS", "").strip().lower() in _TRUTHY:
        emb = _embedding_scores(query, docs)
        if emb is not None:
            return emb
    return bm25_scores(query, docs)
