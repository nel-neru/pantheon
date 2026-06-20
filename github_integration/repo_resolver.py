"""
PR 対象 GitHub リポジトリ (owner/repo) の解決ロジック（FastAPI 非依存・CLI/Web 共有可）。

優先順位: 明示指定（CLI --github-repo）> Organization.github_repo > 環境変数 GITHUB_REPO
> target_repo の git origin リモート。
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.runtime.process_utils import no_window_kwargs

# GitHub の正規ホスト（部分文字列一致では `github.com.evil.com` を誤受理するため厳密一致にする）。
_GITHUB_HOSTS = {"github.com", "www.github.com"}
# owner / repo セグメントの許容書式（GitHub の命名に準拠・パスインジェクション防止）。
_GH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
# scp 風 SSH（git@github.com:owner/repo）の分解。
_SCP_SSH_RE = re.compile(r"^[A-Za-z0-9._-]+@([^:/]+):(.+)$")


def parse_github_owner_repo(url: str) -> str | None:
    """git remote URL から ``owner/repo`` を **host 検証付き**で厳密抽出する（best-effort）。

    旧実装は ``"github.com" in url`` の部分文字列一致 + ``split("github.com")`` で、
    ``https://github.com.evil.com/owner/repo`` のような偽装ホストを誤って受理していた
    （リポジトリ confusion の入口）。ここでは host を ``github.com``/``www.github.com`` に
    厳密一致させ、owner/repo もホワイトリスト書式で検証する。SSH(scp 風)/HTTPS 双方に対応。
    """
    url = (url or "").strip().removesuffix(".git")
    if not url:
        return None
    scp = _SCP_SSH_RE.match(url)
    if scp:
        host, path = scp.group(1), scp.group(2)
    else:
        parsed = urlparse(url)
        host, path = (parsed.hostname or ""), parsed.path
    if host.lower() not in _GITHUB_HOSTS:
        return None
    parts = [segment for segment in path.split("/") if segment]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if _GH_SEGMENT_RE.match(owner) and _GH_SEGMENT_RE.match(repo):
        return f"{owner}/{repo}"
    return None


def git_remote_github_repo(repo_path: Path) -> str | None:
    """target_repo の origin リモートから owner/repo を推定する（best-effort）。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            **no_window_kwargs(),
        )
    except Exception:  # noqa: BLE001 - git 不在 / 非リポジトリは推定不能として扱う
        return None
    return parse_github_owner_repo(result.stdout or "")


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
