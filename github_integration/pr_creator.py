"""
GitHub Integration - PR Creator

PyGithub を使ってブランチ作成・ファイル更新・PR 作成を行う。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def branch_slug(title: str | None) -> str:
    """改善タイトルから git ブランチ名に使える安全な slug を作る。

    PR 経路（本関数）とローカル適用経路（improvement_executor_agent._apply_local_change）の
    両方が同じブランチ命名規約 ``pantheon/improvement-<slug>-<ts>`` を使うため、両者が import
    して slug ロジックを一元化する（同一バグの二重実装を防ぐ）。

    ``[^a-z0-9]+`` を ``-`` に畳むだけだと、日本語タイトル（本プロジェクトの提案の主言語）は
    全文字が非 ASCII で slug が空または ``-`` だけに退化し、全提案のブランチ名が
    ``pantheon/improvement---<timestamp>`` と区別不能・非記述的になる。ASCII を含む場合は
    その英数字部分を活かしつつ、退化したら**タイトルの安定ハッシュ**へフォールバックして、
    ブランチ名が必ず有効かつ提案ごとに識別可能になるようにする（``None``/空も安全に処理）。
    """
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower())[:40].strip("-")
    if base:
        return base
    # 非 ASCII のみ/空 → タイトルの短いハッシュ（先頭英字で git ref を必ず有効に）。
    return "x" + hashlib.sha1((title or "").encode("utf-8")).hexdigest()[:8]


def suggestion_title(suggestion: Dict[str, Any], default: str = "Improvement") -> str:
    """suggestion の title を表示用に返す。None/空/不在なら ``default``。

    ``suggestion`` は検証済み ImprovementProposal ではなく task 入力の自由形式 dict なので
    title が None・不在になり得る。``suggestion.get("title", default)`` は **キーが None 値で
    存在する場合に default ではなく None を返す**ため、commit メッセージや PR タイトルに literal
    ``"None"`` が紛れ込む（例: ``refactor: None``・``[Pantheon] None``）。truthy 判定で
    None/空文字をまとめて default に落とす（``branch_slug`` の ``title or ...`` と同じ防御）。
    PR 経路（``pr_creator``）とローカル適用経路（``improvement_executor_agent``）の両方が
    import して描画ロジックを一元化する（同一バグの二重実装を防ぐ）。
    """
    value = suggestion.get("title")
    return str(value) if value else default


def suggestion_description(suggestion: Dict[str, Any], default: str = "(説明なし)") -> str:
    """suggestion の description を表示用に返す。None/空/不在なら ``default``（literal ``"None"`` 防止）。"""
    value = suggestion.get("description")
    return str(value) if value else default


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

    slug = branch_slug(suggestion.get("title") or "improvement")
    branch_name = (
        f"pantheon/improvement-{slug}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )

    default_branch = repo.get_branch(repo.default_branch)
    if hasattr(repo, "create_git_ref"):
        repo.create_git_ref(f"refs/heads/{branch_name}", default_branch.commit.sha)

    try:
        file_obj = repo.get_contents(file_path, ref=repo.default_branch)
        repo.update_file(
            path=file_path,
            message=f"refactor: {suggestion_title(suggestion, 'Apply improvement')}",
            content=modified_content,
            sha=file_obj.sha,
            branch=branch_name,
        )
    except GithubException as exc:
        if getattr(exc, "status", 404) != 404:
            raise  # 401/403/422/429/5xx は真因を握り潰さず表に出す
        repo.create_file(
            path=file_path,
            message=f"feat: {suggestion_title(suggestion, 'Apply improvement')}",
            content=modified_content,
            branch=branch_name,
        )

    pr = repo.create_pull(
        title=f"[Pantheon] {suggestion_title(suggestion)}",
        body=_build_pr_body(suggestion),
        head=branch_name,
        base=repo.default_branch,
    )
    return pr.html_url


def _build_pr_body(suggestion: Dict[str, Any]) -> str:
    return (
        "## 🤖 Pantheon による自動改善\n\n"
        f"**改善提案**: {suggestion_title(suggestion)}\n\n"
        f"**説明**: {suggestion_description(suggestion)}\n\n"
        f"**期待される効果**: {suggestion.get('expected_impact') or '未定義'}\n\n"
        f"**優先度**: {suggestion.get('priority') or 'medium'}\n\n"
        f"**カテゴリ**: {suggestion.get('category') or 'general'}\n\n"
        "---\n"
        "*このPRは Pantheon によって自動生成されました。*"
    )
