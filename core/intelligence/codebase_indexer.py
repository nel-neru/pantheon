"""
CodebaseIndexer — ASTベースコードベースインデックス (K-01, K-02)

リポジトリを一度スキャンし、ファイル構造・クラス・関数・importを
圧縮JSONインデックスとして保存する。

毎回全ファイルを読み込む代わりにインデックスを参照することで、
エージェントのトークン消費を大幅に削減する。

インクリメンタル更新: ファイルのmtimeを比較し変更分のみ再インデックス。
"""

from __future__ import annotations

import ast
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

INDEX_VERSION = "1.0.0"

SUPPORTED_EXTENSIONS = {".py", ".ts", ".js", ".go", ".rs", ".java", ".rb", ".cpp", ".c"}

EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".pantheon",
    "pantheon.egg-info",
}

ENTRY_STEMS = {"main", "app", "cli", "__main__", "server", "api", "run", "index"}


class CodebaseIndexer:
    """
    ASTベースのコードベースインデックス生成器。

    ファイルを毎回読み込む代わりに圧縮インデックスを管理し、
    トークン消費を削減する。インクリメンタル更新で変更ファイルのみ再解析。
    """

    def __init__(self, repo_path: Path | str):
        self.repo_path = Path(repo_path).resolve()
        self.state_dir = self.repo_path / ".pantheon"
        self.index_path = self.state_dir / "codebase_index.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # パブリック API                                                       #
    # ------------------------------------------------------------------ #

    def build(self, force: bool = False) -> Dict[str, Any]:
        """
        コードベースのインデックスを構築する。

        force=False の場合、mtime 変化があったファイルのみ再インデックス。
        Returns: インデックス辞書
        """
        existing = self._load_index() or {}
        index: Dict[str, Any] = {
            "version": INDEX_VERSION,
            "repo_path": str(self.repo_path),
            "built_at": datetime.now(timezone.utc).isoformat(),
            "files": dict(existing.get("files", {})),
        }

        all_files = self._collect_files()
        existing_files = set(index["files"].keys())
        current_rels = set()
        updated = 0

        for file_path in all_files:
            rel = str(file_path.relative_to(self.repo_path))
            current_rels.add(rel)
            try:
                mtime = file_path.stat().st_mtime
            except OSError:
                continue

            if not force and index["files"].get(rel, {}).get("mtime") == mtime:
                continue

            entry = self._index_file(file_path, rel, mtime)
            if entry:
                index["files"][rel] = entry
                updated += 1

        # 削除されたファイルをインデックスから除去
        for removed in existing_files - current_rels:
            index["files"].pop(removed, None)

        index["total_files"] = len(index["files"])
        index["updated_files"] = updated
        self._save_index(index)
        logger.info(
            "CodebaseIndexer: %d files indexed, %d updated (%s)",
            index["total_files"], updated, self.repo_path.name,
        )
        return index

    def get_index(self) -> Dict[str, Any]:
        """インデックスを取得。存在しない場合はビルドして返す。"""
        index = self._load_index()
        if not index:
            index = self.build()
        return index

    def get_file_entry(self, rel_path: str) -> Optional[Dict[str, Any]]:
        """特定ファイルのインデックスエントリを取得。"""
        return self.get_index().get("files", {}).get(rel_path)

    def search(self, keyword: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        キーワードでファイルを検索（スコアリング付き）。

        スコア計算:
          - ファイルパスにキーワード含む: +3
          - クラス名に含む: +2 / 件
          - 関数名に含む: +1 / 件
          - docstring に含む: +1
        """
        kw = keyword.lower()
        scored: List[Dict[str, Any]] = []

        for rel, entry in self.get_index().get("files", {}).items():
            score = 0
            if kw in rel.lower():
                score += 3
            for cls in entry.get("classes", []):
                if kw in cls.lower():
                    score += 2
            for fn in entry.get("functions", []):
                if kw in fn.lower():
                    score += 1
            if kw in entry.get("docstring_summary", "").lower():
                score += 1

            if score > 0:
                scored.append({"path": rel, "score": score, **entry})

        return sorted(scored, key=lambda x: x["score"], reverse=True)[:top_k]

    def get_dependency_map(self) -> Dict[str, List[str]]:
        """ファイル → import先 の依存マップを返す。"""
        return {
            rel: entry.get("imports", [])
            for rel, entry in self.get_index().get("files", {}).items()
        }

    def get_summary_stats(self) -> Dict[str, Any]:
        """インデックスのサマリー統計を返す。"""
        index = self.get_index()
        files = index.get("files", {})
        total_classes = sum(len(e.get("classes", [])) for e in files.values())
        total_functions = sum(len(e.get("functions", [])) for e in files.values())
        total_size = sum(e.get("size_bytes", 0) for e in files.values())
        by_ext: Dict[str, int] = {}
        for e in files.values():
            ext = e.get("extension", "other")
            by_ext[ext] = by_ext.get(ext, 0) + 1

        return {
            "total_files": index.get("total_files", 0),
            "total_classes": total_classes,
            "total_functions": total_functions,
            "total_size_kb": round(total_size / 1024, 1),
            "by_extension": by_ext,
            "built_at": index.get("built_at"),
        }

    # ------------------------------------------------------------------ #
    # 内部実装                                                             #
    # ------------------------------------------------------------------ #

    def _collect_files(self) -> List[Path]:
        files = []
        for f in self.repo_path.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix not in SUPPORTED_EXTENSIONS:
                continue
            if any(part in EXCLUDE_DIRS for part in f.relative_to(self.repo_path).parts):
                continue
            files.append(f)
        return sorted(files)

    def _index_file(self, file_path: Path, rel_path: str, mtime: float) -> Optional[Dict[str, Any]]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

        entry: Dict[str, Any] = {
            "path": rel_path,
            "mtime": mtime,
            "size_bytes": file_path.stat().st_size,
            "extension": file_path.suffix,
            "is_entry_point": file_path.stem.lower() in ENTRY_STEMS,
            "classes": [],
            "functions": [],
            "imports": [],
            "docstring_summary": "",
        }

        if file_path.suffix == ".py":
            _parse_python(content, entry)

        return entry

    def _load_index(self) -> Optional[Dict[str, Any]]:
        if not self.index_path.exists():
            return None
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save_index(self, index: Dict[str, Any]) -> None:
        self.index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def get_stale_files(index_path: Path, repo_root: Path) -> list[Path]:
    """Return indexed files whose mtime is older than the current file mtime."""
    index_file = Path(index_path)
    root = Path(repo_root)
    if not index_file.exists():
        return []
    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    stale: list[Path] = []
    for rel_path, entry in data.get("files", {}).items():
        file_path = root / rel_path
        if not file_path.exists():
            continue
        try:
            if file_path.stat().st_mtime > float(entry.get("mtime", 0)):
                stale.append(file_path)
        except OSError:
            continue
    return stale


def invalidate_cache(index_path: Path, file_paths: list[Path]) -> None:
    """Remove file entries from an existing index JSON file."""
    index_file = Path(index_path)
    if not index_file.exists():
        return
    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
    except Exception:
        return

    normalized = {str(Path(file_path)) for file_path in file_paths}
    files = data.get("files", {})
    for rel_path in list(files.keys()):
        candidate = str(Path(rel_path))
        if candidate in normalized or any(Path(path).name == Path(rel_path).name for path in normalized):
            files.pop(rel_path, None)
    data["total_files"] = len(files)
    index_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ #
# 言語別パーサー                                                       #
# ------------------------------------------------------------------ #

def _parse_python(content: str, entry: Dict[str, Any]) -> None:
    """Python ファイルを AST 解析してインデックスエントリを埋める。"""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return

    docstring = ast.get_docstring(tree)
    if docstring:
        entry["docstring_summary"] = docstring[:200]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                entry["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                entry["imports"].append(node.module)
        elif isinstance(node, ast.ClassDef):
            entry["classes"].append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # モジュールレベルの関数のみ（メソッドは除く）
            if isinstance(node.col_offset, int) and node.col_offset == 0:
                entry["functions"].append(node.name)
