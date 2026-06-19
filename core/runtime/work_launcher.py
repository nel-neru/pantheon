"""
Work launcher — 実行系の作業を wmux の「監視セッション」として着火する。

設計方針（Web GUI=監視 / wmux=対話・実行）に従い、analyze / goal / apply といった実行系を
Web の in-process ストリームではなく、**Pantheon のサブコマンドを wmux タブ（headless 時は
サブプロセス）で起動**して走らせる。これにより:

  * 既存の Python パイプライン（提案生成・永続化など）がそのまま動く（生 claude ではない）。
  * 1 作業 = 1 セッション（``<repo>/.pantheon/sessions/<id>/``）として永続化され、Web GUI の
    セッション／プラットフォームでライブ監視できる。

呼び出し元は主に wmux 汎用／組織チャットの REPL（``/analyze`` ``/goal``）。GUI も将来この経路を
使える。multiplexer が無い環境では :class:`SessionOrchestrator` が headless にフォールバックする。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, List, Optional

from core.runtime.session_orchestrator import SessionOrchestrator, SessionRecord


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text or "").strip("-").lower() or "work"


def self_command(*args: str) -> List[str]:
    """この Pantheon 自身を再呼び出しする argv を返す（frozen exe / ソース両対応）。"""
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    from core.paths import resource_root

    return [sys.executable, str(resource_root() / "main.py"), *args]


def _default_repo_root(repo_root: Optional[Path]) -> Path:
    """セッション永続化先のルート。

    Web の監視側（``web.server._session_orchestrator``）は ``PROJECT_ROOT =
    resource_root()`` 配下の ``.pantheon/sessions`` を読む。生産者（ここ）が
    ``cwd`` 既定だと frozen exe（``resource_root()`` = ``sys._MEIPASS`` の一時ディレクトリ）
    などで生産/消費ディレクトリが食い違い、着火したセッションが GUI に出ない。
    既定を ``resource_root()`` に揃えて producer == consumer を保証する。
    """
    if repo_root is not None:
        return Path(repo_root)
    from core.paths import resource_root

    return resource_root()


def _next_index(orch: SessionOrchestrator, group: str, kind: str) -> int:
    """``group`` 内の ``kind#N`` 連番の次の番号を返す（既存セッションから算出）。"""
    n = 0
    for rec in orch.list_sessions():
        if rec.name != group:
            continue
        for sr in rec.surfaces:
            title = str(sr.get("title", ""))
            if title.startswith(f"{kind}#"):
                n = max(n, _trailing_int(title))
    return n + 1


def _trailing_int(title: str) -> int:
    m = re.search(r"#(\d+)$", title)
    return int(m.group(1)) if m else 0


def launch_analyze(
    org_name: str,
    *,
    max_files: int = 15,
    repo_root: Optional[Path] = None,
    prefer: Optional[str] = None,
) -> SessionRecord:
    """``pantheon analyze --org-name <org>`` を ``<org> · analyze#N`` タブで起動する。"""
    orch = SessionOrchestrator(_default_repo_root(repo_root), prefer=prefer)
    n = _next_index(orch, org_name, "analyze")
    return orch.start_command_session(
        name=org_name,
        command=self_command("analyze", "--org-name", org_name, "--max-files", str(max_files)),
        title=f"analyze#{n}",
        agent_id=f"work:{_slug(org_name)}:analyze:{n}",
        role="analyze",
    )


def launch_goal(
    goal_text: str,
    *,
    org_name: Optional[str] = None,
    repo_root: Optional[Path] = None,
    prefer: Optional[str] = None,
) -> SessionRecord:
    """``pantheon goal run <text>`` を ``<group> · goal#N`` タブで起動する。"""
    group = org_name or "Pantheon"
    orch = SessionOrchestrator(_default_repo_root(repo_root), prefer=prefer)
    n = _next_index(orch, group, "goal")
    return orch.start_command_session(
        name=group,
        command=self_command("goal", "run", goal_text),
        title=f"goal#{n}",
        agent_id=f"work:{_slug(group)}:goal:{n}",
        role="goal",
    )


def launch_apply(
    proposal_id: str,
    org_name: str,
    *,
    repo_root: Optional[Path] = None,
    prefer: Optional[str] = None,
) -> SessionRecord:
    """``pantheon approve <id> --org-name <org>`` を ``<org> · apply#N`` タブで起動する。"""
    orch = SessionOrchestrator(_default_repo_root(repo_root), prefer=prefer)
    n = _next_index(orch, org_name, "apply")
    return orch.start_command_session(
        name=org_name,
        command=self_command("approve", proposal_id, "--org-name", org_name, "--yes"),
        title=f"apply#{n}",
        agent_id=f"work:{_slug(org_name)}:apply:{n}",
        role="apply",
    )


def dispatch_task(
    task: dict[str, Any],
    *,
    repo_root: Optional[Path] = None,
    prefer: Optional[str] = None,
) -> SessionRecord:
    """作業ボードの 1 タスクを wmux の work セッションへ着火する（type→launch 振り分け）。

    web の drain ループ（``web.server._dispatch_task_to_wmux``）と CLI の
    ``pantheon tasks drain`` の共通チョークポイント。analyze/review/improve かつ
    org 指定があれば ``launch_analyze``、それ以外は ``launch_goal`` に流す。
    """
    ttype = str(task.get("type", "custom"))
    org = task.get("org_name") or "Pantheon"
    desc = task.get("description") or ""
    if ttype in ("analyze", "review", "improve") and task.get("org_name"):
        return launch_analyze(org, repo_root=repo_root, prefer=prefer)
    return launch_goal(
        desc or ttype, org_name=task.get("org_name"), repo_root=repo_root, prefer=prefer
    )
