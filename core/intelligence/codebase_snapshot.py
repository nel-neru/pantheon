"""
CodebaseSnapshot — 目的別最小トークン表現 (K-03)

エージェントのプロンプトに埋め込む「最小トークン表現」を生成する。
目的（モード）に応じて必要な情報だけを抽出し、トークンを最小化しながら
エージェントがコードベースを正確に理解できるコンテキストを提供する。

目安: 全ファイル生読み → 探索用スナップショットは -80% トークン削減
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .codebase_indexer import CodebaseIndexer


SNAPSHOT_MODES: Dict[str, Dict[str, Any]] = {
    "exploration": {
        "max_files": 30,
        "description": "全体把握: 構造全体を俯瞰する",
        "priority_boost": [],
    },
    "code_review": {
        "max_files": 20,
        "description": "コードレビュー: エントリポイントと主要クラスを重点表示",
        "priority_boost": ["entry_point", "large", "many_classes"],
    },
    "improvement": {
        "max_files": 15,
        "description": "改善提案: 問題のあるファイルを優先表示",
        "priority_boost": ["large", "many_imports", "no_docstring"],
    },
    "security": {
        "max_files": 10,
        "description": "セキュリティ: 認証・通信・設定ファイルを優先",
        "priority_boost": ["auth_related", "config_file"],
    },
    "meta_improvement": {
        "max_files": 20,
        "description": "アーキテクチャ改善: コア構造と結合度を優先",
        "priority_boost": ["core_module", "many_imports", "entry_point"],
    },
}

SECURITY_KEYWORDS = {"auth", "token", "password", "secret", "key", "crypt", "hash", "login", "session"}
CORE_DIRS = {"core", "lib", "src", "pkg"}


class CodebaseSnapshot:
    """
    エージェントのプロンプトに埋め込む「最小トークン表現」を生成する。
    目的（モード）ごとに異なるランキング基準でファイルを選択する。
    """

    def __init__(self, indexer: CodebaseIndexer):
        self._indexer = indexer

    def generate(self, mode: str = "exploration", max_tokens: int = 2000) -> str:
        """
        指定モードのスナップショットを生成する。
        max_tokens を超えないよう自動トリミングされる（1トークン ≒ 4文字）。
        """
        index = self._indexer.get_index()
        files = index.get("files", {})
        repo_name = Path(index.get("repo_path", ".")).name
        total_files = index.get("total_files", 0)
        stats = self._indexer.get_summary_stats()
        mode_cfg = SNAPSHOT_MODES.get(mode, SNAPSHOT_MODES["exploration"])

        lines: List[str] = [
            f"# {repo_name} コードベーススナップショット（{mode}モード）",
            f"# {mode_cfg['description']}",
            f"ファイル数: {total_files} | クラス: {stats['total_classes']} | "
            f"関数: {stats['total_functions']} | 合計: {stats['total_size_kb']}KB",
            "",
            "## ファイル構造（重要度順）",
        ]

        ranked = self._rank_files(files, mode)
        max_files = mode_cfg["max_files"]

        for rel_path, entry in ranked[:max_files]:
            line = _format_entry(rel_path, entry)
            lines.append(line)

        if total_files > max_files:
            lines.append(f"... 他 {total_files - max_files} ファイル省略")

        # 依存関係サマリー（上位ファイル）
        if mode in ("meta_improvement", "improvement"):
            dep_map = self._indexer.get_dependency_map()
            most_imported = _find_most_imported(dep_map, top_k=5)
            if most_imported:
                lines.append("")
                lines.append("## 最も依存されているモジュール（変更影響大）")
                for mod, count in most_imported:
                    lines.append(f"  - {mod}: {count} ファイルから参照")

        result = "\n".join(lines)

        # トークン予算内に収める
        max_chars = max_tokens * 4
        if len(result) > max_chars:
            result = result[:max_chars] + "\n... (トークン上限により省略)"

        return result

    def generate_for_file(self, rel_path: str) -> str:
        """特定ファイルの詳細スナップショットを生成する。"""
        entry = self._indexer.get_file_entry(rel_path)
        if not entry:
            return f"ファイル {rel_path} はインデックスに存在しません。"

        lines = [
            f"## {rel_path}",
            f"サイズ: {entry.get('size_bytes', 0) / 1024:.1f}KB",
            f"クラス: {', '.join(entry.get('classes', [])) or 'なし'}",
            f"関数: {', '.join(entry.get('functions', [])) or 'なし'}",
            f"インポート: {', '.join(entry.get('imports', [])[:10])}",
        ]
        if entry.get("docstring_summary"):
            lines.append(f"概要: {entry['docstring_summary'][:150]}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 内部実装                                                             #
    # ------------------------------------------------------------------ #

    def _rank_files(
        self, files: Dict[str, Any], mode: str
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """モードに応じてファイルをスコアリングしてソートする。"""
        from pathlib import Path as P

        scored: List[Tuple[str, Dict[str, Any], float]] = []

        for rel_path, entry in files.items():
            score = 0.0
            stem = P(rel_path).stem.lower()

            # 全モード共通: エントリポイント優先
            if entry.get("is_entry_point"):
                score += 5

            if mode == "code_review":
                score += min(entry.get("size_bytes", 0) / 2000, 3)
                score += len(entry.get("classes", []))

            elif mode == "improvement":
                score += min(entry.get("size_bytes", 0) / 3000, 3)
                score += min(len(entry.get("imports", [])) / 5, 2)
                if not entry.get("docstring_summary"):
                    score += 1

            elif mode == "security":
                path_lower = rel_path.lower()
                if any(kw in path_lower for kw in SECURITY_KEYWORDS):
                    score += 5
                for cls in entry.get("classes", []):
                    if any(kw in cls.lower() for kw in SECURITY_KEYWORDS):
                        score += 2

            elif mode == "meta_improvement":
                parts = P(rel_path).parts
                if any(p in CORE_DIRS for p in parts):
                    score += 3
                score += min(len(entry.get("imports", [])) / 3, 3)

            scored.append((rel_path, entry, score))

        return [(p, e) for p, e, _ in sorted(scored, key=lambda x: x[2], reverse=True)]


# ------------------------------------------------------------------ #
# ユーティリティ                                                       #
# ------------------------------------------------------------------ #

def _format_entry(rel_path: str, entry: Dict[str, Any]) -> str:
    """インデックスエントリを1行のスナップショット行にフォーマットする。"""
    parts = [f"- **{rel_path}**"]

    classes = entry.get("classes", [])
    if classes:
        parts.append(f"cls:[{', '.join(classes[:4])}{'...' if len(classes) > 4 else ''}]")

    functions = entry.get("functions", [])
    if functions:
        parts.append(f"fn:[{', '.join(functions[:4])}{'...' if len(functions) > 4 else ''}]")

    size_kb = entry.get("size_bytes", 0) / 1024
    imports_count = len(entry.get("imports", []))
    parts.append(f"({size_kb:.1f}KB, imp:{imports_count})")

    line = " ".join(parts)
    if entry.get("docstring_summary"):
        line += f"\n  └ {entry['docstring_summary'][:80]}"

    return line


def _find_most_imported(
    dep_map: Dict[str, List[str]], top_k: int = 5
) -> List[Tuple[str, int]]:
    """最も多くのファイルからimportされているモジュールを返す。"""
    counts: Dict[str, int] = {}
    for imports in dep_map.values():
        for mod in imports:
            counts[mod] = counts.get(mod, 0) + 1

    return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_k]
