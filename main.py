"""
RepoCorp AI CLI

使用例:
  repocorp init                                       # グローバルプラットフォーム初期化
  repocorp org add --name "MyApp" --repo /path/to/app # 子会社を登録
  repocorp org list                                   # 子会社一覧
  repocorp analyze --org-name "MyApp"                 # 分析して改善提案を生成
  repocorp proposals --org-name "MyApp"               # 提案一覧
  repocorp approve <id> --org-name "MyApp"            # 提案を承認・適用
  repocorp platform status                            # 全子会社横断ダッシュボード
  repocorp platform run-all                           # 全 Org の改善サイクルを実行
  repocorp serve                                      # Web GUI 起動（http://localhost:7860）
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
from pathlib import Path

from commands import build_parser
from commands.chat import cmd_chat as _cmd_chat_impl
from commands.goal import cmd_goal_run as _cmd_goal_run_impl
from commands.goal import cmd_goal_status as _cmd_goal_status_impl
from commands.doctor import cmd_doctor as _cmd_doctor_impl
from commands.orchestration import cmd_agent_status as _cmd_agent_status_impl
from commands.orchestration import cmd_agent_list as _cmd_agent_list_impl
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
from commands.org import cmd_analyze as _cmd_analyze_impl
from commands.org import cmd_approve as _cmd_approve_impl
from commands.org import cmd_init as _cmd_init_impl
from commands.org import cmd_org_add as _cmd_org_add_impl
from commands.org import cmd_org_list as _cmd_org_list_impl
from commands.org import cmd_org_show as _cmd_org_show_impl
from commands.org import cmd_org_remove as _cmd_org_remove_impl
from commands.org import cmd_proposal_apply as _cmd_proposal_apply_impl
from commands.org import cmd_proposal_reject as _cmd_proposal_reject_impl
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
from commands.platform import cmd_platform_run_all as _cmd_platform_run_all_impl
from commands.platform import cmd_platform_status as _cmd_platform_status_impl
from commands.platform import cmd_platform_restore as _cmd_platform_restore_impl
from commands.platform import cmd_serve as _cmd_serve_impl
from commands.version import cmd_version as _cmd_version_impl
from core.platform.state import PlatformStateManager

PROJECT_ROOT = Path(__file__).resolve().parent


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
    if isinstance(org_bucket, dict) and all(isinstance(value, dict) for value in org_bucket.values()):
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


SETTINGS_FILE = Path.home() / ".repocorp" / "gui_settings.json"
_PROVIDER_KEY_MAPPING = {
    "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "groq": ("groq_api_key", "GROQ_API_KEY"),
    "github_models": ("github_models_api_key", "GITHUB_TOKEN"),
    "gemini": ("gemini_api_key", "GOOGLE_API_KEY"),
}
_SAFE_QUERY_FILTER_FIELDS = {"id", "priority", "category", "title", "file_path", "status"}


def _load_gui_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_llm_provider() -> str:
    settings = _load_gui_settings()
    provider = os.getenv("REPOCORP_DEFAULT_LLM_PROVIDER") or settings.get("llm_provider", "anthropic")
    return provider if provider in _PROVIDER_KEY_MAPPING else "anthropic"


def _require_api_key(command_name: str) -> None:
    provider = _resolve_llm_provider()
    settings_key, env_var = _PROVIDER_KEY_MAPPING[provider]
    settings = _load_gui_settings()
    configured_key = os.getenv(env_var) or settings.get(settings_key, "")
    if configured_key:
        return

    print(f"[ERROR] {command_name} の実行には {env_var} が必要です。")
    print(f"   現在の LLM プロバイダー: {provider}")
    print("   対応方法:")
    print(f"   1. export {env_var}=your-api-key")
    print("   2. または repocorp serve で GUI を開き、Settings から API キーを保存")
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
        raise ValueError("--filter には SQL 構文を含められません。key=value[,key=value] 形式を使ってください。")

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


async def cmd_org_list(args) -> None:
    await _cmd_org_list_impl(args, get_psm=_get_psm)


async def cmd_org_show(args) -> None:
    await _cmd_org_show_impl(args, get_psm=_get_psm)


async def cmd_org_remove(args) -> None:
    await _cmd_org_remove_impl(args, confirm_action=_confirm_action, get_psm=_get_psm)


async def cmd_analyze(args) -> None:
    await _cmd_analyze_impl(args, get_orchestrator=_get_orchestrator, get_psm=_get_psm)


async def cmd_proposals(args) -> None:
    await _cmd_proposals_impl(args, get_psm=_get_psm)


async def cmd_proposal_show(args) -> None:
    await _cmd_proposal_show_impl(args, get_psm=_get_psm)


async def cmd_proposal_reject(args) -> None:
    await _cmd_proposal_reject_impl(args, confirm_action=_confirm_action, get_psm=_get_psm)


async def cmd_proposal_apply(args) -> None:
    await _cmd_proposal_apply_impl(
        args,
        confirm_action=_confirm_action,
        get_orchestrator=_get_orchestrator,
        get_psm=_get_psm,
        require_api_key=_require_api_key,
    )


async def cmd_query(args) -> None:
    await _cmd_query_impl(args, get_platform_home=_get_platform_home, parse_query_filters=_parse_query_filters)


async def cmd_approve(args) -> None:
    await _cmd_approve_impl(
        args,
        confirm_action=_confirm_action,
        get_orchestrator=_get_orchestrator,
        get_psm=_get_psm,
        require_api_key=_require_api_key,
    )


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


async def cmd_daemon_start(args) -> None:
    await _cmd_daemon_start_impl(args, get_platform_home=_get_platform_home, project_root=PROJECT_ROOT)


def cmd_daemon_stop(args) -> None:
    _cmd_daemon_stop_impl(args, get_platform_home=_get_platform_home)


def cmd_daemon_status(args) -> None:
    _cmd_daemon_status_impl(args, get_platform_home=_get_platform_home)


def cmd_chat(args) -> None:
    _cmd_chat_impl(args, require_api_key=_require_api_key)


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


async def cmd_goal_status(args) -> None:
    await _cmd_goal_status_impl(args, get_platform_home=_get_platform_home)


async def cmd_goal_run(args) -> None:
    await _cmd_goal_run_impl(args, require_api_key=_require_api_key)


async def cmd_doctor(args) -> None:
    await _cmd_doctor_impl(args)


async def cmd_version(args) -> None:
    await _cmd_version_impl(args)


HANDLERS = {
    "cmd_init": cmd_init,
    "cmd_org_add": cmd_org_add,
    "cmd_org_list": cmd_org_list,
    "cmd_org_show": cmd_org_show,
    "cmd_org_remove": cmd_org_remove,
    "cmd_analyze": cmd_analyze,
    "cmd_proposals": cmd_proposals,
    "cmd_proposal_show": cmd_proposal_show,
    "cmd_proposal_reject": cmd_proposal_reject,
    "cmd_proposal_apply": cmd_proposal_apply,
    "cmd_query": cmd_query,
    "cmd_approve": cmd_approve,
    "cmd_platform_status": cmd_platform_status,
    "cmd_platform_config": cmd_platform_config,
    "cmd_platform_config_set": cmd_platform_config_set,
    "cmd_platform_logs": cmd_platform_logs,
    "cmd_platform_backup": cmd_platform_backup,
    "cmd_platform_restore": cmd_platform_restore,
    "cmd_platform_run_all": cmd_platform_run_all,
    "cmd_serve": cmd_serve,
    "cmd_daemon_start": cmd_daemon_start,
    "cmd_daemon_stop": cmd_daemon_stop,
    "cmd_daemon_status": cmd_daemon_status,
    "cmd_chat": cmd_chat,
    "cmd_version": cmd_version,
    "cmd_doctor": cmd_doctor,
    "cmd_orchestration_analyze": cmd_orchestration_analyze,
    "cmd_orchestration_history": cmd_orchestration_history,
    "cmd_orchestration_capabilities": cmd_orchestration_capabilities,
    "cmd_orchestration_self_review": cmd_orchestration_self_review,
    "cmd_agent_status": cmd_agent_status,
    "cmd_agent_list": cmd_agent_list,
    "cmd_goal_status": cmd_goal_status,
    "cmd_goal_run": cmd_goal_run,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    handler_name = getattr(args, "handler_name", "")
    handler = HANDLERS.get(handler_name)
    if handler is None:
        parser.error(f"No handler registered for {handler_name or args.command}")
    result = handler(args)
    if inspect.isawaitable(result):
        asyncio.run(result)


if __name__ == "__main__":
    main()
