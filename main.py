"""
Pantheon CLI

使用例:
  pantheon init                                       # グローバルプラットフォーム初期化
  pantheon org add --name "MyApp" --repo /path/to/app # 子会社を登録
  pantheon org list                                   # 子会社一覧
  pantheon analyze --org-name "MyApp"                 # 分析して改善提案を生成
  pantheon proposals --org-name "MyApp"               # 提案一覧
  pantheon approve <id> --org-name "MyApp"            # 提案を承認・適用
  pantheon platform status                            # 全子会社横断ダッシュボード
  pantheon platform run-all                           # 全 Org の改善サイクルを実行
  pantheon serve                                      # Web GUI 起動（http://localhost:7860）
"""

from __future__ import annotations

import asyncio
import inspect
import sys

from commands import build_parser
from commands.atlas import cmd_atlas as _cmd_atlas_impl
from commands.business import cmd_business_archive as _cmd_business_archive_impl
from commands.business import cmd_business_compose as _cmd_business_compose_impl
from commands.business import cmd_business_create as _cmd_business_create_impl
from commands.business import cmd_business_delete as _cmd_business_delete_impl
from commands.business import cmd_business_from_proposal as _cmd_business_from_proposal_impl
from commands.business import cmd_business_list as _cmd_business_list_impl
from commands.business import cmd_business_outcomes as _cmd_business_outcomes_impl
from commands.business import cmd_business_pause as _cmd_business_pause_impl
from commands.business import cmd_business_show as _cmd_business_show_impl
from commands.business import cmd_business_update as _cmd_business_update_impl
from commands.chat import cmd_chat as _cmd_chat_impl
from commands.doctor import cmd_doctor as _cmd_doctor_impl
from commands.eval import cmd_eval as _cmd_eval_impl
from commands.goal import cmd_goal_plan as _cmd_goal_plan_impl
from commands.goal import cmd_goal_run as _cmd_goal_run_impl
from commands.goal import cmd_goal_status as _cmd_goal_status_impl
from commands.handoff import cmd_handoff as _cmd_handoff_impl
from commands.hq import cmd_hq_apply as _cmd_hq_apply_impl
from commands.hq import cmd_hq_diagnose as _cmd_hq_diagnose_impl
from commands.hq import cmd_hq_outcomes as _cmd_hq_outcomes_impl
from commands.hq import cmd_hq_propose as _cmd_hq_propose_impl
from commands.memory import cmd_memory_capture as _cmd_memory_capture_impl
from commands.memory import cmd_memory_list as _cmd_memory_list_impl
from commands.memory import cmd_memory_propagate as _cmd_memory_propagate_impl
from commands.orchestration import cmd_agent_list as _cmd_agent_list_impl
from commands.orchestration import cmd_agent_status as _cmd_agent_status_impl
from commands.orchestration import (
    cmd_orchestration_analyze as _cmd_orchestration_analyze_impl,
)
from commands.orchestration import (
    cmd_orchestration_capabilities as _cmd_orchestration_capabilities_impl,
)
from commands.orchestration import cmd_orchestration_history as _cmd_orchestration_history_impl
from commands.orchestration import (
    cmd_orchestration_self_review as _cmd_orchestration_self_review_impl,
)
from commands.orchestration import cmd_skills_list as _cmd_skills_list_impl
from commands.org import cmd_analyze as _cmd_analyze_impl
from commands.org import cmd_approve as _cmd_approve_impl
from commands.org import cmd_init as _cmd_init_impl
from commands.org import cmd_org_add as _cmd_org_add_impl
from commands.org import cmd_org_list as _cmd_org_list_impl
from commands.org import cmd_org_migrate_workspace as _cmd_org_migrate_workspace_impl
from commands.org import cmd_org_remove as _cmd_org_remove_impl
from commands.org import cmd_org_scan as _cmd_org_scan_impl
from commands.org import cmd_org_show as _cmd_org_show_impl
from commands.org import cmd_proposal_apply as _cmd_proposal_apply_impl
from commands.org import cmd_proposal_reject as _cmd_proposal_reject_impl
from commands.org import cmd_proposal_rollback as _cmd_proposal_rollback_impl
from commands.org import cmd_proposal_show as _cmd_proposal_show_impl
from commands.org import cmd_proposals as _cmd_proposals_impl
from commands.org import cmd_query as _cmd_query_impl
from commands.platform import cmd_daemon_start as _cmd_daemon_start_impl
from commands.platform import cmd_daemon_status as _cmd_daemon_status_impl
from commands.platform import cmd_daemon_stop as _cmd_daemon_stop_impl
from commands.platform import cmd_platform_backup as _cmd_platform_backup_impl
from commands.platform import cmd_platform_config as _cmd_platform_config_impl
from commands.platform import cmd_platform_config_set as _cmd_platform_config_set_impl
from commands.platform import cmd_platform_logs as _cmd_platform_logs_impl
from commands.platform import cmd_platform_restore as _cmd_platform_restore_impl
from commands.platform import cmd_platform_run_all as _cmd_platform_run_all_impl
from commands.platform import cmd_platform_status as _cmd_platform_status_impl
from commands.platform import cmd_serve as _cmd_serve_impl
from commands.plugin import cmd_plugin_add_division as _cmd_plugin_add_division_impl
from commands.plugin import cmd_plugin_install_company as _cmd_plugin_install_company_impl
from commands.plugin import cmd_plugin_list as _cmd_plugin_list_impl
from commands.plugin import cmd_plugin_scaffold_company as _cmd_plugin_scaffold_company_impl
from commands.plugin import cmd_plugin_scaffold_division as _cmd_plugin_scaffold_division_impl
from commands.portfolio import cmd_portfolio_overview as _cmd_portfolio_overview_impl
from commands.story import cmd_story_brief as _cmd_story_brief_impl
from commands.story import cmd_story_characters as _cmd_story_characters_impl
from commands.story import cmd_story_insights as _cmd_story_insights_impl
from commands.story import cmd_story_produce as _cmd_story_produce_impl
from commands.story import cmd_story_publish as _cmd_story_publish_impl
from commands.story import cmd_story_render as _cmd_story_render_impl
from commands.story import cmd_story_schedule as _cmd_story_schedule_impl
from commands.story import cmd_story_thumbnail as _cmd_story_thumbnail_impl
from commands.traces import cmd_traces as _cmd_traces_impl
from commands.up import cmd_up as _cmd_up_impl
from commands.version import cmd_version as _cmd_version_impl
from core.paths import resource_root
from core.platform.state import PlatformStateManager

# Windows のコンソール/リダイレクト先は既定が cp932 で、em-dash 等の非 cp932 文字を
# print すると UnicodeEncodeError でクラッシュする（CLI コマンドの実害。例: daemons
# watchdog install の print(err)）。標準出力を UTF-8 に張り替え、エンコード不能文字は
# 置換して決して落ちないようにする（best-effort。端末が無い/再設定不可なら無視）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

PROJECT_ROOT = resource_root()


def _get_platform_home():
    from core.platform.state import get_platform_home as resolve_platform_home

    return resolve_platform_home()


def _get_psm() -> PlatformStateManager:
    return PlatformStateManager()


def _get_orchestrator():
    """
    OrchestratorAgent を返す。
    CLI はすべてのタスクをこのエージェント経由で実行する。
    OrchestratorAgent が PreTaskOrchestrator で分析し、最適な専門エージェントに委任する。
    """
    from agents.orchestrator_agent import OrchestratorAgent

    return OrchestratorAgent.create()


def _filter_proficiency_data_by_org(data: dict, org_name: str) -> dict:
    org_bucket = data.get(org_name)
    if isinstance(org_bucket, dict) and all(
        isinstance(value, dict) for value in org_bucket.values()
    ):
        return org_bucket

    org_name_cf = org_name.casefold()
    prefixes = (
        f"{org_name_cf}:",
        f"{org_name_cf}/",
        f"{org_name_cf}|",
        f"{org_name_cf}::",
    )
    filtered = {}
    org_aware = False

    for agent_id, skills in data.items():
        if not isinstance(skills, dict):
            continue

        record_org_names = {
            str(value).casefold()
            for record in skills.values()
            if isinstance(record, dict)
            for value in [record.get("org_name") or record.get("organization_name")]
            if value
        }
        normalized_agent_id = str(agent_id).casefold()
        if record_org_names or any(token in normalized_agent_id for token in (":", "/", "|")):
            org_aware = True
        if normalized_agent_id.startswith(prefixes) or org_name_cf in record_org_names:
            filtered[agent_id] = skills

    return filtered if org_aware else data


# 旧 SETTINGS_FILE / _PROVIDER_KEY_MAPPING / _resolve_llm_provider / _load_gui_settings
# （ホスト型プロバイダ選択・GUI 設定読込）は Claude Code CLI 専用化で dead code だったため削除
# （2026-06-14 リポジトリ衛生監査）。生成は claude CLI 経由のみ。
_SAFE_QUERY_FILTER_FIELDS = {"id", "priority", "category", "title", "file_path", "status"}


def _require_api_key(command_name: str) -> None:
    """Ensure the local ``claude`` CLI backend is usable.

    Pantheon uses **no hosted-LLM API keys** — all generation runs through the local
    ``claude`` CLI (``core.runtime.claude_code``). The historical name is kept because
    call sites pass this as ``require_api_key=``; it now checks the CLI, not an API key.
    """
    from core.runtime.claude_code import claude_available

    if claude_available():
        return

    print(f"[ERROR] {command_name} の実行には Claude Code CLI が必要です。")
    print("   Pantheon は API キーを使いません。ローカルの `claude` CLI を利用します。")
    print("   対応方法:")
    print("   1. `claude` をインストールし、一度 `claude` を実行してログインする")
    print("   2. または PANTHEON_CLAUDE_BIN で claude バイナリのパスを指定する")
    print("   3. GUI から確認する場合は pantheon serve を実行する")
    sys.exit(1)


def _confirm_action(prompt: str, *, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def _parse_query_filters(raw_filter: str) -> dict[str, str]:
    filter_text = (raw_filter or "").strip()
    if not filter_text:
        return {}
    if any(token in filter_text for token in (";", "--", "/*", "*/")):
        raise ValueError(
            "--filter には SQL 構文を含められません。key=value[,key=value] 形式を使ってください。"
        )

    filters: dict[str, str] = {}
    for clause in filter_text.split(","):
        item = clause.strip()
        if not item:
            raise ValueError("空の filter 条件は使えません。")
        if item.lower().startswith(("where ", "order ", "and ", "or ")):
            raise ValueError("--filter は key=value[,key=value] 形式のみ対応しています。")
        if item.count("=") != 1:
            raise ValueError("--filter は key=value[,key=value] 形式のみ対応しています。")

        field, value = (part.strip() for part in item.split("=", 1))
        field = field.lower()
        if field not in _SAFE_QUERY_FILTER_FIELDS:
            allowed = ", ".join(sorted(_SAFE_QUERY_FILTER_FIELDS))
            raise ValueError(f"未対応の filter 項目です: {field} (allowed: {allowed})")
        if not value:
            raise ValueError(f"filter 値が空です: {field}")
        if value.startswith(("'", '"')) or value.endswith(("'", '"')):
            raise ValueError("--filter の値に引用符は使えません。例: priority=high")
        if any(ch in value for ch in ("\x00", "\n", "\r")):
            raise ValueError(f"filter 値に不正な文字が含まれています: {field}")
        if field in filters:
            raise ValueError(f"filter 項目が重複しています: {field}")
        filters[field] = value
    return filters


async def cmd_init(args) -> None:
    await _cmd_init_impl(args, get_psm=_get_psm, get_platform_home=_get_platform_home)


async def cmd_org_add(args) -> None:
    await _cmd_org_add_impl(args, get_psm=_get_psm, project_root=PROJECT_ROOT)


async def cmd_org_create(args) -> None:
    from commands.org import cmd_org_create as _impl

    await _impl(args, get_psm=_get_psm, project_root=PROJECT_ROOT)


async def cmd_business_create(args) -> None:
    await _cmd_business_create_impl(args, get_psm=_get_psm)


async def cmd_business_list(args) -> None:
    await _cmd_business_list_impl(args, get_psm=_get_psm)


async def cmd_business_show(args) -> None:
    await _cmd_business_show_impl(args, get_psm=_get_psm)


async def cmd_business_outcomes(args) -> None:
    await _cmd_business_outcomes_impl(args, get_psm=_get_psm)


async def cmd_business_compose(args) -> None:
    await _cmd_business_compose_impl(args, get_psm=_get_psm)


async def cmd_business_update(args) -> None:
    await _cmd_business_update_impl(args, get_psm=_get_psm)


async def cmd_business_pause(args) -> None:
    await _cmd_business_pause_impl(args, get_psm=_get_psm)


async def cmd_business_archive(args) -> None:
    await _cmd_business_archive_impl(args, get_psm=_get_psm)


async def cmd_business_delete(args) -> None:
    await _cmd_business_delete_impl(args, get_psm=_get_psm)


async def cmd_business_from_proposal(args) -> None:
    await _cmd_business_from_proposal_impl(args, get_psm=_get_psm)


async def cmd_plugin_list(args) -> None:
    await _cmd_plugin_list_impl(args, get_psm=_get_psm)


async def cmd_plugin_add_division(args) -> None:
    await _cmd_plugin_add_division_impl(args, get_psm=_get_psm)


async def cmd_plugin_scaffold_division(args) -> None:
    await _cmd_plugin_scaffold_division_impl(args, get_psm=_get_psm)


async def cmd_plugin_scaffold_company(args) -> None:
    await _cmd_plugin_scaffold_company_impl(args, get_psm=_get_psm)


async def cmd_portfolio_overview(args) -> None:
    await _cmd_portfolio_overview_impl(args, get_psm=_get_psm)


async def cmd_story_brief(args) -> None:
    await _cmd_story_brief_impl(args, get_psm=_get_psm)


async def cmd_story_render(args) -> None:
    await _cmd_story_render_impl(args, get_psm=_get_psm)


async def cmd_story_publish(args) -> None:
    await _cmd_story_publish_impl(args, get_psm=_get_psm)


async def cmd_story_produce(args) -> None:
    await _cmd_story_produce_impl(args, get_psm=_get_psm)


async def cmd_story_thumbnail(args) -> None:
    await _cmd_story_thumbnail_impl(args, get_psm=_get_psm)


async def cmd_story_characters(args) -> None:
    await _cmd_story_characters_impl(args, get_psm=_get_psm)


async def cmd_story_insights(args) -> None:
    await _cmd_story_insights_impl(args, get_psm=_get_psm)


async def cmd_story_schedule(args) -> None:
    await _cmd_story_schedule_impl(args, get_psm=_get_psm)


async def cmd_plugin_install_company(args) -> None:
    await _cmd_plugin_install_company_impl(args, get_psm=_get_psm)


async def cmd_org_list(args) -> None:
    await _cmd_org_list_impl(args, get_psm=_get_psm)


async def cmd_org_scan(args) -> None:
    await _cmd_org_scan_impl(args, get_psm=_get_psm)


async def cmd_org_show(args) -> None:
    await _cmd_org_show_impl(args, get_psm=_get_psm)


async def cmd_org_remove(args) -> None:
    await _cmd_org_remove_impl(args, confirm_action=_confirm_action, get_psm=_get_psm)


async def cmd_org_migrate_workspace(args) -> None:
    await _cmd_org_migrate_workspace_impl(args, get_psm=_get_psm)


async def cmd_analyze(args) -> None:
    await _cmd_analyze_impl(args, get_orchestrator=_get_orchestrator, get_psm=_get_psm)


async def cmd_proposals(args) -> None:
    await _cmd_proposals_impl(args, get_psm=_get_psm)


async def cmd_proposal_show(args) -> None:
    await _cmd_proposal_show_impl(args, get_psm=_get_psm)


async def cmd_proposal_reject(args) -> None:
    await _cmd_proposal_reject_impl(args, confirm_action=_confirm_action, get_psm=_get_psm)


async def cmd_proposal_rollback(args) -> None:
    await _cmd_proposal_rollback_impl(args, confirm_action=_confirm_action)


async def cmd_proposal_apply(args) -> None:
    await _cmd_proposal_apply_impl(
        args,
        confirm_action=_confirm_action,
        get_orchestrator=_get_orchestrator,
        get_psm=_get_psm,
        require_api_key=_require_api_key,
    )


async def cmd_query(args) -> None:
    await _cmd_query_impl(
        args,
        get_platform_home=_get_platform_home,
        parse_query_filters=_parse_query_filters,
        get_psm=_get_psm,
    )


async def cmd_approve(args) -> None:
    await _cmd_approve_impl(
        args,
        confirm_action=_confirm_action,
        get_orchestrator=_get_orchestrator,
        get_psm=_get_psm,
        require_api_key=_require_api_key,
    )


async def cmd_hq_diagnose(args) -> None:
    await _cmd_hq_diagnose_impl(args, get_psm=_get_psm)


async def cmd_hq_propose(args) -> None:
    await _cmd_hq_propose_impl(args, get_psm=_get_psm)


async def cmd_hq_apply(args) -> None:
    await _cmd_hq_apply_impl(
        args,
        confirm_action=_confirm_action,
        get_psm=_get_psm,
        require_api_key=_require_api_key,
    )


async def cmd_hq_outcomes(args) -> None:
    await _cmd_hq_outcomes_impl(args, get_psm=_get_psm)


async def cmd_handoff(args) -> None:
    await _cmd_handoff_impl(args, get_psm=_get_psm)


async def cmd_platform_status(args) -> None:
    await _cmd_platform_status_impl(args, get_psm=_get_psm)


async def cmd_platform_config(args) -> None:
    await _cmd_platform_config_impl(args, get_psm=_get_psm)


async def cmd_platform_config_set(args) -> None:
    await _cmd_platform_config_set_impl(args, get_psm=_get_psm)


async def cmd_platform_logs(args) -> None:
    await _cmd_platform_logs_impl(args, get_psm=_get_psm)


async def cmd_platform_backup(args) -> None:
    await _cmd_platform_backup_impl(args, get_psm=_get_psm)


async def cmd_platform_restore(args) -> None:
    await _cmd_platform_restore_impl(args, get_psm=_get_psm)


async def cmd_platform_run_all(args) -> None:
    await _cmd_platform_run_all_impl(args, get_psm=_get_psm)


def cmd_serve(args) -> None:
    _cmd_serve_impl(args)


def cmd_up(args) -> None:
    _cmd_up_impl(args)


async def cmd_daemon_start(args) -> None:
    await _cmd_daemon_start_impl(
        args, get_platform_home=_get_platform_home, project_root=PROJECT_ROOT
    )


def cmd_daemon_stop(args) -> None:
    _cmd_daemon_stop_impl(args, get_platform_home=_get_platform_home)


def cmd_daemon_status(args) -> None:
    _cmd_daemon_status_impl(args, get_platform_home=_get_platform_home)


def cmd_chat(args) -> None:
    _cmd_chat_impl(args, require_api_key=_require_api_key)


def cmd_atlas(args) -> None:
    _cmd_atlas_impl(args)


def cmd_traces(args) -> None:
    _cmd_traces_impl(args)


def cmd_eval(args) -> None:
    _cmd_eval_impl(args)


def cmd_memory_propagate(args) -> None:
    _cmd_memory_propagate_impl(args)


def cmd_memory_list(args) -> None:
    _cmd_memory_list_impl(args)


def cmd_memory_capture(args) -> None:
    _cmd_memory_capture_impl(args)


async def cmd_orchestration_analyze(args) -> None:
    await _cmd_orchestration_analyze_impl(args, get_orchestrator=_get_orchestrator)


async def cmd_orchestration_history(args) -> None:
    await _cmd_orchestration_history_impl(args)


async def cmd_orchestration_capabilities(args) -> None:
    await _cmd_orchestration_capabilities_impl(args)


async def cmd_orchestration_self_review(args) -> None:
    await _cmd_orchestration_self_review_impl(args)


async def cmd_agent_status(args) -> None:
    await _cmd_agent_status_impl(
        args,
        filter_proficiency_data_by_org=_filter_proficiency_data_by_org,
        get_platform_home=_get_platform_home,
    )


async def cmd_agent_list(args) -> None:
    await _cmd_agent_list_impl(args, get_psm=_get_psm)


async def cmd_skills_list(args) -> None:
    await _cmd_skills_list_impl(args, get_psm=_get_psm)


async def cmd_goal_status(args) -> None:
    await _cmd_goal_status_impl(args, get_platform_home=_get_platform_home)


async def cmd_goal_run(args) -> None:
    await _cmd_goal_run_impl(args, require_api_key=_require_api_key)


async def cmd_goal_plan(args) -> None:
    await _cmd_goal_plan_impl(args, get_platform_home=_get_platform_home)


async def cmd_doctor(args) -> None:
    await _cmd_doctor_impl(args)


async def cmd_version(args) -> None:
    await _cmd_version_impl(args)


async def cmd_session_start(args) -> None:
    from commands.session import cmd_session_start as _impl

    await _impl(args)


async def cmd_session_list(args) -> None:
    from commands.session import cmd_session_list as _impl

    await _impl(args)


async def cmd_session_show(args) -> None:
    from commands.session import cmd_session_show as _impl

    await _impl(args)


async def cmd_session_stop(args) -> None:
    from commands.session import cmd_session_stop as _impl

    await _impl(args)


async def cmd_session_resume(args) -> None:
    from commands.session import cmd_session_resume as _impl

    await _impl(args)


async def cmd_session_doctor(args) -> None:
    from commands.session import cmd_session_doctor as _impl

    await _impl(args)


async def cmd_tasks_add(args) -> None:
    from commands.tasks import cmd_tasks_add as _impl

    await _impl(args)


async def cmd_tasks_list(args) -> None:
    from commands.tasks import cmd_tasks_list as _impl

    await _impl(args)


async def cmd_tasks_drain(args) -> None:
    from commands.tasks import cmd_tasks_drain as _impl

    await _impl(args)


async def cmd_tasks_get(args) -> None:
    from commands.tasks import cmd_tasks_get as _impl

    await _impl(args)


async def cmd_tasks_cancel(args) -> None:
    from commands.tasks import cmd_tasks_cancel as _impl

    await _impl(args)


async def cmd_daemons_status(args) -> None:
    from commands.daemons import cmd_daemons_status as _impl

    await _impl(args)


async def cmd_daemons_start(args) -> None:
    from commands.daemons import cmd_daemons_start as _impl

    await _impl(args)


async def cmd_daemons_stop(args) -> None:
    from commands.daemons import cmd_daemons_stop as _impl

    await _impl(args)


async def cmd_daemons_enable(args) -> None:
    from commands.daemons import cmd_daemons_enable as _impl

    await _impl(args)


async def cmd_daemons_disable(args) -> None:
    from commands.daemons import cmd_daemons_disable as _impl

    await _impl(args)


async def cmd_daemons_watchdog_install(args) -> None:
    from commands.daemons import cmd_daemons_watchdog_install as _impl

    await _impl(args)


async def cmd_daemons_watchdog_uninstall(args) -> None:
    from commands.daemons import cmd_daemons_watchdog_uninstall as _impl

    await _impl(args)


async def cmd_daemons_watchdog_status(args) -> None:
    from commands.daemons import cmd_daemons_watchdog_status as _impl

    await _impl(args)


async def cmd_trends_collect(args) -> None:
    from commands.trends import cmd_trends_collect as _impl

    await _impl(args)


async def cmd_trends_list(args) -> None:
    from commands.trends import cmd_trends_list as _impl

    await _impl(args)


async def cmd_trends_business_scan(args) -> None:
    from commands.trends import cmd_trends_business_scan as _impl

    await _impl(args)


async def cmd_trends_untapped(args) -> None:
    from commands.trends import cmd_trends_untapped as _impl

    await _impl(args)


async def cmd_trends_business_proposals(args) -> None:
    from commands.trends import cmd_trends_business_proposals as _impl

    await _impl(args)


async def cmd_revenue_collect(args) -> None:
    from commands.revenue import cmd_revenue_collect as _impl

    await _impl(args)


async def cmd_revenue_report(args) -> None:
    from commands.revenue import cmd_revenue_report as _impl

    await _impl(args)


async def cmd_revenue_intelligence(args) -> None:
    from commands.revenue import cmd_revenue_intelligence as _impl

    await _impl(args)


async def cmd_revenue_projection(args) -> None:
    from commands.revenue import cmd_revenue_projection as _impl

    await _impl(args)


async def cmd_revenue_forecast(args) -> None:
    from commands.revenue import cmd_revenue_forecast as _impl

    await _impl(args)


async def cmd_revenue_attribution(args) -> None:
    from commands.revenue import cmd_revenue_attribution as _impl

    await _impl(args)


async def cmd_revenue_goal_status(args) -> None:
    from commands.revenue import cmd_revenue_goal_status as _impl

    await _impl(args)


async def cmd_revenue_integrity(args) -> None:
    from commands.revenue import cmd_revenue_integrity as _impl

    await _impl(args)


async def cmd_db_sync(args) -> None:
    from commands.db import cmd_db_sync as _impl

    await _impl(args)


async def cmd_db_stats(args) -> None:
    from commands.db import cmd_db_stats as _impl

    await _impl(args)


async def cmd_inbox_list(args) -> None:
    from commands.inbox import cmd_inbox_list as _impl

    await _impl(args)


async def cmd_content_list(args) -> None:
    from commands.content import cmd_content_list as _impl

    await _impl(args)


async def cmd_content_create(args) -> None:
    from commands.content import cmd_content_create as _impl

    await _impl(args)


async def cmd_content_run(args) -> None:
    from commands.content import cmd_content_run as _impl

    await _impl(args)


async def cmd_content_enable(args) -> None:
    from commands.content import cmd_content_enable as _impl

    await _impl(args)


async def cmd_content_disable(args) -> None:
    from commands.content import cmd_content_disable as _impl

    await _impl(args)


async def cmd_content_delete(args) -> None:
    from commands.content import cmd_content_delete as _impl

    await _impl(args)


async def cmd_publish_connect(args) -> None:
    from commands.publish import cmd_publish_connect as _impl

    await _impl(args)


async def cmd_publish_status(args) -> None:
    from commands.publish import cmd_publish_status as _impl

    await _impl(args)


async def cmd_publish_disconnect(args) -> None:
    from commands.publish import cmd_publish_disconnect as _impl

    await _impl(args)


async def cmd_publish_auto(args) -> None:
    from commands.publish import cmd_publish_auto as _impl

    await _impl(args)


async def cmd_publish_jobs_list(args) -> None:
    from commands.publish import cmd_publish_jobs_list as _impl

    await _impl(args)


async def cmd_publish_jobs_run(args) -> None:
    from commands.publish import cmd_publish_jobs_run as _impl

    await _impl(args)


async def cmd_publish_jobs_confirm(args) -> None:
    from commands.publish import cmd_publish_jobs_confirm as _impl

    await _impl(args)


async def cmd_publish_jobs_delete(args) -> None:
    from commands.publish import cmd_publish_jobs_delete as _impl

    await _impl(args)


HANDLERS = {
    "cmd_init": cmd_init,
    "cmd_org_add": cmd_org_add,
    "cmd_org_create": cmd_org_create,
    "cmd_business_create": cmd_business_create,
    "cmd_business_list": cmd_business_list,
    "cmd_business_show": cmd_business_show,
    "cmd_business_outcomes": cmd_business_outcomes,
    "cmd_business_compose": cmd_business_compose,
    "cmd_business_update": cmd_business_update,
    "cmd_business_pause": cmd_business_pause,
    "cmd_business_archive": cmd_business_archive,
    "cmd_business_delete": cmd_business_delete,
    "cmd_business_from_proposal": cmd_business_from_proposal,
    "cmd_plugin_list": cmd_plugin_list,
    "cmd_plugin_add_division": cmd_plugin_add_division,
    "cmd_plugin_scaffold_division": cmd_plugin_scaffold_division,
    "cmd_plugin_scaffold_company": cmd_plugin_scaffold_company,
    "cmd_portfolio_overview": cmd_portfolio_overview,
    "cmd_story_brief": cmd_story_brief,
    "cmd_story_render": cmd_story_render,
    "cmd_story_publish": cmd_story_publish,
    "cmd_story_produce": cmd_story_produce,
    "cmd_story_thumbnail": cmd_story_thumbnail,
    "cmd_story_characters": cmd_story_characters,
    "cmd_story_insights": cmd_story_insights,
    "cmd_story_schedule": cmd_story_schedule,
    "cmd_plugin_install_company": cmd_plugin_install_company,
    "cmd_org_list": cmd_org_list,
    "cmd_org_scan": cmd_org_scan,
    "cmd_org_show": cmd_org_show,
    "cmd_org_remove": cmd_org_remove,
    "cmd_org_migrate_workspace": cmd_org_migrate_workspace,
    "cmd_analyze": cmd_analyze,
    "cmd_proposals": cmd_proposals,
    "cmd_proposal_show": cmd_proposal_show,
    "cmd_proposal_reject": cmd_proposal_reject,
    "cmd_proposal_rollback": cmd_proposal_rollback,
    "cmd_proposal_apply": cmd_proposal_apply,
    "cmd_query": cmd_query,
    "cmd_approve": cmd_approve,
    "cmd_hq_diagnose": cmd_hq_diagnose,
    "cmd_hq_propose": cmd_hq_propose,
    "cmd_hq_apply": cmd_hq_apply,
    "cmd_hq_outcomes": cmd_hq_outcomes,
    "cmd_handoff": cmd_handoff,
    "cmd_platform_status": cmd_platform_status,
    "cmd_platform_config": cmd_platform_config,
    "cmd_platform_config_set": cmd_platform_config_set,
    "cmd_platform_logs": cmd_platform_logs,
    "cmd_platform_backup": cmd_platform_backup,
    "cmd_platform_restore": cmd_platform_restore,
    "cmd_platform_run_all": cmd_platform_run_all,
    "cmd_serve": cmd_serve,
    "cmd_up": cmd_up,
    "cmd_daemon_start": cmd_daemon_start,
    "cmd_daemon_stop": cmd_daemon_stop,
    "cmd_daemon_status": cmd_daemon_status,
    "cmd_chat": cmd_chat,
    "cmd_atlas": cmd_atlas,
    "cmd_traces": cmd_traces,
    "cmd_eval": cmd_eval,
    "cmd_memory_propagate": cmd_memory_propagate,
    "cmd_memory_list": cmd_memory_list,
    "cmd_memory_capture": cmd_memory_capture,
    "cmd_version": cmd_version,
    "cmd_doctor": cmd_doctor,
    "cmd_orchestration_analyze": cmd_orchestration_analyze,
    "cmd_orchestration_history": cmd_orchestration_history,
    "cmd_orchestration_capabilities": cmd_orchestration_capabilities,
    "cmd_orchestration_self_review": cmd_orchestration_self_review,
    "cmd_agent_status": cmd_agent_status,
    "cmd_agent_list": cmd_agent_list,
    "cmd_skills_list": cmd_skills_list,
    "cmd_goal_status": cmd_goal_status,
    "cmd_goal_run": cmd_goal_run,
    "cmd_goal_plan": cmd_goal_plan,
    "cmd_session_start": cmd_session_start,
    "cmd_session_list": cmd_session_list,
    "cmd_session_show": cmd_session_show,
    "cmd_session_stop": cmd_session_stop,
    "cmd_session_resume": cmd_session_resume,
    "cmd_session_doctor": cmd_session_doctor,
    "cmd_tasks_add": cmd_tasks_add,
    "cmd_tasks_list": cmd_tasks_list,
    "cmd_tasks_drain": cmd_tasks_drain,
    "cmd_tasks_get": cmd_tasks_get,
    "cmd_tasks_cancel": cmd_tasks_cancel,
    "cmd_daemons_status": cmd_daemons_status,
    "cmd_daemons_start": cmd_daemons_start,
    "cmd_daemons_stop": cmd_daemons_stop,
    "cmd_daemons_enable": cmd_daemons_enable,
    "cmd_daemons_disable": cmd_daemons_disable,
    "cmd_daemons_watchdog_install": cmd_daemons_watchdog_install,
    "cmd_daemons_watchdog_uninstall": cmd_daemons_watchdog_uninstall,
    "cmd_daemons_watchdog_status": cmd_daemons_watchdog_status,
    "cmd_trends_collect": cmd_trends_collect,
    "cmd_trends_list": cmd_trends_list,
    "cmd_trends_business_scan": cmd_trends_business_scan,
    "cmd_trends_untapped": cmd_trends_untapped,
    "cmd_trends_business_proposals": cmd_trends_business_proposals,
    "cmd_revenue_collect": cmd_revenue_collect,
    "cmd_revenue_report": cmd_revenue_report,
    "cmd_revenue_intelligence": cmd_revenue_intelligence,
    "cmd_revenue_projection": cmd_revenue_projection,
    "cmd_revenue_forecast": cmd_revenue_forecast,
    "cmd_revenue_attribution": cmd_revenue_attribution,
    "cmd_revenue_goal_status": cmd_revenue_goal_status,
    "cmd_revenue_integrity": cmd_revenue_integrity,
    "cmd_db_sync": cmd_db_sync,
    "cmd_db_stats": cmd_db_stats,
    "cmd_inbox_list": cmd_inbox_list,
    "cmd_content_list": cmd_content_list,
    "cmd_content_create": cmd_content_create,
    "cmd_content_run": cmd_content_run,
    "cmd_content_enable": cmd_content_enable,
    "cmd_content_disable": cmd_content_disable,
    "cmd_content_delete": cmd_content_delete,
    "cmd_publish_connect": cmd_publish_connect,
    "cmd_publish_status": cmd_publish_status,
    "cmd_publish_disconnect": cmd_publish_disconnect,
    "cmd_publish_auto": cmd_publish_auto,
    "cmd_publish_jobs_list": cmd_publish_jobs_list,
    "cmd_publish_jobs_run": cmd_publish_jobs_run,
    "cmd_publish_jobs_confirm": cmd_publish_jobs_confirm,
    "cmd_publish_jobs_delete": cmd_publish_jobs_delete,
}


def main() -> None:
    argv = sys.argv[1:]

    # exe 化（frozen）時のデーモン自己再起動エントリ。
    # `python -m core._daemon_runner` が使えないため、自分自身を
    # `Pantheon.exe --daemon-run --interval=.. --max-files=..` の形で再実行する
    # （commands/platform.py の cmd_daemon_start を参照）。
    if argv and argv[0] == "--daemon-run":
        from core import _daemon_runner

        sys.argv = [sys.argv[0], *argv[1:]]
        _daemon_runner.main()
        return

    # コンテンツ/PDCA デーモンの frozen 自己再起動エントリ。
    if argv and argv[0] == "--content-daemon-run":
        from core import _content_daemon_runner

        sys.argv = [sys.argv[0], *argv[1:]]
        _content_daemon_runner.main()
        return

    # watchdog（daemon 監視・自動復旧）の frozen 自己再起動エントリ。
    if argv and argv[0] == "--watchdog-run":
        from core import _watchdog_runner

        sys.argv = [sys.argv[0], *argv[1:]]
        _watchdog_runner.main()
        return

    # trend daemon（トレンド収集・変換）の frozen 自己再起動エントリ。
    if argv and argv[0] == "--trend-daemon-run":
        from core import _trend_daemon_runner

        sys.argv = [sys.argv[0], *argv[1:]]
        _trend_daemon_runner.main()
        return

    # revenue daemon（収益分析＋ポートフォリオ提案スキャン）の frozen 自己再起動エントリ。
    if argv and argv[0] == "--revenue-daemon-run":
        from core import _revenue_daemon_runner

        sys.argv = [sys.argv[0], *argv[1:]]
        _revenue_daemon_runner.main()
        return

    # task daemon（作業ボードの headless 自動実行）の frozen 自己再起動エントリ。
    if argv and argv[0] == "--task-daemon-run":
        from core import _task_daemon_runner

        sys.argv = [sys.argv[0], *argv[1:]]
        _task_daemon_runner.main()
        return

    # 引数なし起動（exe をダブルクリックした場合など）はフル起動（up）する:
    # Web GUI（監視）+ wmux 汎用チャットタブ + ブラウザ自動オープン。
    # ターミナルから `Pantheon.exe <command>` とすれば従来どおり CLI が使える。
    if not argv:
        argv = ["up"]

    parser = build_parser()
    args = parser.parse_args(argv)
    handler_name = getattr(args, "handler_name", "")
    handler = HANDLERS.get(handler_name)
    if handler is None:
        parser.error(f"No handler registered for {handler_name or args.command}")
    result = handler(args)
    if inspect.isawaitable(result):
        asyncio.run(result)


if __name__ == "__main__":
    main()
