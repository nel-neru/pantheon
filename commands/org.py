from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.models.organization import ImprovementProposal


def _print_proposal(proposal: dict[str, Any]) -> None:
    print(f"  ID       : {proposal.get('id')}")
    print(f"  タイトル : {proposal.get('title')}")
    print(f"  優先度   : {proposal.get('priority')}")
    if proposal.get("file_path"):
        print(f"  ファイル : {proposal.get('file_path')}")
    print(f"  説明     : {str(proposal.get('description', ''))[:100]}...")
    print()


def _find_pending_proposal(
    proposals: list[dict[str, Any]], proposal_id: str
) -> dict[str, Any] | None:
    return next(
        (proposal for proposal in proposals if str(proposal.get("id", "")).startswith(proposal_id)),
        None,
    )


def _print_org(org, pending_count: int) -> None:
    print(f"\nOrganization 詳細 — {org.name}\n")
    print(f"  ID        : {org.id}")
    print(f"  状態      : {org.status.value}")
    print(f"  目的      : {org.purpose}")
    print(f"  リポジトリ: {org.target_repo_path or '(未設定)'}")
    print(f"  分離レベル: {getattr(org, 'isolation_level', 'standard')}")
    print(f"  作成日時  : {org.created_at.isoformat()}")
    print(f"  最終活動  : {org.last_active.isoformat()}")
    print(f"  自律度    : {org.autonomy_score:.1f}")
    print(f"  成長速度  : {org.improvement_velocity:.1f}")
    print(f"  未対応提案: {pending_count} 件")
    agents = org.get_all_agents()
    print(f"  Agent数   : {len(agents)} 個")
    for division in org.divisions:
        print(f"  - Division: {division.name} [{division.type.value}]")
        for team in division.teams:
            print(
                f"    - Team: {team.name} [{team.division_type.value}] ({len(team.agents)} agents)"
            )
            for agent in team.agents:
                skills = " / ".join(getattr(skill, "value", skill) for skill in agent.skills)
                print(f"      - {agent.name} [{skills}]")
    print()


async def cmd_init(args: argparse.Namespace, *, get_psm: Any, get_platform_home: Any) -> None:
    """グローバルプラットフォームを初期化する"""
    from core.bootstrap import bootstrap_platform

    psm = get_psm()
    if psm.is_initialized():
        orgs = psm.load_organizations()
        print("[OK] プラットフォームはすでに初期化されています")
        print(f"   場所    : {psm.platform_home}")
        print(f"   子会社数 : {len(orgs)} 個")
        print('\n次のステップ: pantheon org add --name "MyApp" --repo /path/to/app')
        return

    bootstrap_platform()
    print("\n[OK] Pantheon プラットフォームを初期化しました")
    print(f"   場所: {get_platform_home()}")
    print('\n次のステップ: pantheon org add --name "MyApp" --repo /path/to/app')


async def cmd_org_add(args: argparse.Namespace, *, get_psm: Any, project_root: Path) -> None:
    """新しい Organization（子会社）を担当リポジトリ付きで登録する"""
    from core.bootstrap import bootstrap_platform
    from core.org_factory import create_default_organization, create_organization_from_template

    psm = bootstrap_platform()

    existing = psm.load_organization_by_name(args.name)
    if existing:
        print(f"[WARN] Organization '{args.name}' はすでに存在します (ID: {existing.id})")
        return

    # 中核モデル「1 ワークスペース = 1 Organization」: repo は必須（argparse で required）。
    repo_path = Path(args.repo).resolve()
    if not repo_path.exists():
        print(f"[ERROR] リポジトリパスが存在しません: {repo_path}")
        sys.exit(1)

    isolation_level = getattr(args, "isolation_level", "standard")
    if args.template:
        template_path = project_root / "config" / "departments" / f"{args.template}.yaml"
        org = create_organization_from_template(
            args.name,
            args.purpose or "",
            template_path,
            repo_path=repo_path,
            isolation_level=isolation_level,
        )
    else:
        org = create_default_organization(
            args.name,
            args.purpose or "",
            repo_path=repo_path,
            isolation_level=isolation_level,
        )
    psm.save_organization(org)

    agents = org.get_all_agents()
    print("\n[OK] Organization を登録しました\n")
    print(f"  名前      : {org.name}")
    print(f"  目的      : {org.purpose}")
    print(f"  リポジトリ: {org.target_repo_path}")
    print(f"  分離レベル: {getattr(org, 'isolation_level', 'standard')}")
    print(f"  ID        : {org.id}")
    print(f"  Division  : {len(org.divisions)} 個 / Agent: {len(agents)} 個")
    for agent in agents:
        skills = " / ".join(getattr(skill, "value", skill) for skill in agent.skills)
        print(f"    - {agent.name} [{skills}]")
    print(f'\n次のステップ: pantheon analyze --org-name "{org.name}"')


def _find_git_repos(parent: Path, depth: int = 1) -> list[Path]:
    """``parent`` 配下の git リポジトリ（``.git`` を持つディレクトリ）を浅く探索して返す。

    depth=1 は直下のみ。ネストした巨大ツリーを舐めないよう既定は浅い探索にする。
    """
    repos: list[Path] = []
    if not parent.is_dir():
        return repos
    if (parent / ".git").exists():
        repos.append(parent)
    if depth >= 1:
        for child in sorted(parent.iterdir()):
            try:
                if child.is_dir() and (child / ".git").exists():
                    repos.append(child)
            except OSError:
                continue
    # 重複除去（同一パスを1つに）
    seen: set[str] = set()
    unique: list[Path] = []
    for r in repos:
        key = str(r.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


async def cmd_org_scan(args: argparse.Namespace, *, get_psm: Any) -> None:
    """親フォルダ配下の git リポジトリを検出し、未登録のものをワークスペースとして登録する。

    中核モデル「1 ワークスペース = 1 Organization」: 検出した repo ごとに、フォルダ名を
    既定の Organization 名として登録する（既登録の repo はスキップ）。``--yes`` で一括登録、
    無指定なら候補を表示するだけ。
    """
    from core.org_factory import create_default_organization

    if getattr(args, "parent", None):
        parent = Path(args.parent).expanduser().resolve()
    else:
        from core.paths import resource_root

        parent = resource_root().parent  # 既定: Pantheon リポジトリの親フォルダ

    if not parent.is_dir():
        print(f"[ERROR] 親フォルダが存在しません: {parent}")
        sys.exit(1)

    psm = get_psm()
    repos = _find_git_repos(parent)
    if not repos:
        print(f"git リポジトリが見つかりませんでした: {parent}")
        return

    new_repos = [r for r in repos if psm.load_organization_by_repo(r) is None]
    registered = [r for r in repos if psm.load_organization_by_repo(r) is not None]

    print(f"\nスキャン: {parent}")
    print(f"  検出 {len(repos)} 件 / 既登録 {len(registered)} 件 / 新規 {len(new_repos)} 件\n")
    for r in registered:
        org = psm.load_organization_by_repo(r)
        print(f"  [済] {r.name}  →  {org.name if org else '?'}")
    for r in new_repos:
        print(f"  [新] {r.name}  →  (Organization名: {r.name})")

    if not new_repos:
        print("\n新規に登録するワークスペースはありません。")
        return

    if not getattr(args, "yes", False):
        print("\n登録するには --yes を付けて再実行してください:")
        print(f"  pantheon org scan {parent} --yes")
        return

    added = 0
    for r in new_repos:
        name = r.name
        if psm.load_organization_by_name(name):
            print(f"  [スキップ] '{name}' は同名 Organization が既に存在します")
            continue
        org = create_default_organization(name, f"{name} のワークスペース", repo_path=str(r))
        psm.save_organization(org)
        added += 1
        print(f"  [登録] {name}  →  {r}")
    print(f"\n[OK] {added} 件のワークスペースを登録しました。")


async def cmd_org_list(args: argparse.Namespace, *, get_psm: Any) -> None:
    """登録済み Organization を一覧表示する"""
    psm = get_psm()
    orgs = psm.load_organizations()

    if not orgs:
        print("Organization が登録されていません。")
        print("\nヒント: pantheon org add --name MyApp --repo /path/to/app")
        return

    print(f"\nOrganization 一覧 ({len(orgs)} 件)\n")
    for org in orgs:
        state_manager = psm.get_org_state_manager(org)
        pending = len(state_manager.get_pending_improvement_proposals(limit=100))
        print(f"  {org.name}")
        print(f"    リポジトリ : {org.target_repo_path or '(未設定)'}")
        print(f"    目的       : {org.purpose[:60]}")
        print(f"    ステータス : {org.status.value}")
        print(f"    Agent数    : {len(org.get_all_agents())} 個")
        print(f"    未対応提案 : {pending} 件")
        print()


async def cmd_org_show(args: argparse.Namespace, *, get_psm: Any) -> None:
    psm = get_psm()
    org = psm.load_organization_by_name(args.name)
    if not org:
        print(f"[ERROR] Organization '{args.name}' が見つかりません。")
        sys.exit(1)

    state_manager = psm.get_org_state_manager(org)
    pending = len(state_manager.get_pending_improvement_proposals(limit=100))
    _print_org(org, pending)


async def cmd_org_remove(args: argparse.Namespace, *, confirm_action: Any, get_psm: Any) -> None:
    """Organization を削除する"""
    psm = get_psm()
    org = psm.load_organization_by_name(args.name)
    if not org:
        print(f"[ERROR] Organization '{args.name}' が見つかりません。")
        sys.exit(1)
    if getattr(org, "is_system", False) and not getattr(args, "force", False):
        print(f"[ERROR] '{args.name}' はシステム Organization のため削除できません。")
        print("   どうしても削除する場合は --force を指定してください。")
        sys.exit(1)
    if not confirm_action(
        f"Organization '{args.name}' を削除します。関連する設定参照が使えなくなる可能性があります。続行しますか?",
        assume_yes=getattr(args, "yes", False),
    ):
        print("[INFO] 削除を中止しました。")
        return
    psm.remove_organization(str(org.id))
    print(f"[OK] Organization '{args.name}' を削除しました。")


async def cmd_analyze(args: argparse.Namespace, *, get_orchestrator: Any, get_psm: Any) -> None:
    """Organization の担当リポジトリを分析して改善提案を生成する"""
    from agents.base import AgentTask
    from core.state.manager import RepoStateManager

    psm = get_psm()
    org = psm.load_organization_by_name(args.org_name)
    if not org:
        print(f"[ERROR] Organization '{args.org_name}' が見つかりません。")
        print("   pantheon org list で登録済みの一覧を確認してください。")
        sys.exit(1)

    repo_path = Path(org.target_repo_path) if org.target_repo_path else Path(".")
    print(f"\n{org.name} のコード分析を開始します...")
    print(f"   リポジトリ: {repo_path}\n")

    state_manager = RepoStateManager(repo_path, org.name)
    agent = get_orchestrator()
    task = AgentTask(
        task_type="code_review",
        description=f"{org.name} のコードレビューと改善提案生成",
        input={"repo_path": str(repo_path), "max_files": args.max_files},
    )

    result = await agent.run(task)
    if not result.success:
        print(f"[ERROR] 分析失敗: {result.error}")
        sys.exit(1)

    suggestions = result.output.get("suggestions", [])
    files = result.output.get("files_reviewed", 0)
    print(f"[OK] {files} ファイルを分析し、{len(suggestions)} 件の改善提案を生成しました。\n")

    for suggestion in suggestions:
        proposal = ImprovementProposal(
            review_id=uuid4(),
            priority=suggestion.get("priority", "medium"),
            category=suggestion.get("category", "general"),
            title=suggestion.get("title", "改善提案"),
            description=suggestion.get("description", ""),
            file_path=suggestion.get("file_path", ""),
            expected_impact=suggestion.get("expected_impact", ""),
        )
        state_manager.save_improvement_proposal(proposal)
        badge = (
            "[HIGH]"
            if proposal.priority == "high"
            else "[MEDIUM]"
            if proposal.priority == "medium"
            else "[LOW]"
        )
        print(f"  {badge} [{proposal.priority.upper():6}] {proposal.title}")
        if proposal.file_path:
            print(f"           ファイル: {proposal.file_path}")
        print(f"           {proposal.description[:80]}...")
        print()

    print(f"[OK] {len(suggestions)} 件を保存しました。")
    print(f'\n次のステップ: pantheon proposals --org-name "{org.name}"')


async def cmd_proposals(args: argparse.Namespace, *, get_psm: Any) -> None:
    """未対応の改善提案を一覧表示する"""
    psm = get_psm()
    org = psm.load_organization_by_name(args.org_name)
    if not org:
        print(f"[ERROR] Organization '{args.org_name}' が見つかりません。")
        sys.exit(1)

    state_manager = psm.get_org_state_manager(org)
    proposals = state_manager.get_pending_improvement_proposals(limit=50)

    if not proposals:
        print("未対応の改善提案はありません。")
        print(f'\nヒント: pantheon analyze --org-name "{org.name}"')
        return

    executable = [proposal for proposal in proposals if proposal.get("file_path")]
    meta = [proposal for proposal in proposals if not proposal.get("file_path")]

    print(f"\n未対応の改善提案 ({len(proposals)} 件) — {org.name}\n")
    if executable:
        print(f"【実行可能】 ({len(executable)} 件)")
        for proposal in executable:
            _print_proposal(proposal)
    if meta:
        print(f"【Meta-level（手動対応）】 ({len(meta)} 件)")
        for proposal in meta:
            _print_proposal(proposal)

    print(f'承認: pantheon approve <ID の最初の8文字> --org-name "{org.name}"')


async def cmd_proposal_show(args: argparse.Namespace, *, get_psm: Any) -> None:
    psm = get_psm()
    org = psm.load_organization_by_name(args.org_name)
    if not org:
        print(f"[ERROR] Organization '{args.org_name}' が見つかりません。")
        sys.exit(1)

    state_manager = psm.get_org_state_manager(org)
    proposal = _find_pending_proposal(
        state_manager.get_pending_improvement_proposals(limit=100), args.proposal_id
    )
    if not proposal:
        print(f"[ERROR] ID '{args.proposal_id}' に一致する未対応提案が見つかりません。")
        sys.exit(1)

    print(f"\n提案詳細 — {org.name}\n")
    for key in (
        "id",
        "title",
        "status",
        "priority",
        "category",
        "file_path",
        "expected_impact",
        "implementation_difficulty",
        "created_at",
    ):
        value = proposal.get(key, "")
        if key == "file_path" and not value:
            value = "(なし)"
        print(f"  {key:24}: {value}")
    print(f"  description              : {proposal.get('description', '')}")
    print()


async def cmd_proposal_reject(
    args: argparse.Namespace, *, confirm_action: Any, get_psm: Any
) -> None:
    psm = get_psm()
    org = psm.load_organization_by_name(args.org_name)
    if not org:
        print(f"[ERROR] Organization '{args.org_name}' が見つかりません。")
        sys.exit(1)

    state_manager = psm.get_org_state_manager(org)
    proposal = _find_pending_proposal(
        state_manager.get_pending_improvement_proposals(limit=100), args.proposal_id
    )
    if not proposal:
        print(f"[ERROR] ID '{args.proposal_id}' に一致する未対応提案が見つかりません。")
        sys.exit(1)

    if not confirm_action(
        f"提案 '{proposal.get('title')}' を却下しますか?", assume_yes=getattr(args, "yes", False)
    ):
        print("[INFO] 却下を中止しました。")
        return

    state_manager.update_proposal_status(str(proposal.get("id", "")), "rejected")
    print(f"[OK] 提案 '{proposal.get('title')}' を却下しました。")


async def cmd_proposal_apply(
    args: argparse.Namespace,
    *,
    confirm_action: Any,
    get_orchestrator: Any,
    get_psm: Any,
    require_api_key: Any,
) -> None:
    from agents.base import AgentTask

    # NOTE: require_api_key は LLM を使う file ベース適用の直前でのみ行う。
    # 構造介入 / content_asset は決定論的（claude CLI 不要）で、Web 経路とも挙動を揃える。
    psm = get_psm()
    org = psm.load_organization_by_name(args.org_name)
    if not org:
        print(f"[ERROR] Organization '{args.org_name}' が見つかりません。")
        sys.exit(1)

    state_manager = psm.get_org_state_manager(org)
    proposal = _find_pending_proposal(
        state_manager.get_pending_improvement_proposals(limit=100), args.proposal_id
    )
    if not proposal:
        print(f"[ERROR] ID '{args.proposal_id}' に一致する未対応提案が見つかりません。")
        sys.exit(1)

    # 承認は人間起点でも必ず PolicyEngine を通す（Web と同じ非交渉ルール）。
    from core.policy.engine import ApprovalDecision, OrgBoundaryContext, PolicyEngine

    policy_path = psm.platform_home / "policy.yaml"
    org_context = OrgBoundaryContext(
        isolation_level=getattr(org, "isolation_level", "standard"),
        allowed_path_scope=getattr(org, "allowed_path_scope", []),
    )
    verdict = PolicyEngine(policy_path if policy_path.exists() else None).evaluate(
        proposal, org_context=org_context
    )
    state_manager.update_proposal_fields(
        str(proposal.get("id", "")),
        policy_decision=verdict.decision.value,
        policy_reason=verdict.reason,
        policy_rule=verdict.rule_name,
    )
    if verdict.decision == ApprovalDecision.REJECT:
        print(f"[ERROR] ポリシーにより承認できません: {verdict.reason}")
        state_manager.update_proposal_status(str(proposal.get("id", "")), "rejected")
        sys.exit(1)

    # cross-org 構造介入は file_path を持たない。empty-file_path 棄却の前に専用 executor へ委任する。
    # 判定は PolicyEngine と同じ 4-way 述語に揃える（取りこぼし防止）。
    from core.models.organization import is_structural_intervention_dict

    if is_structural_intervention_dict(proposal):
        if not confirm_action(
            f"構造介入 '{proposal.get('title')}' を適用しますか?",
            assume_yes=getattr(args, "yes", False),
        ):
            print("[INFO] 適用を中止しました。")
            return
        state_manager.update_proposal_status(str(proposal.get("id", "")), "in_progress")
        from core.orchestration.structural_intervention import execute_structural_intervention

        result = await execute_structural_intervention(proposal, psm=psm)
        if not result.success:
            print(f"[ERROR] 構造介入の適用失敗: {result.error}")
            state_manager.update_proposal_status(str(proposal.get("id", "")), "failed")
            sys.exit(1)
        state_manager.update_proposal_status(str(proposal.get("id", "")), "done")
        print(f"[OK] 構造介入を適用しました: {result.output}")
        return

    # content_asset（ワークスペース内資産）は専用 executor で安全に書き込む。
    # file_path を持つが「既存ファイルの LLM 書換」ではないため、通常 executor の前に分岐。
    from core.models.organization import is_content_asset_dict

    if is_content_asset_dict(proposal):
        if not org.target_repo_path:
            print(
                "[ERROR] content_asset 提案には Organization の target_repo（ワークスペース）が必要です。"
            )
            state_manager.update_proposal_status(str(proposal.get("id", "")), "failed")
            sys.exit(1)
        if not confirm_action(
            f"コンテンツ資産 '{proposal.get('title')}' を適用しますか?",
            assume_yes=getattr(args, "yes", False),
        ):
            print("[INFO] 適用を中止しました。")
            return
        state_manager.update_proposal_status(str(proposal.get("id", "")), "in_progress")
        from core.orchestration.asset_application import execute_content_asset

        result = await execute_content_asset(proposal, repo_path=org.target_repo_path)
        if not result.success:
            print(f"[ERROR] コンテンツ資産の適用失敗: {result.error}")
            state_manager.update_proposal_status(str(proposal.get("id", "")), "failed")
            sys.exit(1)
        state_manager.update_proposal_status(str(proposal.get("id", "")), "done")
        print(f"[OK] コンテンツ資産を適用しました: {result.output}")
        return

    file_path = proposal.get("file_path", "")
    if not file_path:
        print("[ERROR] この提案は file_path がありません（meta-level 提案）。")
        state_manager.update_proposal_status(str(proposal.get("id", "")), "rejected")
        sys.exit(1)

    # ここから先は LLM（claude CLI）でコードを書き換える経路なので API キー（claude 可用性）を要求する。
    require_api_key("pantheon approve")

    repo_path = Path(org.target_repo_path) if org.target_repo_path else Path(".")
    print(f"\n改善提案を適用します: {proposal.get('title')}")
    print(f"   ファイル   : {file_path}")
    print(f"   リポジトリ : {repo_path}\n")

    if not confirm_action(
        f"提案 '{proposal.get('title')}' を適用しますか?",
        assume_yes=getattr(args, "yes", False),
    ):
        print("[INFO] 適用を中止しました。")
        return

    state_manager.update_proposal_status(str(proposal.get("id", "")), "in_progress")
    github_token = args.github_token or os.getenv("GITHUB_TOKEN")

    from github_integration.repo_resolver import resolve_github_repo

    github_repo = resolve_github_repo(getattr(args, "github_repo", None), org, repo_path)

    executor = get_orchestrator()
    task = AgentTask(
        task_type="improvement_execution",
        description=f"改善提案の適用: {proposal.get('title')}",
        input={
            "repo_path": str(repo_path),
            "suggestion": proposal,
            "github_token": github_token,
            "github_repo": github_repo,
        },
    )

    result = await executor.run(task)
    if not result.success:
        print(f"[ERROR] 適用失敗: {result.error}")
        state_manager.update_proposal_status(str(proposal.get("id", "")), "failed")
        sys.exit(1)

    state_manager.update_proposal_status(str(proposal.get("id", "")), "done")
    if "pr_url" in result.output:
        print(f"[OK] PR を作成しました: {result.output['pr_url']}")
    elif "branch" in result.output:
        print(f"[OK] ローカルブランチを作成しました: {result.output['branch']}")
        print(f"   変更内容: {result.output.get('change_summary')}")
    else:
        print(f"[OK] 完了: {result.output}")


async def cmd_query(
    args: argparse.Namespace,
    *,
    get_platform_home: Any,
    parse_query_filters: Any,
    get_psm: Any = None,
) -> None:
    """改善提案を検索する。

    ストアの主従:
      - 正準（source of truth）: 各リポジトリ内 JSON（RepoStateManager / <repo>/.pantheon/improvements）。
        ``--org-name`` 指定時はこちらを読む。
      - 副（任意のクエリ用ミラー）: グローバル SQLite（StateMigrator で投入）。
        ``--org-name`` を付けない、または ``--db-path`` 指定時はこちらを読む。
    """
    try:
        field_filters = parse_query_filters(getattr(args, "filter", ""))
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    limit = getattr(args, "limit", 50)
    org_name = getattr(args, "org_name", None)

    if org_name and not getattr(args, "db_path", None):
        # 正準 JSON ストアを読む
        if get_psm is None:
            print("[ERROR] 内部エラー: get_psm が利用できません。")
            sys.exit(1)
        psm = get_psm()
        org = psm.load_organization_by_name(org_name)
        if not org:
            print(f"[ERROR] Organization '{org_name}' が見つかりません。")
            sys.exit(1)
        sm = psm.get_org_state_manager(org)
        # SQLite ミラーと同様に全ステータスを対象にする（status=done 等の filter も効くように）
        improvements_dir = sm.state_dir / "improvements"
        rows = []
        if improvements_dir.exists():
            import json as _json

            for path in sorted(improvements_dir.glob("*.json")):
                try:
                    rows.append(_json.loads(path.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    continue
        for key, value in field_filters.items():
            rows = [r for r in rows if str(r.get(key, "")) == value]
        rows = rows[:limit]
    else:
        # 副 SQLite ミラーを読む（後方互換）
        from core.state.sqlite_manager import SQLiteStateManager

        db_path = (
            Path(args.db_path).expanduser().resolve()
            if getattr(args, "db_path", None)
            else get_platform_home() / "state.db"
        )
        manager = SQLiteStateManager(db_path)
        try:
            rows = manager.query_proposals(field_filters=field_filters, limit=limit)
        finally:
            manager.close()

    if not rows:
        print("条件に一致する提案はありません。")
        return

    print(f"\nQuery Results ({len(rows)} 件)\n")
    for row in rows:
        print(f"  ID       : {row.get('id')}")
        print(f"  タイトル : {row.get('title')}")
        print(f"  優先度   : {row.get('priority')}")
        print(f"  ステータス: {row.get('status')}")
        if row.get("file_path"):
            print(f"  ファイル : {row.get('file_path')}")
        print()


async def cmd_approve(
    args: argparse.Namespace,
    *,
    confirm_action: Any,
    get_orchestrator: Any,
    get_psm: Any,
    require_api_key: Any,
) -> None:
    """改善提案を承認してコードに適用し PR またはローカルブランチを作成する"""
    await cmd_proposal_apply(
        args,
        confirm_action=confirm_action,
        get_orchestrator=get_orchestrator,
        get_psm=get_psm,
        require_api_key=require_api_key,
    )


def register(subparsers: Any) -> None:
    init_parser = subparsers.add_parser("init", help="グローバルプラットフォームを初期化する")
    init_parser.set_defaults(handler_name="cmd_init")

    org_parser = subparsers.add_parser("org", help="Organization（子会社）の管理")
    org_sub = org_parser.add_subparsers(dest="org_command", required=True)

    add_parser = org_sub.add_parser(
        "add", help="新しい Organization を担当ワークスペース（repo）付きで登録する"
    )
    add_parser.add_argument("--name", required=True, help="Organization 名")
    add_parser.add_argument(
        "--repo",
        required=True,
        help="担当ワークスペース（git リポジトリ）の絶対パス。1 Organization = 1 repo（必須）",
    )
    add_parser.add_argument("--purpose", default="", help="Organization の目的・ゴール")
    add_parser.add_argument(
        "--template", default=None, help="テンプレート名（例: meta_improvement）"
    )
    add_parser.add_argument(
        "--isolation-level",
        choices=["core", "standard", "external"],
        default="standard",
        help="組織の分離レベル（external=外部目的・自ワークスペース外への変更を制限）",
    )
    add_parser.set_defaults(handler_name="cmd_org_add")

    list_parser = org_sub.add_parser("list", help="Organization の一覧を表示する")
    list_parser.set_defaults(handler_name="cmd_org_list")

    scan_parser = org_sub.add_parser(
        "scan", help="親フォルダ配下の git リポジトリを検出してワークスペース登録する"
    )
    scan_parser.add_argument(
        "parent",
        nargs="?",
        default=None,
        help="スキャンする親フォルダ（省略時は Pantheon リポジトリの親）",
    )
    scan_parser.add_argument(
        "--yes", action="store_true", help="検出した新規 repo を確認なしで一括登録する"
    )
    scan_parser.set_defaults(handler_name="cmd_org_scan")

    show_parser = org_sub.add_parser("show", help="Organization の詳細を表示する")
    show_parser.add_argument("--name", required=True, help="Organization 名")
    show_parser.set_defaults(handler_name="cmd_org_show")

    remove_parser = org_sub.add_parser("remove", help="Organization を削除する")
    remove_parser.add_argument("--name", required=True, help="削除する Organization 名")
    remove_parser.add_argument("--yes", action="store_true", help="確認を省略して削除する")
    remove_parser.add_argument(
        "--force",
        action="store_true",
        help="システム Organization（Meta-Improvement 等）でも強制的に削除する",
    )
    remove_parser.set_defaults(handler_name="cmd_org_remove")

    analyze_parser = subparsers.add_parser("analyze", help="担当リポジトリを分析して改善提案を生成")
    analyze_parser.add_argument("--org-name", required=True, help="対象 Organization 名")
    analyze_parser.add_argument("--max-files", type=int, default=15, help="分析する最大ファイル数")
    analyze_parser.set_defaults(handler_name="cmd_analyze")

    proposals_parser = subparsers.add_parser("proposals", help="未対応の改善提案を一覧表示")
    proposals_parser.add_argument("--org-name", required=True, help="対象 Organization 名")
    proposals_parser.set_defaults(handler_name="cmd_proposals")

    proposal_parser = subparsers.add_parser("proposal", help="改善提案の詳細・却下・適用")
    proposal_sub = proposal_parser.add_subparsers(dest="proposal_command", required=True)

    proposal_show = proposal_sub.add_parser("show", help="改善提案の詳細を表示")
    proposal_show.add_argument("proposal_id", help="提案 ID（先頭一致可）")
    proposal_show.add_argument("--org-name", required=True, help="対象 Organization 名")
    proposal_show.set_defaults(handler_name="cmd_proposal_show")

    proposal_reject = proposal_sub.add_parser("reject", help="改善提案を却下")
    proposal_reject.add_argument("proposal_id", help="提案 ID（先頭一致可）")
    proposal_reject.add_argument("--org-name", required=True, help="対象 Organization 名")
    proposal_reject.add_argument("--yes", action="store_true", help="確認を省略して却下する")
    proposal_reject.set_defaults(handler_name="cmd_proposal_reject")

    proposal_apply = proposal_sub.add_parser("apply", help="改善提案を適用")
    proposal_apply.add_argument("proposal_id", help="提案 ID（先頭一致可）")
    proposal_apply.add_argument("--org-name", required=True, help="対象 Organization 名")
    proposal_apply.add_argument(
        "--github-repo", default=None, help="GitHub リポジトリ (owner/repo)"
    )
    proposal_apply.add_argument("--github-token", default=None, help="GitHub トークン")
    proposal_apply.add_argument("--yes", action="store_true", help="確認を省略して適用する")
    proposal_apply.set_defaults(handler_name="cmd_proposal_apply")

    approve_parser = subparsers.add_parser("approve", help="改善提案を承認してコードに適用")
    approve_parser.add_argument("proposal_id", help="承認する提案の ID（先頭 8 文字以上）")
    approve_parser.add_argument("--org-name", required=True, help="対象 Organization 名")
    approve_parser.add_argument(
        "--github-repo", default=None, help="GitHub リポジトリ (owner/repo)"
    )
    approve_parser.add_argument("--github-token", default=None, help="GitHub トークン")
    approve_parser.add_argument("--yes", action="store_true", help="確認を省略して適用する")
    approve_parser.set_defaults(handler_name="cmd_approve")

    query_parser = subparsers.add_parser(
        "query", help="改善提案を検索（--org-name で正準 JSON / 省略時は SQLite ミラー）"
    )
    query_parser.add_argument(
        "--filter", default="", help="安全な filter 条件 (例: priority=high,status=proposed)"
    )
    query_parser.add_argument("--limit", type=int, default=50, help="最大件数")
    query_parser.add_argument(
        "--org-name", default=None, help="対象 Organization（指定時は正準 JSON ストアを読む）"
    )
    query_parser.add_argument("--db-path", default=None, help="対象 SQLite DB パス（ミラー）")
    query_parser.set_defaults(handler_name="cmd_query")
