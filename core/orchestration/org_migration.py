"""
WS-1: repo 紐付き Organization → workspace モードへの移行コア（計画書 §5）。

repo モードの Organization（git リポジトリ紐付け）を workspace モード
（アプリ内データ管理・git 不要）へ変換するための **純粋なモデル変換** を提供する。

設計方針:
- **git 操作やファイル削除・実データ移動は一切しない**。ここで行うのはモデル属性の更新と
  移行後 workspace パスの決定のみ。実データの移動は後続処理／呼び出し側の責務とする。
- 決定論・冪等。同じ入力に対して常に同じ結果を返し、すでに workspace モードの org に
  対しては no-op（そのまま返す／already_workspace=True）。
- LLM 非依存。外部 I/O なし（パス計算のみ）。

移行元（target_repo_path）は **履歴／移行元として保持** する（消さない）。これにより
「どの repo から workspace 化したか」の来歴を後段が参照できる。
"""

from __future__ import annotations

import re
from pathlib import Path

from core.models.organization import Organization

# safe 化: 英数・アンダースコア・ハイフン以外の文字を 1 文字ずつ "-" に置換する。
# workspace ディレクトリ名として OS 横断で安全な名前を決定論的に作るための単一規則。
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_-]")


def _safe_name(name: str) -> str:
    """org 名を workspace ディレクトリ名として安全な形へ正規化する（決定論）。

    英数・``_``・``-`` 以外を ``-`` に置換する。空になった場合は ``"org"`` を返し、
    常に非空のディレクトリ名を保証する。
    """
    safe = _UNSAFE_NAME_CHARS.sub("-", name or "")
    return safe or "org"


def _target_workspace_path(org: Organization, workspace_root: str | Path) -> str:
    """移行後の workspace_path（``workspace_root / safe(org.name)``）を絶対パス文字列で返す。"""
    root = Path(workspace_root)
    # Organization.workspace_path は絶対パス必須（validator）。resolve せず絶対化のみ行い、
    # 決定論を保つ（resolve はシンボリックリンク等で環境依存になりうるため避ける）。
    target = (root / _safe_name(org.name)).absolute()
    return str(target)


def plan_repo_to_workspace_migration(
    org: Organization,
    *,
    workspace_root: str | Path,
) -> dict:
    """repo→workspace 移行の **計画** を返す（モデルは変更しない・副作用なし）。

    org が repo モードなら、移行後の workspace_path（``workspace_root / safe(org.name)``）と
    移行元 repo パスを含む計画 dict を返す。すでに workspace モードなら
    ``already_workspace=True`` を立てて返す（移行不要）。

    Returns 例（repo モード）::

        {
            "org_name": "Foo Bar",
            "from_repo": "C:/path/to/repo",
            "to_workspace": "C:/.../workspaces/Foo-Bar",
            "already_workspace": False,
        }
    """
    if org.management_mode == "workspace":
        return {
            "org_name": org.name,
            "from_repo": org.target_repo_path,
            # すでに workspace の場合は現行 workspace_path をそのまま提示する。
            "to_workspace": org.workspace_path,
            "already_workspace": True,
        }

    return {
        "org_name": org.name,
        "from_repo": org.target_repo_path,
        "to_workspace": _target_workspace_path(org, workspace_root),
        "already_workspace": False,
    }


def migrate_repo_org_to_workspace(
    org: Organization,
    *,
    workspace_root: str | Path,
) -> Organization:
    """org を **workspace モードへ変換** して返す（属性代入で更新・冪等）。

    - ``management_mode`` を ``"workspace"`` に設定する。
    - ``workspace_path`` を ``workspace_root / safe(org.name)``（絶対パス）に設定する。
    - ``target_repo_path`` は **保持**（履歴／移行元として残す。git 操作・削除はしない）。

    すでに workspace モードの org はそのまま返す（no-op・冪等）。実データの移動は行わない
    （呼び出し側が結果を保存し、必要なら別途データ移送する）。
    """
    if org.management_mode == "workspace":
        return org

    target = _target_workspace_path(org, workspace_root)
    # Pydantic v2: 属性代入で更新する（target_repo_path は意図的に保持）。
    org.management_mode = "workspace"
    org.workspace_path = target
    return org
