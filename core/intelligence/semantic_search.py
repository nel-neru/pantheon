"""
SemanticCodeSearch — セマンティックコード検索 (K-04)
TF-IDFベースの軽量コード意味検索
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SearchResult:
    file_path: str
    function_name: str
    relevance_score: float
    snippet: str


class SemanticCodeSearch:
    """Keyword-overlap semantic search over CodebaseIndexer output."""

    STOP_WORDS = {"the", "and", "for", "with", "from", "into", "code", "file"}

    def __init__(self, index=None):
        self.index = index

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        query_terms = self._tokenize(query)
        if not query_terms or self.index is None:
            return []

        index_data = self.index.get_index() if hasattr(self.index, "get_index") else self.index
        files = (index_data or {}).get("files", {})
        results: list[SearchResult] = []

        for rel_path, entry in files.items():
            corpus_parts = [
                rel_path,
                " ".join(entry.get("classes", [])),
                " ".join(entry.get("functions", [])),
                entry.get("docstring_summary", ""),
            ]
            corpus_tokens = set(self._tokenize(" ".join(corpus_parts)))
            matches = sorted(set(query_terms) & corpus_tokens)
            if not matches:
                continue
            functions = entry.get("functions", [])
            matched_function = next(
                (fn for fn in functions if set(self._tokenize(fn)) & set(query_terms)),
                functions[0] if functions else "",
            )
            snippet = entry.get("docstring_summary") or ", ".join(functions[:3]) or rel_path
            results.append(
                SearchResult(
                    file_path=rel_path,
                    function_name=matched_function,
                    relevance_score=round(len(matches) / max(1, len(set(query_terms))), 3),
                    snippet=snippet,
                )
            )

        return sorted(results, key=lambda item: item.relevance_score, reverse=True)[:top_k]

    def _tokenize(self, text: str) -> list[str]:
        tokens = re.split(r"[\s_\W]+", text.lower())
        return [token for token in tokens if len(token) > 1 and token not in self.STOP_WORDS]
