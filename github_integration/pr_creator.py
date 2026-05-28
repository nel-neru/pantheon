"""
GitHub Integration - PR Creator

PyGithub を使ってブランチ作成・ファイル更新・PR 作成を行う。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


async def create_improvement_pr(
    repo_path: Path,
    github_token: str,
    github_repo: str,
    file_path: str,
    modified_content: str,
    suggestion: Dict[str, Any],
) -> str:
    """
    改善提案を元に GitHub に PR を作成する。

    Args:
        repo_path: ローカルリポジトリのパス（未使用だが将来の拡張用に保持）
        github_token: GitHub Personal Access Token
        github_repo: "owner/repo" 形式のリポジトリ識別子
        file_path: 変更するファイルの相対パス
        modified_content: 変更後のファイル全体の内容
        suggestion: 改善提案の dict

    Returns:
        作成された PR の URL
    """
    try:
        from github import Github, GithubException
    except ImportError:
        raise ImportError("PyGithub が必要です: pip install PyGithub")

    g = Github(github_token)
    repo = g.get_repo(github_repo)

    slug = re.sub(r"[^a-z0-9]+", "-", suggestion.get("title", "improvement").lower())[:40]
    branch_name = f"repocorp/improvement-{slug}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    default_branch = repo.get_branch(repo.default_branch)
    repo.create_git_ref(f"refs/heads/{branch_name}", default_branch.commit.sha)

    try:
        file_obj = repo.get_contents(file_path, ref=repo.default_branch)
        repo.update_file(
            path=file_path,
            message=f"refactor: {suggestion.get('title', 'Apply improvement')}",
            content=modified_content,
            sha=file_obj.sha,
            branch=branch_name,
        )
    except GithubException:
        repo.create_file(
            path=file_path,
            message=f"feat: {suggestion.get('title', 'Apply improvement')}",
            content=modified_content,
            branch=branch_name,
        )

    pr = repo.create_pull(
        title=f"[RepoCorp AI] {suggestion.get('title', 'Improvement')}",
        body=_build_pr_body(suggestion),
        head=branch_name,
        base=repo.default_branch,
    )
    return pr.html_url


def _build_pr_body(suggestion: Dict[str, Any]) -> str:
    return (
        "## 🤖 RepoCorp AI による自動改善\n\n"
        f"**改善提案**: {suggestion.get('title')}\n\n"
        f"**説明**: {suggestion.get('description')}\n\n"
        f"**期待される効果**: {suggestion.get('expected_impact', '未定義')}\n\n"
        f"**優先度**: {suggestion.get('priority', 'medium')}\n\n"
        f"**カテゴリ**: {suggestion.get('category', 'general')}\n\n"
        "---\n"
        "*このPRは [RepoCorp AI](https://github.com/) によって自動生成されました。*"
    )
