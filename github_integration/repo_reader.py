"""
GitHub Integration - Repository Reader

コードレビューに使用するファイルをリポジトリから収集するユーティリティ。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".repocorp",
}

CODE_EXTENSIONS = {".py", ".ts", ".js", ".go", ".rs", ".java", ".rb", ".cpp", ".c", ".h"}
ENTRY_POINT_STEMS = {"main", "app", "cli", "__main__", "server", "api", "run", "index"}


def get_file_tree(repo_path: Path) -> List[str]:
    """コードファイルのパス一覧を返す（除外ディレクトリ除く）"""
    result = []
    for f in sorted(repo_path.rglob("*")):
        if f.is_dir():
            continue
        if any(part in EXCLUDE_DIRS for part in f.relative_to(repo_path).parts):
            continue
        result.append(str(f.relative_to(repo_path)))
    return result


def read_file_content(repo_path: Path, rel_path: str, max_bytes: int = 50_000) -> Optional[str]:
    """ファイルの内容を読む（サイズ上限あり）"""
    target = repo_path / rel_path
    if not target.exists():
        return None
    content = target.read_text(encoding="utf-8", errors="ignore")
    if len(content) > max_bytes:
        return content[:max_bytes] + "\n... (truncated)"
    return content


def get_important_files(repo_path: Path, max_files: int = 15) -> Dict[str, str]:
    """
    コードレビューに重要なファイルを優先度順に返す。
    優先度: エントリポイント > 最近更新 > それ以外
    """
    candidates: List[Path] = []
    for f in repo_path.rglob("*"):
        if f.is_dir():
            continue
        if f.suffix not in CODE_EXTENSIONS:
            continue
        if any(part in EXCLUDE_DIRS for part in f.relative_to(repo_path).parts):
            continue
        candidates.append(f)

    def sort_key(f: Path) -> tuple:
        is_entry = f.stem.lower() in ENTRY_POINT_STEMS
        try:
            mtime = f.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (not is_entry, -mtime)

    candidates.sort(key=sort_key)

    result: Dict[str, str] = {}
    total_chars = 0
    max_total = 50_000

    for f in candidates:
        if len(result) >= max_files or total_chars >= max_total:
            break
        content = read_file_content(repo_path, str(f.relative_to(repo_path)))
        if content:
            rel = str(f.relative_to(repo_path))
            result[rel] = content
            total_chars += len(content)

    return result
