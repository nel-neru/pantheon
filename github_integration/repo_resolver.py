"""
PR 対象 GitHub リポジトリ (owner/repo) の解決ロジック（FastAPI 非依存・CLI/Web 共有可）。

優先順位: 明示指定（CLI --github-repo）> Organization.github_repo > 環境変数 GITHUB_REPO
> target_repo の git origin リモート。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


def git_remote_github_repo(repo_path: Path) -> str | None:
    """target_repo の origin リモートから owner/repo を推定する（best-effort）。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:  # noqa: BLE001 - git 不在 / 非リポジトリは推定不能として扱う
        return None
    url = (result.stdout or "").strip()
    if not url or "github.com" not in url:
        return None
    tail = url.removesuffix(".git").split("github.com", 1)[-1].lstrip(":/")
    parts = [segment for segment in tail.split("/") if segment]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return None


def resolve_github_repo(explicit: str | None, org: Any, repo_path: Path) -> str | None:
    """PR 作成用の GitHub リポジトリ (owner/repo) を解決する。"""
    if explicit:
        return str(explicit)
    org_repo = getattr(org, "github_repo", None)
    if org_repo:
        return str(org_repo)
    env_repo = os.getenv("GITHUB_REPO")
    if env_repo:
        return env_repo
    return git_remote_github_repo(repo_path)
