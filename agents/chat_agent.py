"""
ChatAgent — RepoCorp AI 自然言語対話エージェント

ユーザーは自然言語で話しかけるだけ。
ChatAgent が意図を解析し、適切なツールを呼び出して作業を実行する。

インタラクションモデル:
  - GUI設定または環境変数でLLMが使えれば: 自然言語 → 適切なLLM / Pythonエージェント実行
  - APIキーなし: スラッシュコマンド（/help, /status, /goal "..."）

スラッシュコマンド一覧（APIキー不要）:
  /init              プラットフォームを初期化
  /org add           Organizationを追加
  /analyze <org>     リポジトリを分析
  /proposals <org>   改善提案一覧
  /approve <id>      提案を承認
  /goal <text>       抽象ゴールを実行
  /status            プラットフォーム状態
  /agents            登録エージェント一覧
  /help              ヘルプ表示
  /exit              終了
"""

from __future__ import annotations

import json
import logging
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path.home() / ".repocorp" / "gui_settings.json"
DEFAULT_MODEL = ""  # empty => let the `claude` CLI pick its own default model


def _load_llm_config() -> dict[str, Any]:
    """Resolve Pantheon's only execution backend: the local ``claude`` CLI.

    There are no API keys. The optional model preference comes from
    ``PANTHEON_DEFAULT_MODEL`` (or the GUI settings file, if present).
    """
    from core.runtime.claude_code import claude_available

    model = os.environ.get("PANTHEON_DEFAULT_MODEL", DEFAULT_MODEL)
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            model = settings.get("llm_model", model) or model
        except Exception:
            logger.warning("Failed to load GUI settings from %s", SETTINGS_FILE, exc_info=True)

    return {
        "provider": "claude_code",
        "model": model,
        "available": claude_available(),
    }


def _apply_llm_config_to_env(config: dict[str, Any]) -> None:
    """Reflect the optional model preference into the environment."""
    model = config.get("model") or ""
    if model:
        os.environ["PANTHEON_DEFAULT_MODEL"] = model


def _has_llm_config(config: dict[str, Any]) -> bool:
    return bool(config.get("available"))


def _missing_api_key_message(config: dict[str, Any]) -> str:
    return (
        "Claude Code が見つかりません。\n"
        "Pantheon は唯一の実行基盤として `claude` CLI を使います。\n"
        "`claude` をインストールしてログイン済みか確認してください（`claude --version`）。"
    )


def _build_llm_config(config: dict[str, Any]):
    from core.llm import LLMConfig

    return LLMConfig(default_model=config.get("model") or None)


def _parse_tool_input(raw_input: Any) -> Dict[str, Any]:
    if isinstance(raw_input, dict):
        return raw_input
    if isinstance(raw_input, str):
        try:
            parsed = json.loads(raw_input)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _classify_agent_task(user_message: str) -> Optional[str]:
    text = user_message.lower()
    keyword_map = {
        "code_review": [
            "code review",
            "review",
            "コードレビュー",
            "レビュー",
            "見て",
            "確認して",
            "診断して",
            "security",
            "audit",
            "脆弱",
            "セキュリティ",
            "監査",
        ],
        "codebase_exploration": ["analyze", "analysis", "分析", "調査", "explore", "理解して"],
    }
    for task_type, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            return task_type
    return None


async def _generate_llm_response(messages: List[Dict[str, Any]], config: dict[str, Any]) -> Dict[str, Any]:
    """Generate a conversational reply via Claude Code (the local ``claude`` CLI).

    Claude Code manages its own tools, so Pantheon no longer runs a manual
    tool-call loop here: we return the assistant text with an empty
    ``tool_calls`` list. Explicit platform operations remain available through
    slash commands and the orchestrator path in :func:`_handle_agent_task`.
    """
    from core.llm import LLMMessage, get_llm_provider

    provider = get_llm_provider()
    response = await provider.generate(
        messages=[LLMMessage(role=message["role"], content=message["content"]) for message in messages],
        model=config.get("model") or None,
    )
    return {"content": response.content, "tool_calls": []}


async def _handle_agent_task(user_message: str, config: dict[str, Any], current_org: Optional[str] = None) -> str:
    """自然言語タスクをバックエンドのPythonエージェントシステムで実行する。"""
    if not _has_llm_config(config):
        return _missing_api_key_message(config)

    task_type = _classify_agent_task(user_message)
    if task_type is None:
        return ""

    try:
        from agents.agent_factory import AgentFactory
        from agents.base import AgentTask
        from core.llm import get_llm_provider
        from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator
    except ImportError:
        return "エージェントシステムが利用できません。requirements.txt を確認してください。"

    _apply_llm_config_to_env(config)
    llm_provider = get_llm_provider()
    repo_path = Path.cwd()
    task_input = {
        "repo_path": str(repo_path),
        "user_message": user_message,
        "current_org": current_org,
    }
    if task_type == "code_review":
        task_input["max_files"] = 10

    task = AgentTask(task_type=task_type, description=user_message, input=task_input)
    agent_factory = AgentFactory(llm_client=llm_provider)
    orchestrator = PreTaskOrchestrator(llm_client=llm_provider, agent_factory=agent_factory)
    analysis = orchestrator.analyze(task_type, user_message, context=task_input)
    result = await orchestrator.execute(task, analysis, agent_factory=agent_factory.create)

    lines = [
        f"🧭 PreTaskOrchestrator: {task_type}",
        f"🪄 実行パターン: {analysis.recommended_pattern}",
        f"🤖 推奨エージェント: {', '.join(analysis.recommended_agent_ids) or 'なし'}",
    ]

    if not getattr(result, "success", False):
        lines.append(f"❌ 実行失敗: {getattr(result, 'error', 'unknown error')}")
        return "\n".join(lines)

    output = getattr(result, "output", {}) or {}
    if task_type == "code_review":
        suggestions = output.get("suggestions", [])
        files_reviewed = output.get("files_reviewed", 0)
        lines.append(f"✅ {files_reviewed} ファイルをレビューしました")
        for suggestion in suggestions[:5]:
            lines.append(
                f"- [{suggestion.get('priority', 'medium')}] {suggestion.get('title', '改善提案')}"
                + (f" ({suggestion.get('file_path')})" if suggestion.get('file_path') else "")
            )
        if len(suggestions) > 5:
            lines.append(f"- ...他 {len(suggestions) - 5} 件")
    elif output.get("change_summary"):
        lines.append(f"✅ {output['change_summary']}")
    elif output:
        lines.append("✅ 実行完了")
        lines.append(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    else:
        lines.append("✅ 実行完了")

    if getattr(result, "thinking_process", ""):
        lines.append(f"📝 {result.thinking_process}")
    return "\n".join(lines)


# ───────────────────────────────────────────────────── #
# ツール定義（Anthropic tool_use 形式）                  #
# ───────────────────────────────────────────────────── #

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "initialize_platform",
        "description": "RepoCorp AI プラットフォームを初期化する。初回セットアップ時に使用。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "add_organization",
        "description": "新しい Organization（プロジェクト）を登録する。リポジトリパスと目的を指定する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Organization の名前"},
                "repo": {"type": "string", "description": "担当リポジトリのパス（省略時はカレントディレクトリ）"},
                "purpose": {"type": "string", "description": "Organizationの目的・ゴール"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "analyze_organization",
        "description": "指定した Organization のリポジトリを分析して改善提案を生成する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "org_name": {"type": "string", "description": "分析対象の Organization 名"},
                "max_files": {"type": "integer", "description": "最大分析ファイル数（省略時: 10）"},
            },
            "required": ["org_name"],
        },
    },
    {
        "name": "list_proposals",
        "description": "未対応の改善提案一覧を表示する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "org_name": {"type": "string", "description": "対象 Organization 名"},
            },
            "required": ["org_name"],
        },
    },
    {
        "name": "approve_proposal",
        "description": "改善提案を承認してコードに適用する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string", "description": "承認する提案のID（先頭数文字でも可）"},
                "org_name": {"type": "string", "description": "対象 Organization 名"},
            },
            "required": ["proposal_id", "org_name"],
        },
    },
    {
        "name": "run_goal",
        "description": "抽象的なゴールを自然言語で指定して自律実行する。例: 'セキュリティを改善したい'",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_text": {"type": "string", "description": "実行したいゴールの自然言語テキスト"},
            },
            "required": ["goal_text"],
        },
    },
    {
        "name": "platform_status",
        "description": "全 Organization の状態とメトリクスを表示する。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_capabilities",
        "description": "登録されているエージェントとスキルの一覧を表示する。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_organizations",
        "description": "登録済みの Organization 一覧を表示する。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

SYSTEM_PROMPT = """\
あなたは RepoCorp AI プラットフォームの対話エージェントです。
ユーザーの自然言語の依頼を理解し、適切なツールを呼び出して作業を実行します。

利用可能なツールでできること:
- プラットフォームの初期化・Organization の追加・管理
- リポジトリの自動分析と改善提案の生成
- 改善提案の承認・適用
- 抽象ゴール（「ECサイトを作りたい」等）の自律実行
- システム状態の確認

ガイドライン:
1. ユーザーの意図を正確に把握してから最小限のツール呼び出しで目的を達成する
2. 不明点があれば実行前に確認する（Organization名、リポジトリパスなど）
3. 実行結果を日本語でわかりやすく説明する
4. エラーが起きたら原因と解決策を提示する
"""


# ───────────────────────────────────────────────────── #
# ツール実行（各ツールの実装）                            #
# ───────────────────────────────────────────────────── #

async def _tool_initialize_platform(_input: Dict) -> str:
    from core.bootstrap import bootstrap_platform
    from core.platform.state import PlatformStateManager, get_platform_home
    psm = PlatformStateManager()
    if psm.is_initialized():
        return f"✅ プラットフォームはすでに初期化されています（{psm.platform_home}）"
    bootstrap_platform()
    return f"✅ プラットフォームを初期化しました → {get_platform_home()}"


async def _tool_add_organization(inp: Dict) -> str:
    from uuid import uuid4

    from core.models.organization import Division, Organization, Team
    from core.platform.state import PlatformStateManager

    name = inp["name"]
    repo = inp.get("repo", str(Path.cwd()))
    purpose = inp.get("purpose", "")

    psm = PlatformStateManager()
    if not psm.is_initialized():
        return "❌ まず /init でプラットフォームを初期化してください"

    existing = psm.load_organization_by_name(name)
    if existing:
        return f"⚠️  Organization '{name}' はすでに登録されています"

    org = Organization(id=uuid4(), name=name, target_repo_path=repo, purpose=purpose)
    div = Division(id=uuid4(), name="Core", purpose="コア機能")
    team = Team(id=uuid4(), name="Alpha", purpose="メインチーム")
    div.teams.append(team)
    org.divisions.append(div)
    psm.save_organization(org)
    return f"✅ Organization '{name}' を登録しました（リポジトリ: {repo}）"


async def _tool_analyze_organization(inp: Dict) -> str:
    from uuid import uuid4

    from agents.base import AgentTask
    from agents.orchestrator_agent import OrchestratorAgent
    from core.models.organization import ImprovementProposal
    from core.platform.state import PlatformStateManager
    from core.state.manager import RepoStateManager

    org_name = inp["org_name"]
    max_files = inp.get("max_files", 10)

    psm = PlatformStateManager()
    org = psm.load_organization_by_name(org_name)
    if not org:
        orgs = psm.load_organizations()
        names = [o.name for o in orgs]
        return f"❌ Organization '{org_name}' が見つかりません。登録済み: {names}"

    repo_path = Path(org.target_repo_path) if org.target_repo_path else Path(".")
    sm = RepoStateManager(repo_path, org.name)
    agent = OrchestratorAgent.create()
    task = AgentTask(
        task_type="code_review",
        description=f"{org.name} のコードレビューと改善提案生成",
        input={"repo_path": str(repo_path), "max_files": max_files},
    )
    result = await agent.run(task)
    if not result.success:
        return f"❌ 分析失敗: {result.error}"

    suggestions = result.output.get("suggestions", [])
    files = result.output.get("files_reviewed", 0)
    for s in suggestions:
        proposal = ImprovementProposal(
            review_id=uuid4(),
            priority=s.get("priority", "medium"),
            category=s.get("category", "general"),
            title=s.get("title", "改善提案"),
            description=s.get("description", ""),
            file_path=s.get("file_path", ""),
            expected_impact=s.get("expected_impact", ""),
        )
        sm.save_improvement_proposal(proposal)

    return (
        f"✅ {files} ファイルを分析し、{len(suggestions)} 件の改善提案を生成しました\n"
        + "\n".join(
            f"  {'🔴' if s.get('priority')=='high' else '🟡' if s.get('priority')=='medium' else '🟢'}"
            f" [{s.get('priority','?').upper():6}] {s.get('title','')}"
            for s in suggestions[:5]
        )
        + (f"\n  ...他 {len(suggestions)-5} 件" if len(suggestions) > 5 else "")
    )


async def _tool_list_proposals(inp: Dict) -> str:
    from core.platform.state import PlatformStateManager

    org_name = inp["org_name"]
    psm = PlatformStateManager()
    org = psm.load_organization_by_name(org_name)
    if not org:
        return f"❌ Organization '{org_name}' が見つかりません"

    sm = psm.get_org_state_manager(org)
    proposals = sm.get_pending_improvement_proposals(limit=20)
    if not proposals:
        return f"✅ '{org_name}' に未対応の改善提案はありません"

    lines = [f"📋 '{org_name}' の未対応提案 ({len(proposals)} 件):\n"]
    for p in proposals:
        badge = "🔴" if p.get("priority") == "high" else "🟡" if p.get("priority") == "medium" else "🟢"
        pid = str(p.get("id", ""))[:8]
        lines.append(f"  {badge} [{pid}] {p.get('title', '?')}  ({p.get('priority','?')})")
    return "\n".join(lines)


async def _tool_approve_proposal(inp: Dict) -> str:
    import os

    from agents.base import AgentTask
    from agents.orchestrator_agent import OrchestratorAgent
    from core.platform.state import PlatformStateManager

    proposal_id = inp["proposal_id"]
    org_name = inp["org_name"]

    psm = PlatformStateManager()
    org = psm.load_organization_by_name(org_name)
    if not org:
        return f"❌ Organization '{org_name}' が見つかりません"

    sm = psm.get_org_state_manager(org)
    proposals = sm.get_pending_improvement_proposals(limit=100)
    target = next((p for p in proposals if str(p.get("id", "")).startswith(proposal_id)), None)
    if not target:
        return f"❌ ID '{proposal_id}' に一致する提案が見つかりません"

    repo_path = Path(org.target_repo_path) if org.target_repo_path else Path(".")
    sm.update_proposal_status(str(target.get("id", "")), "in_progress")

    agent = OrchestratorAgent.create()
    task = AgentTask(
        task_type="improvement_execution",
        description=f"改善提案の適用: {target.get('title')}",
        input={
            "repo_path": str(repo_path),
            "suggestion": target,
            "github_token": os.getenv("GITHUB_TOKEN"),
        },
    )
    result = await agent.run(task)
    if not result.success:
        sm.update_proposal_status(str(target.get("id", "")), "failed")
        return f"❌ 適用失敗: {result.error}"

    sm.update_proposal_status(str(target.get("id", "")), "done")
    return f"✅ '{target.get('title')}' を適用しました"


async def _tool_run_goal(inp: Dict) -> str:
    from core.goals.abstract_goal_pipeline import AbstractGoalPipeline

    goal_text = inp["goal_text"]

    pipeline = AbstractGoalPipeline()
    result = await pipeline.run(goal_text)
    summary = result.summary() if callable(getattr(result, "summary", None)) else str(result)
    return summary


async def _tool_platform_status(_input: Dict) -> str:
    from core.metrics.balanced_growth import calculate_organization_metrics
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager()
    orgs = psm.load_organizations()
    if not orgs:
        return "ℹ️  Organization がまだ登録されていません。\n   'Organization を追加して' と話しかけてください。"

    lines = [f"📊 プラットフォーム状態 ({len(orgs)} Organizations)\n"]
    for org in orgs:
        sm = psm.get_org_state_manager(org)
        proposals = sm.get_pending_improvement_proposals(limit=100)
        metrics = calculate_organization_metrics(org)
        health = getattr(metrics, "health_score", 0)
        lines.append(
            f"  {'🟢' if health >= 70 else '🟡' if health >= 40 else '🔴'} "
            f"{org.name}  health={health:.0f}%  未対応提案: {len(proposals)} 件"
        )
    return "\n".join(lines)


async def _tool_list_capabilities(_input: Dict) -> str:
    from core.intelligence.capability_registry import CapabilityRegistry

    registry = CapabilityRegistry()
    entries = registry.list_all()
    agents = [e for e in entries if e.capability_type == "agent"]
    skills = [e for e in entries if e.capability_type == "skill"]

    lines = [f"🤖 登録エージェント ({len(agents)} 件):\n"]
    for e in agents:
        lines.append(f"  • {e.name}")
    if skills:
        lines.append(f"\n🔧 スキル ({len(skills)} 件):\n")
        for s in skills[:10]:
            lines.append(f"  • {s.name}")
    return "\n".join(lines)


async def _tool_list_organizations(_input: Dict) -> str:
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager()
    orgs = psm.load_organizations()
    if not orgs:
        return "ℹ️  Organization がまだ登録されていません"

    lines = [f"📁 登録済み Organization ({len(orgs)} 件):\n"]
    for org in orgs:
        lines.append(f"  • {org.name}  →  {org.target_repo_path or '(リポジトリ未設定)'}")
    return "\n".join(lines)


TOOL_HANDLERS: Dict[str, Any] = {
    "initialize_platform": _tool_initialize_platform,
    "add_organization": _tool_add_organization,
    "analyze_organization": _tool_analyze_organization,
    "list_proposals": _tool_list_proposals,
    "approve_proposal": _tool_approve_proposal,
    "run_goal": _tool_run_goal,
    "platform_status": _tool_platform_status,
    "list_capabilities": _tool_list_capabilities,
    "list_organizations": _tool_list_organizations,
}


# ───────────────────────────────────────────────────── #
# ChatSession                                           #
# ───────────────────────────────────────────────────── #

@dataclass
class ChatSession:
    """
    対話セッション。会話履歴・現在のOrg等のコンテキストを保持する。
    LLMがあれば自然言語→ツール呼び出し、なければスラッシュコマンドのみ。
    """
    history: List[Dict[str, Any]] = field(default_factory=list)
    current_org: Optional[str] = None
    has_llm: bool = False
    config: Dict[str, Any] = field(default_factory=_load_llm_config)

    def __post_init__(self) -> None:
        self.refresh_llm_config()

    def refresh_llm_config(self) -> None:
        self.config = _load_llm_config()
        self.has_llm = _has_llm_config(self.config)
        if self.has_llm:
            _apply_llm_config_to_env(self.config)

    async def send(self, user_text: str) -> str:
        """ユーザーメッセージを処理して返答を返す。"""
        self.refresh_llm_config()

        context_note = ""
        if self.current_org:
            context_note = f"（現在の操作対象 Organization: {self.current_org}）"
        user_entry = user_text + context_note
        self.history.append({"role": "user", "content": user_entry})

        agent_result = await _handle_agent_task(user_text, self.config, self.current_org)
        if agent_result:
            self.history.append({"role": "assistant", "content": agent_result})
            return agent_result

        if not self.has_llm:
            return _missing_api_key_message(self.config) + "\n/help でコマンド一覧を確認してください。"

        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *self.history]
        response = await _generate_llm_response(messages, self.config)

        if response["tool_calls"]:
            tool_results = []
            for call in response["tool_calls"]:
                tool_name = call.get("name", "")
                tool_input = _parse_tool_input(call.get("input", {}))
                handler = TOOL_HANDLERS.get(tool_name)
                if handler:
                    try:
                        result_text = await handler(tool_input)
                        if "org_name" in tool_input:
                            self.current_org = tool_input["org_name"]
                    except Exception as exc:  # noqa: BLE001
                        result_text = f"❌ ツール実行エラー: {exc}"
                else:
                    result_text = f"❌ 未知のツール: {tool_name}"
                tool_results.append(result_text)

            combined = "\n\n".join(tool_results)
            self.history.append({"role": "assistant", "content": combined})
            return combined

        answer = response["content"]
        self.history.append({"role": "assistant", "content": answer})
        return answer


# ───────────────────────────────────────────────────── #
# スラッシュコマンド処理                                  #
# ───────────────────────────────────────────────────── #

HELP_TEXT = """\
╔══════════════════════════════════════════════════════════╗
║  RepoCorp AI チャットエージェント                          ║
╠══════════════════════════════════════════════════════════╣
║  【自然言語モード（設定済みLLMが必要）】                     ║
║   なんでも話しかけてください。例:                           ║
║    > ECサイトを作りたい                                   ║
║    > MyApp のコードをレビューして                           ║
║    > セキュリティの提案を全部承認して                        ║
╠══════════════════════════════════════════════════════════╣
║  【スラッシュコマンド（APIキー不要）】                       ║
║   /init                    プラットフォームを初期化          ║
║   /orgs                    Organization 一覧を表示          ║
║   /add <name> [repo]       Organization を追加              ║
║   /analyze <org>           リポジトリを分析                 ║
║   /proposals <org>         改善提案一覧                     ║
║   /approve <id> <org>      提案を承認                       ║
║   /goal <text>             ゴールを実行                     ║
║   /status                  プラットフォーム状態             ║
║   /agents                  エージェント一覧                 ║
║   /help                    このヘルプを表示                 ║
║   /exit                    終了                            ║
╚══════════════════════════════════════════════════════════╝"""


async def handle_slash_command(cmd: str, session: ChatSession) -> Optional[str]:
    """
    /xxx 形式のコマンドを処理する。
    Returns: 出力テキスト。None なら通常の自然言語処理にフォールバック。
    """
    try:
        parts = shlex.split(cmd.strip())
    except ValueError as exc:
        return f"コマンドを解析できませんでした: {exc}"
    if not parts:
        return None
    command = parts[0].lower()

    if command in ("/exit", "/quit", "/bye"):
        print("\n👋 またいつでも話しかけてください！")
        raise SystemExit(0)

    if command == "/help":
        return HELP_TEXT

    if command == "/init":
        return await _tool_initialize_platform({})

    if command == "/orgs":
        return await _tool_list_organizations({})

    if command == "/status":
        return await _tool_platform_status({})

    if command == "/agents":
        return await _tool_list_capabilities({})

    if command == "/add":
        if len(parts) < 2:
            return "使い方: /add <名前> [リポジトリパス]"
        name = parts[1]
        repo = parts[2] if len(parts) > 2 else str(Path.cwd())
        session.current_org = name
        return await _tool_add_organization({"name": name, "repo": repo})

    if command == "/analyze":
        org_name = parts[1] if len(parts) > 1 else session.current_org
        if not org_name:
            return "使い方: /analyze <Organization名>"
        session.current_org = org_name
        return await _tool_analyze_organization({"org_name": org_name})

    if command == "/proposals":
        org_name = parts[1] if len(parts) > 1 else session.current_org
        if not org_name:
            return "使い方: /proposals <Organization名>"
        session.current_org = org_name
        return await _tool_list_proposals({"org_name": org_name})

    if command == "/approve":
        if len(parts) < 3:
            return "使い方: /approve <提案ID> <Organization名>"
        return await _tool_approve_proposal({"proposal_id": parts[1], "org_name": parts[2]})

    if command == "/goal":
        if len(parts) < 2:
            return "使い方: /goal <ゴールテキスト>"
        goal_text = " ".join(parts[1:])
        return await _tool_run_goal({"goal_text": goal_text})

    # 未知のスラッシュコマンド
    return f"❓ 未知のコマンド '{command}'。/help でコマンド一覧を確認してください。"


# ───────────────────────────────────────────────────── #
# メインループ                                           #
# ───────────────────────────────────────────────────── #

async def run_chat(initial_message: Optional[str] = None) -> None:
    """
    対話ループのエントリーポイント。
    main.py の cmd_chat() から呼び出される。
    """
    session = ChatSession()
    session.refresh_llm_config()

    print("\n" + "═" * 58)
    print("  🤖 RepoCorp AI チャットエージェント")
    print("═" * 58)
    if session.has_llm:
        provider_label = PROVIDER_LABEL_MAP.get(session.config["provider"], session.config["provider"])
        print(f"  ✅ LLM接続: {provider_label} ({session.config['model']})")
        print("  🧠 自然言語の依頼は必要に応じて PreTaskOrchestrator 経由で実行されます")
    else:
        print(f"  ⚠️  {_missing_api_key_message(session.config).replace(chr(10), ' ')}")
        print("  ℹ️  スラッシュコマンドのみ利用可能です（/help）")
    print("  終了: /exit または Ctrl+C")
    print("═" * 58 + "\n")

    # 初期メッセージがあれば最初に処理
    if initial_message:
        print(f"you> {initial_message}")
        await _process_input(initial_message, session)

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 またいつでも話しかけてください！")
            break

        if not user_input:
            continue

        await _process_input(user_input, session)


async def _process_input(user_input: str, session: ChatSession) -> None:
    """1つのユーザー入力を処理して結果を表示する。"""
    print()  # 視認性のための改行

    if user_input.startswith("/"):
        try:
            result = await handle_slash_command(user_input, session)
            if result is not None:
                print(result)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"❌ コマンドエラー: {exc}")
    else:
        # 自然言語 → LLM
        try:
            response = await session.send(user_input)
            print(f"🤖 {response}")
        except Exception as exc:  # noqa: BLE001
            logger.error("Chat error: %s", exc, exc_info=True)
            print(f"❌ エラーが発生しました: {exc}")

    print()  # 視認性のための改行
