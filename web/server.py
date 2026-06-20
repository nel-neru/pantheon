"""
Pantheon - Web Server (Platform Level)

PlatformStateManager を使ってプラットフォーム全体を管理する FastAPI サーバー。
"""

from __future__ import annotations

import asyncio
import base64
import colorsys
import hashlib
import json
import logging
import os
import re
import secrets
import stat
import subprocess
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.models.organization import ImprovementProposal, is_active_improvement_proposal_status
from core.paths import resource_path, resource_root
from core.persistence import atomic_write_text
from core.platform.state import PlatformStateManager, get_platform_home, resolve_environment
from core.policy.engine import DEFAULT_POLICY, ApprovalDecision, PolicyEngine

logger = logging.getLogger(__name__)
app = FastAPI(title="Pantheon Platform", version="2.0.0")

# 同梱リソースは resource_path 経由で解決する（exe 化時は sys._MEIPASS 配下）。
STATIC_DIR = resource_path("web", "static")
DIST_DIR = resource_path("web", "dist")
PROJECT_ROOT = resource_root()
KNOWLEDGE_DIR = resource_path("knowledge")
SYSTEM_ORG_NAMES = {"Meta-Improvement Organization", "Pantheon Core", "meta-improvement"}


# PANTHEON_HOME を尊重して解決する（dev/prod 環境のデータ完全分離）。
# 重要: import 時にモジュール定数として凍結せず、get_platform_home() を毎回呼ぶ遅延解決にする。
# 定数として凍結すると import より後に PANTHEON_HOME が変わる場合（テストの import 順・将来の
# 動的切替）に古い領域を指し続ける（実行順依存フラジリティ）。PlatformStateManager /
# OutcomeStore / TaskQueue は全て get_platform_home() を遅延呼び出ししており、それに揃える。
# 後方互換のため module 属性 ``server.SETTINGS_FILE`` / ``server.CHAT_SESSIONS_DIR`` の読み取りは
# 下の __getattr__ が遅延解決する。内部コードはヘルパ関数を直接呼ぶ。
def _settings_file() -> Path:
    """GUI 設定ファイルのパス（現在の get_platform_home() 由来・遅延解決）。"""
    return get_platform_home() / "gui_settings.json"


def _chat_sessions_dir() -> Path:
    """チャットセッション保存先（現在の get_platform_home() 由来・遅延解決）。"""
    return get_platform_home() / "chat_sessions"


DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)
_chat_sessions_dir().mkdir(parents=True, exist_ok=True)


def __getattr__(name: str):
    """PEP 562: ``SETTINGS_FILE`` / ``CHAT_SESSIONS_DIR`` を遅延解決の module 属性として公開する。

    内部コードはヘルパ関数（``_settings_file`` / ``_chat_sessions_dir``）を直接呼ぶ。テストは
    そのヘルパ関数を monkeypatch する（関数なら monkeypatch の復元が遅延性を保ち、定数の再 setattr で
    stale な tmp パスを module 辞書へ再凍結する事故を避けられる）。
    """
    if name == "SETTINGS_FILE":
        return _settings_file()
    if name == "CHAT_SESSIONS_DIR":
        return _chat_sessions_dir()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# 注: ホスト型プロバイダのキー対応表/モデル一覧（旧 _PROVIDER_KEY_MAPPING / FALLBACK_MODELS）は
# Claude Code CLI 専用化により完全な dead code だったため削除（2026-06-14 リポジトリ衛生監査）。
# 生成は core/runtime/claude_code.ClaudeCodeProvider 経由のみ。モデル一覧は CLAUDE_MODELS を使う。
DEFAULT_MODEL_CONFIGURATIONS = {
    "default": {
        "temperature": 0.2,
        "max_tokens": 4096,
        "fallback_model": "",
        "reasoning_effort": "balanced",
    },
    "providers": {
        "anthropic": {"temperature": 0.2, "max_tokens": 4096},
        "openai": {"temperature": 0.2, "max_tokens": 4096},
        "groq": {"temperature": 0.1, "max_tokens": 8192},
        "github_models": {"temperature": 0.2, "max_tokens": 4096},
        "gemini": {"temperature": 0.2, "max_tokens": 4096},
    },
}
DEFAULT_PROMPT_TEMPLATES = {
    "analysis": "Analyze the repository, summarize risks, and propose the highest-value improvements.",
    "goal_execution": "Plan the goal, execute the highest-priority steps, and report measurable outcomes.",
    "proposal_review": "Review the proposal diff, identify risk, and capture the rationale for approval or rejection.",
}


def _default_gui_settings() -> Dict[str, Any]:
    return {
        "llm_provider": os.getenv("PANTHEON_DEFAULT_LLM_PROVIDER", "anthropic"),
        "llm_model": os.getenv("PANTHEON_DEFAULT_MODEL", "claude-3-5-sonnet-20241022"),
        "anthropic_api_key": "",
        "openai_api_key": "",
        "groq_api_key": "",
        "github_models_api_key": "",
        "gemini_api_key": "",
        "daemon_interval": 3600,
        "daemon_max_files": 10,
        "model_configurations": deepcopy(DEFAULT_MODEL_CONFIGURATIONS),
        "prompt_templates": deepcopy(DEFAULT_PROMPT_TEMPLATES),
        "policy_rules": deepcopy(DEFAULT_POLICY),
    }


_model_cache: dict[str, tuple[list[str], float]] = {}
_CACHE_TTL = 300


def _cors_allowed_origins() -> list[str]:
    raw_origins = os.getenv("PANTHEON_CORS_ORIGINS", "")
    if raw_origins.strip():
        origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
        if origins:
            return origins
    return list(DEFAULT_CORS_ORIGINS)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 任意の API トークン認証: PANTHEON_API_TOKEN を設定した場合のみ /api/* と
# /ws/* に Bearer 認証を要求する（未設定なら従来どおり認証なし＝ローカル利用前提）。
# LAN 公開（--host 0.0.0.0）時の必須ガード。
API_TOKEN_ENV = "PANTHEON_API_TOKEN"


def _configured_api_token() -> str:
    return os.getenv(API_TOKEN_ENV, "").strip()


def _token_matches(provided: str, token: str) -> bool:
    # ヘッダ/クエリは latin-1 由来で非 ASCII を含み得る。compare_digest は
    # str に非 ASCII があると TypeError を投げるため、必ず bytes 同士で比較する
    # （latin-1 文字列の UTF-8 エンコードは決して例外を投げない）。
    return secrets.compare_digest(provided.encode("utf-8"), token.encode("utf-8"))


@app.middleware("http")
async def _api_token_guard(request, call_next):
    token = _configured_api_token()
    # OPTIONS（CORS preflight）は仕様上 Authorization を運ばないため除外する
    # （この guard は CORSMiddleware より外側で実行されるので、ここで弾くと
    # クロスオリジン構成の preflight が 401 になり UI が壊れる）。
    if token and request.method != "OPTIONS" and request.url.path.startswith("/api"):
        auth = request.headers.get("authorization") or ""
        provided = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if not _token_matches(provided, token):
            return Response(
                content='{"detail": "Unauthorized"}',
                status_code=401,
                media_type="application/json",
            )
    return await call_next(request)


async def _reject_ws_if_unauthorized(websocket: WebSocket) -> bool:
    """トークン設定時、未認証 WS を accept 前に 1008 で閉じる。

    ブラウザは WebSocket に Authorization ヘッダを付けられないため、トークンは
    クエリ文字列（``?token=``）で受け取る。``True`` を返したら呼び出し側は即 return。
    """
    token = _configured_api_token()
    if not token:
        return False
    provided = (websocket.query_params.get("token") or "").strip()
    if _token_matches(provided, token):
        return False
    await websocket.close(code=1008)  # policy violation
    return True


# Serve React build (dist/) when available, fallback to legacy static/
def _resolve_serve_dir() -> Path:
    """配信する frontend の dist を選ぶ（web/dist、無ければ静的フォールバック）。"""
    return DIST_DIR if DIST_DIR.is_dir() else STATIC_DIR


_serve_dir = _resolve_serve_dir()
app.mount(
    "/assets",
    StaticFiles(
        directory=_serve_dir / "assets" if (_serve_dir / "assets").is_dir() else STATIC_DIR
    ),
    name="assets",
)


def _warn_if_settings_permissions_too_open(path: Path) -> None:
    if os.name == "nt" or not path.exists():
        return
    try:
        file_mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return
    if file_mode & 0o077:
        logger.warning(
            "GUI settings file permissions are too open (%s: %s); expected 0o600",
            path,
            oct(file_mode),
        )


def _set_settings_file_permissions(path: Path) -> None:
    if os.name == "nt" or not path.exists():
        return
    try:
        path.chmod(0o600)
    except OSError as exc:
        logger.warning("Failed to set restrictive permissions on %s: %s", path, exc)


def _load_gui_settings() -> Dict[str, Any]:
    """GUI 設定ファイルを読み込む（存在しなければデフォルト値を返す）"""
    defaults = _default_gui_settings()
    settings_file = _settings_file()
    if settings_file.exists():
        _warn_if_settings_permissions_too_open(settings_file)
        try:
            loaded = json.loads(settings_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                merged = deepcopy(defaults)
                merged.update(
                    {
                        k: v
                        for k, v in loaded.items()
                        if k not in {"model_configurations", "prompt_templates", "policy_rules"}
                    }
                )
                for key in ("model_configurations", "prompt_templates", "policy_rules"):
                    value = loaded.get(key)
                    if isinstance(value, dict):
                        merged[key] = value
                return merged
        except Exception:
            pass
    return defaults


def _save_gui_settings(data: Dict[str, Any]) -> None:
    settings_file = _settings_file()
    # 原子的に書く（書きかけ JSON を残さない）。atomic_write_text が parent.mkdir を内包。
    # 一時ファイルは mkstemp（0o600 生成）→ os.replace なので最終ファイルへ
    # _set_settings_file_permissions を適用すれば権限も維持される。
    atomic_write_text(settings_file, json.dumps(data, ensure_ascii=False, indent=2))
    _set_settings_file_permissions(settings_file)


def _ensure_chat_sessions_dir() -> None:
    _chat_sessions_dir().mkdir(parents=True, exist_ok=True)


def _get_session_path(session_id: str) -> Path:
    _ensure_chat_sessions_dir()
    sessions_dir = _chat_sessions_dir()
    path = (sessions_dir / f"{session_id}.json").resolve()
    try:
        path.relative_to(sessions_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="不正なセッションIDです") from exc
    return path


def _load_session(session_id: str) -> dict[str, Any] | None:
    path = _get_session_path(session_id)
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _save_session(session: dict[str, Any]) -> None:
    _ensure_chat_sessions_dir()
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = _get_session_path(session["id"])
    # 原子的に書く（プロセス強制終了でも切り詰めた壊れセッション JSON を残さない）。
    atomic_write_text(path, json.dumps(session, ensure_ascii=False, indent=2))


def _list_sessions(limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
    _ensure_chat_sessions_dir()
    # mtime 降順でソートしてから limit/offset で先に切り、必要分だけ json.load する
    # （数千セッションでも全件 load+parse しない＝メモリ churn 抑制）。
    paths = sorted(
        _chat_sessions_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if offset:
        paths = paths[offset:]
    if limit is not None:
        paths = paths[:limit]
    sessions = []
    for path in paths:
        try:
            with path.open(encoding="utf-8") as f:
                session = json.load(f)
            sessions.append(
                {
                    "id": session["id"],
                    "name": session.get("name") or "無題のセッション",
                    "created_at": session.get("created_at", ""),
                    "updated_at": session.get("updated_at", ""),
                    "message_count": len(session.get("messages", [])),
                }
            )
        except Exception:
            continue
    return sessions


def _infer_current_org(messages: list[dict[str, Any]] | None) -> str | None:
    current_org = None
    for message in messages or []:
        if message.get("role") != "user":
            continue
        content = str(message.get("content", "")).strip()
        if not content.startswith("/"):
            continue
        parts = content.split()
        if not parts:
            continue
        command = parts[0].lower()
        if command == "/add" and len(parts) > 1:
            current_org = parts[1]
        elif command in {"/analyze", "/proposals"} and len(parts) > 1:
            current_org = parts[1]
        elif command == "/approve" and len(parts) > 2:
            current_org = parts[2]
    return current_org


def _restore_chat_session(chat_session: Any, session_context: list[dict[str, Any]] | None) -> None:
    chat_session.history = [
        {"role": message["role"], "content": message["content"]}
        for message in session_context or []
        if message.get("role") in {"user", "assistant"} and isinstance(message.get("content"), str)
    ]
    chat_session.current_org = _infer_current_org(session_context)


async def _dispatch_chat_message(chat_session: Any, message: str, allow_exit: bool = False) -> str:
    from agents.chat_agent import handle_slash_command

    if message.startswith("/"):
        try:
            result = await handle_slash_command(message, chat_session)
        except SystemExit:
            if allow_exit:
                raise
            return "👋 またいつでも話しかけてください！"
        except Exception as exc:  # noqa: BLE001
            return f"[ERROR] コマンドエラー: {exc}"
        return result or ""

    try:
        return await chat_session.send(message)
    except Exception as exc:  # noqa: BLE001
        return f"[ERROR] エラーが発生しました: {exc}"


async def _process_chat_message(
    message: str, session_context: list[dict[str, Any]] | None = None
) -> str:
    from agents.chat_agent import ChatSession

    chat_session = ChatSession(has_llm=_has_llm())
    _restore_chat_session(chat_session, session_context)
    return await _dispatch_chat_message(chat_session, message)


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return ""
    return key[:8] + "..." + key[-4:]


def _get_cached_models(provider: str) -> list[str] | None:
    if provider in _model_cache:
        models, ts = _model_cache[provider]
        if time.time() - ts < _CACHE_TTL:
            return models
    return None


def _set_cached_models(provider: str, models: list[str]) -> None:
    _model_cache[provider] = (models, time.time())


def _normalize_request_path(
    value: str,
    field_name: str,
    *,
    allow_empty: bool = True,
    file_name_only: bool = False,
) -> str:
    if "\x00" in value:
        raise ValueError(f"{field_name} に無効な文字が含まれています")
    if value == "":
        if allow_empty:
            return value
        raise ValueError(f"{field_name} は必須です")

    normalized = Path(os.path.normpath(str(Path(value).expanduser())))
    if any(part == ".." for part in normalized.parts):
        raise ValueError(f"{field_name} に親ディレクトリ参照は使えません")
    if file_name_only and (normalized.is_absolute() or len(normalized.parts) != 1):
        raise ValueError(f"{field_name} にはファイル名のみ指定できます")
    return str(normalized)


class ApiRequestModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class OrgCreateRequest(ApiRequestModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(default="", max_length=2000)
    # 中核モデル「1 ワークスペース = 1 Organization」: 担当 repo は必須。
    target_repo_path: str = Field(min_length=1, max_length=4096)
    # isolation_level を GUI でも第一級に（CLI と同一挙動）。external でないと境界ガードが効かない。
    isolation_level: Literal["core", "standard", "external"] = "standard"
    allowed_path_scope: List[str] = Field(default_factory=list, max_length=64)

    @field_validator("target_repo_path")
    @classmethod
    def validate_target_repo_path(cls, value: str) -> str:
        return _normalize_request_path(value, "target_repo_path", allow_empty=False)


class OrgIconRequest(ApiRequestModel):
    icon_data: str = Field(max_length=512 * 1024)


class BusinessRouteModel(ApiRequestModel):
    from_org: str = Field(min_length=1, max_length=120)
    to_org: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="content_brief", max_length=64)


class BusinessCreateRequest(ApiRequestModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(default="", max_length=2000)
    member_orgs: List[str] = Field(default_factory=list, max_length=64)
    roles: Dict[str, str] = Field(default_factory=dict)
    handoff_routes: List[BusinessRouteModel] = Field(default_factory=list, max_length=64)
    kpis: List[str] = Field(default_factory=list, max_length=64)


class BusinessUpdateRequest(ApiRequestModel):
    """Business の部分更新（None のフィールドは変更しない）。"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    purpose: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[str] = Field(default=None, max_length=32)
    member_orgs: Optional[List[str]] = Field(default=None, max_length=64)
    roles: Optional[Dict[str, str]] = Field(default=None)
    kpis: Optional[List[str]] = Field(default=None, max_length=64)


class AnalyzeRequest(ApiRequestModel):
    org_name: str = Field(min_length=1, max_length=120)
    max_files: int = Field(default=15, ge=1, le=50)


class ProposalApproveRequest(ApiRequestModel):
    approval_notes: str | None = Field(default=None, max_length=2000)


class GoalRunRequest(ApiRequestModel):
    goal_text: str = Field(min_length=1, max_length=4000)


class DaemonStartRequest(ApiRequestModel):
    interval: int = Field(default=3600, ge=1)
    max_files: int = Field(default=10, ge=1, le=1000)


class DaemonsActionRequest(ApiRequestModel):
    """統合 daemon API（/api/daemons/{name}/start）の起動オプション。"""

    interval: int | None = Field(default=None, ge=1)
    max_files: int | None = Field(default=None, ge=1, le=1000)
    # revenue daemon 用（target>0 で自律経営 cadence を起動する・P14）。
    target: float | None = Field(default=None, ge=0)
    source_org: str | None = Field(default=None, max_length=120)
    min_reach: float | None = Field(default=None, ge=0)


class TaskQueueRequest(ApiRequestModel):
    task_type: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    org_name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=1, le=10)


class ChatPayload(ApiRequestModel):
    message: str = Field(max_length=4000)


class ChatRequest(ApiRequestModel):
    message: str = Field(max_length=4000)
    session_context: list[dict[str, Any]] = Field(default_factory=list)


class ChatSessionCreate(ApiRequestModel):
    name: str = Field(default="", max_length=120)


class ChatSessionUpdate(ApiRequestModel):
    name: str = Field(max_length=120)


class ChatMessageCreate(ApiRequestModel):
    content: str = Field(max_length=4000)
    role: Literal["user"] = "user"


class KnowledgeFileUpdate(ApiRequestModel):
    content: str = Field(max_length=200000)


class KnowledgeFileCreate(ApiRequestModel):
    name: str = Field(max_length=255)
    content: str = Field(default="", max_length=200000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_request_path(value, "name", allow_empty=False, file_name_only=True)


class ProposalBatchRequest(ApiRequestModel):
    proposal_ids: list[str] = Field(min_length=1, max_length=100)
    action: Literal["approve", "reject"]


class PlatformStatusResponse(BaseModel):
    group_health_score: float
    balance_score: float
    total_organizations: int
    active_organizations: int
    weakest_organization: str | None
    strongest_organization: str | None
    platform_home: str
    initialized: bool
    has_llm: bool
    environment: str = "production"
    env_label: str = "PROD"


class DaemonStatusResponse(BaseModel):
    status: str | None = None
    message: str | None = None
    running: bool
    pid: int | None
    log_path: str | None
    interval: int | None = None
    max_files: int | None = None
    # プロセス横断レート制限ゲート（~/.pantheon/rate_limit_state.json）の状態。
    rate_limited: bool = False
    retry_at: str | None = None
    rate_limit_scope: str | None = None


class PlatformInitResponse(BaseModel):
    status: str
    message: str
    platform_home: str
    meta_improvement_org: str | None = None
    initialized: bool


class AnalyzeResponse(BaseModel):
    org_name: str
    files_reviewed: int
    proposals_generated: int
    generated_proposals: list[dict[str, Any]] = Field(default_factory=list)


class GoalHistoryItemResponse(BaseModel):
    id: str | None = None
    goal: str
    result: str
    timestamp: str
    org_name: str | None = None
    summary: str | None = None
    goal_text: str | None = None
    created_at: str | None = None
    organization: str | None = None
    success: bool | None = None
    goal_type: str | None = None
    scale: str | None = None
    done_count: int | None = None
    total: int | None = None
    failed_count: int | None = None
    achievement_pct: float | None = None
    recommendations: list[Any] = Field(default_factory=list)


class SettingsResponse(BaseModel):
    llm_provider: str
    llm_model: str
    anthropic_api_key_masked: str
    openai_api_key_masked: str
    groq_api_key_masked: str
    github_models_api_key_masked: str
    gemini_api_key_masked: str
    anthropic_api_key_set: bool
    openai_api_key_set: bool
    groq_api_key_set: bool
    github_models_api_key_set: bool
    gemini_api_key_set: bool
    daemon_interval: int
    daemon_max_files: int
    model_configurations: dict[str, Any] = Field(default_factory=dict)
    prompt_templates: dict[str, str] = Field(default_factory=dict)
    policy_rules: dict[str, Any] = Field(default_factory=dict)
    # SET-EXPOSE（§4 P2-5/P3-12）: トークンクォータ・通知を統一アプリ設定へ露出。
    token_quota: dict[str, Any] = Field(default_factory=dict)
    notification_settings: dict[str, Any] = Field(default_factory=dict)
    settings_file: str
    has_llm: bool


class ProviderModelsResponse(BaseModel):
    provider: str
    models: list[str] = Field(default_factory=list)
    source: str


class ExecutionHistoryItemResponse(BaseModel):
    id: str
    timestamp: str
    operation: str
    status: str
    title: str
    details: str = ""
    org_name: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    route: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResultItemResponse(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str = ""
    route: str
    org_name: str | None = None
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


PLATFORM_STATUS_EXAMPLE = {
    "group_health_score": 82.5,
    "balance_score": 91.0,
    "total_organizations": 3,
    "active_organizations": 2,
    "weakest_organization": "sandbox",
    "strongest_organization": "platform-core",
    "platform_home": str(Path.home() / ".pantheon"),
    "initialized": True,
    "has_llm": True,
    "environment": "production",
    "env_label": "PROD",
}
DAEMON_STATUS_EXAMPLE = {
    "running": True,
    "pid": 4321,
    "log_path": str(Path.home() / ".pantheon" / "daemon.log"),
    "rate_limited": False,
}
DAEMON_ACTION_EXAMPLE = {
    "status": "started",
    "message": "デーモンを起動しました。",
    "running": True,
    "pid": 4321,
    "log_path": str(Path.home() / ".pantheon" / "daemon.log"),
    "interval": 3600,
    "max_files": 10,
}
INIT_RESPONSE_EXAMPLE = {
    "status": "initialized",
    "message": "プラットフォームを初期化しました。",
    "platform_home": str(Path.home() / ".pantheon"),
    "meta_improvement_org": "Meta-Improvement Organization",
    "initialized": True,
}
ANALYZE_RESPONSE_EXAMPLE = {
    "org_name": "demo-org",
    "files_reviewed": 12,
    "proposals_generated": 3,
    "generated_proposals": [
        {
            "id": "proposal-1",
            "priority": "high",
            "category": "quality",
            "title": "テストを追加する",
            "description": "エッジケースをカバーするテストが不足しています。",
            "file_path": "web/server.py",
            "expected_impact": "回帰を防止できます。",
            "status": "proposed",
        }
    ],
}
GOAL_HISTORY_EXAMPLE = {
    "goal": "品質を改善する",
    "goal_text": "品質を改善する",
    "result": "改善提案を3件作成しました。",
    "summary": "改善提案を3件作成しました。",
    "timestamp": "2025-01-01T00:00:00+00:00",
    "created_at": "2025-01-01T00:00:00+00:00",
    "org_name": "Platform",
    "organization": "Platform",
    "success": True,
    "goal_type": "quality",
    "scale": "medium",
    "done_count": 3,
    "total": 3,
    "failed_count": 0,
    "achievement_pct": 100.0,
    "recommendations": [],
}
SETTINGS_RESPONSE_EXAMPLE = {
    "llm_provider": "anthropic",
    "llm_model": "claude-3-5-sonnet-20241022",
    "anthropic_api_key_masked": "sk-ant-****",
    "openai_api_key_masked": "",
    "groq_api_key_masked": "",
    "github_models_api_key_masked": "",
    "gemini_api_key_masked": "",
    "anthropic_api_key_set": True,
    "openai_api_key_set": False,
    "groq_api_key_set": False,
    "github_models_api_key_set": False,
    "gemini_api_key_set": False,
    "daemon_interval": 3600,
    "daemon_max_files": 10,
    "settings_file": str(Path.home() / ".pantheon" / "gui_settings.json"),
    "has_llm": True,
}
PROVIDER_MODELS_EXAMPLE = {
    "provider": "anthropic",
    "models": ["claude-opus-4-5", "claude-sonnet-4-5"],
    "source": "api",
}
EXECUTION_HISTORY_EXAMPLE = {
    "id": "org-create-1",
    "timestamp": "2025-01-01T00:00:00+00:00",
    "operation": "organization_created",
    "status": "success",
    "title": "Organization created",
    "details": "Created sample-org",
    "org_name": "sample-org",
    "entity_type": "organization",
    "entity_id": "sample-org",
    "route": "/orgs",
    "metadata": {},
}
SEARCH_RESULT_EXAMPLE = {
    "id": "organization:sample-org",
    "type": "organization",
    "title": "sample-org",
    "subtitle": "Demo organization",
    "route": "/orgs",
    "org_name": "sample-org",
    "status": "active",
    "metadata": {},
}


class UpdateHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, event: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections)

        stale: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(event)
            except Exception:
                stale.append(connection)

        if stale:
            async with self._lock:
                for connection in stale:
                    self._connections.discard(connection)


_updates_hub = UpdateHub()

# --- Live session monitor (GUI=監視) ----------------------------------------- #
# 実行系は wmux の「監視セッション」として走る（core/runtime/work_launcher）。サーバは
# アクティブなセッションをポーリングし、状態が変わったら /ws/updates へ push する。テストで
# 勝手に動かないよう run_server() が呼ばれたときだけ有効化する（_LIVE_MONITOR_ENABLED）。
_LIVE_MONITOR_ENABLED = False
_session_monitor_task: "asyncio.Task[None] | None" = None
_session_status_cache: dict[str, str] = {}
# /api/tasks（人間が起票する作業ボード）の drain。run_server 時に config
# auto_drain_tasks（既定 True）で有効化され、PENDING タスクを wmux の work セッションへ
# 着火（dispatch）する。テストでは _TASK_DRAIN_ENABLED が False のまま動かない。
_TASK_DRAIN_ENABLED = False
_task_drain_task: "asyncio.Task[None] | None" = None


def _session_signature(rec: Any) -> str:
    parts = [rec.status]
    for surface in rec.surfaces:
        parts.append(
            f"{surface.get('agent_id')}:{surface.get('status')}:{surface.get('exit_code')}"
        )
    return "|".join(str(p) for p in parts)


async def _poll_and_broadcast_sessions() -> None:
    """アクティブセッションをポーリングし、変化したものを /ws/updates へ配信する。"""
    orch = _session_orchestrator()
    sessions = await asyncio.to_thread(orch.list_sessions)
    for rec in sessions:
        if rec.status in ("running", "rate_limited"):
            polled = await asyncio.to_thread(orch.poll_session, rec.id)
            rec = polled or rec
        signature = _session_signature(rec)
        if _session_status_cache.get(rec.id) == signature:
            continue
        _session_status_cache[rec.id] = signature
        await _updates_hub.broadcast(
            {
                "type": "session_update",
                "session_id": rec.id,
                "name": rec.name,
                "status": rec.status,
                "driver": rec.driver,
                "title": f"{rec.name}: {rec.status}",
                "agents": [
                    {
                        "agent_id": s.get("agent_id"),
                        "title": s.get("title"),
                        "status": s.get("status"),
                        "exit_code": s.get("exit_code"),
                    }
                    for s in rec.surfaces
                ],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


async def _session_monitor_loop(interval: float = 3.0) -> None:
    while _LIVE_MONITOR_ENABLED:
        try:
            await _poll_and_broadcast_sessions()
        except Exception:  # noqa: BLE001 - 監視ループは決して落とさない
            logger.debug("session monitor iteration failed", exc_info=True)
        await asyncio.sleep(interval)


async def _drain_pending_tasks() -> None:
    """PENDING タスクを wmux work セッションへ dispatch し、結果を /ws/updates へ配信する。

    drain の本体（executor を組んで pending を捌く）は CLI（``pantheon tasks drain``）
    / headless daemon（``task``）と共通の ``core.runtime.task_drain.drain_pending_tasks``
    に集約している。ここは web 固有の broadcast 提示だけを担う。
    """
    from core.runtime.task_drain import drain_pending_tasks

    results = await drain_pending_tasks(queue=_task_queue(), max_tasks=5)
    for result in results:
        if isinstance(result, dict) and result.get("session_id"):
            await _updates_hub.broadcast(
                {
                    "type": "task_dispatched",
                    "session_id": result["session_id"],
                    "driver": result.get("driver"),
                    "title": "作業ボードのタスクを wmux に着火しました",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )


async def _task_drain_loop(interval: float = 5.0) -> None:
    while _LIVE_MONITOR_ENABLED and _TASK_DRAIN_ENABLED:
        try:
            await _drain_pending_tasks()
        except Exception:  # noqa: BLE001 - drain ループは決して落とさない
            logger.debug("task drain iteration failed", exc_info=True)
        await asyncio.sleep(interval)


def _ensure_session_monitor() -> None:
    """ライブ監視ループと（有効時）task drain を一度だけ起動する。

    いずれも run_server 経由で有効化されている場合のみ動く（テストでは起動しない）。
    """
    global _session_monitor_task, _task_drain_task
    if not _LIVE_MONITOR_ENABLED:
        return
    if _session_monitor_task is None or _session_monitor_task.done():
        try:
            _session_monitor_task = asyncio.create_task(_session_monitor_loop())
        except RuntimeError:  # 実行中ループが無い場合（通常リクエスト中は発生しない）
            pass
    if _TASK_DRAIN_ENABLED and (_task_drain_task is None or _task_drain_task.done()):
        try:
            _task_drain_task = asyncio.create_task(_task_drain_loop())
        except RuntimeError:
            pass


def _migrate_system_orgs(psm: PlatformStateManager | None = None) -> None:
    state_manager = psm or PlatformStateManager()
    meta_org_id = state_manager.load_platform_config().get("meta_improvement_org_id")

    for org in state_manager.load_organizations():
        should_protect = org.name in SYSTEM_ORG_NAMES or (
            meta_org_id and str(org.id) == meta_org_id
        )
        if should_protect and not org.is_system:
            org.is_system = True
            state_manager.save_organization(org)


def _psm() -> PlatformStateManager:
    psm = PlatformStateManager()
    _migrate_system_orgs(psm)
    return psm


def _task_queue():
    from core.orchestration.task_queue import TaskQueue

    return TaskQueue()


def _has_llm(settings: Dict[str, Any] | None = None) -> bool:
    # Pantheon's only execution backend is the local Claude Code CLI.
    from core.runtime.claude_code import claude_available

    return claude_available()


def _goal_history_path() -> Path:
    return _psm().platform_home / "goal_history.json"


def _normalize_goal_history_item(item: dict[str, Any]) -> dict[str, Any]:
    goal = str(item.get("goal") or item.get("goal_text") or "")
    result = str(item.get("result") or item.get("summary") or "")
    timestamp = str(item.get("timestamp") or item.get("created_at") or "")
    org_name = item.get("org_name") or item.get("organization")
    normalized = dict(item)
    normalized.update(
        {
            "goal": goal,
            "goal_text": str(item.get("goal_text") or goal),
            "result": result,
            "summary": str(item.get("summary") or result),
            "timestamp": timestamp,
            "created_at": str(item.get("created_at") or timestamp),
            "org_name": org_name,
            "organization": item.get("organization") or org_name,
            "recommendations": item.get("recommendations")
            if isinstance(item.get("recommendations"), list)
            else [],
        }
    )
    return normalized


def _load_goal_history() -> list[dict[str, Any]]:
    path = _goal_history_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [_normalize_goal_history_item(item) for item in data if isinstance(item, dict)]


def _save_goal_history(record: dict[str, Any], keep: int = 12) -> None:
    history = [_normalize_goal_history_item(record), *_load_goal_history()][:keep]
    # read-modify-write の state。torn write でゴール履歴が破損しないよう原子的に書く。
    atomic_write_text(
        _goal_history_path(),
        json.dumps(history, ensure_ascii=False, indent=2),
    )


def _execution_history_path() -> Path:
    return _psm().platform_home / "execution_history.json"


def _normalize_execution_history_item(item: dict[str, Any]) -> dict[str, Any]:
    timestamp = str(item.get("timestamp") or datetime.now(timezone.utc).isoformat())
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return {
        "id": str(item.get("id") or uuid4()),
        "timestamp": timestamp,
        "operation": str(item.get("operation") or "event"),
        "status": str(item.get("status") or "info"),
        "title": str(item.get("title") or "Pantheon event"),
        "details": str(item.get("details") or ""),
        "org_name": item.get("org_name"),
        "entity_type": item.get("entity_type"),
        "entity_id": str(item.get("entity_id")) if item.get("entity_id") is not None else None,
        "route": item.get("route"),
        "metadata": metadata,
    }


def _load_execution_history() -> list[dict[str, Any]]:
    path = _execution_history_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [_normalize_execution_history_item(item) for item in data if isinstance(item, dict)]


def _save_execution_history(records: list[dict[str, Any]], keep: int = 200) -> None:
    normalized = [_normalize_execution_history_item(record) for record in records][:keep]
    # read-modify-write の state。torn write で実行履歴が破損しないよう原子的に書く。
    atomic_write_text(
        _execution_history_path(),
        json.dumps(normalized, ensure_ascii=False, indent=2),
    )


def _append_execution_history(record: dict[str, Any], keep: int = 200) -> dict[str, Any]:
    normalized = _normalize_execution_history_item(record)
    _save_execution_history([normalized, *_load_execution_history()], keep=keep)
    return normalized


def _matches_search_text(query: str, *values: Any) -> bool:
    needle = query.strip().lower()
    if not needle:
        return True
    return any(
        needle in str(value).lower() for value in values if value is not None and value != ""
    )


def _goal_history_execution_items() -> list[dict[str, Any]]:
    items = []
    for goal in _load_goal_history():
        items.append(
            _normalize_execution_history_item(
                {
                    "id": f"goal-{goal.get('id') or hashlib.sha1(json.dumps(goal, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:12]}",
                    "timestamp": goal.get("timestamp") or goal.get("created_at"),
                    "operation": "goal_completed",
                    "status": "success" if goal.get("success", True) else "error",
                    "title": goal.get("goal") or goal.get("goal_text") or "Goal run",
                    "details": goal.get("result") or goal.get("summary") or "",
                    "org_name": goal.get("org_name") or goal.get("organization"),
                    "entity_type": "goal",
                    "entity_id": goal.get("id") or goal.get("goal_text"),
                    "route": "/data",
                    "metadata": {
                        "success": goal.get("success"),
                        "goal_type": goal.get("goal_type"),
                        "scale": goal.get("scale"),
                    },
                }
            )
        )
    return items


def _task_execution_items() -> list[dict[str, Any]]:
    items = []
    for task in _task_queue().list_tasks(limit=None):
        timestamp = task.get("completed_at") or task.get("started_at") or task.get("created_at")
        status = str(task.get("status") or "pending")
        items.append(
            _normalize_execution_history_item(
                {
                    "id": f"task-{task.get('id')}",
                    "timestamp": timestamp,
                    "operation": f"task_{status}",
                    "status": "error"
                    if status == "failed"
                    else "success"
                    if status in {"done", "cancelled"}
                    else "pending",
                    "title": task.get("description") or "Task update",
                    "details": task.get("error") or "",
                    "org_name": task.get("org_name"),
                    "entity_type": "task",
                    "entity_id": task.get("id"),
                    "route": "/dashboard",
                    "metadata": {
                        "task_type": task.get("type"),
                        "status": status,
                        "result": task.get("result"),
                    },
                }
            )
        )
    return items


def _combined_execution_history(
    search: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    records = [
        *_load_execution_history(),
        *_goal_history_execution_items(),
        *_task_execution_items(),
    ]
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    # 複数ソース由来の record は timestamp が null/非 str になりうる（``None < str`` のソート
    # TypeError で履歴 API 全体が 500 になるのを防ぐ）。比較前に str へ coerce。
    for record in sorted(records, key=lambda item: str(item.get("timestamp") or ""), reverse=True):
        record_id = str(record.get("id"))
        if record_id in seen:
            continue
        seen.add(record_id)
        if search and not _matches_search_text(
            search,
            record.get("title"),
            record.get("details"),
            record.get("org_name"),
            record.get("operation"),
            record.get("entity_type"),
            json.dumps(record.get("metadata", {}), ensure_ascii=False),
        ):
            continue
        deduped.append(record)
        if len(deduped) >= limit:
            break
    return deduped


async def _record_execution_event(
    operation: str,
    title: str,
    *,
    status: str = "success",
    details: str = "",
    org_name: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    route: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = _append_execution_history(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "status": status,
            "title": title,
            "details": details,
            "org_name": org_name,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "route": route,
            "metadata": metadata or {},
        }
    )
    await _updates_hub.broadcast({"type": operation, **record})
    return record


def _resolve_knowledge_path(file_path: str) -> Path:
    full_path = KNOWLEDGE_DIR / file_path
    try:
        resolved = full_path.resolve()
        resolved.relative_to(KNOWLEDGE_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="不正なパスです") from exc

    if resolved.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Markdown ファイルのみ操作できます")
    return resolved


def _format_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _stream_response(generator) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _daemon_paths() -> tuple[Path, Path]:
    platform_home = get_platform_home()
    return platform_home / "daemon.pid", platform_home / "daemon.log"


def _read_daemon_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _is_process_running(pid: int) -> bool:
    # Windows-safe: raw os.kill(pid, 0) reports a recently-exited (reaped) pid as
    # alive on Windows, mis-showing crashed daemons as "running" in the UI.
    from core.runtime.process_utils import pid_alive

    return pid_alive(pid)


def _rate_gate_payload() -> dict[str, Any]:
    """プロセス横断のレート制限ゲート状態（daemon status 表示用）。"""
    from core.runtime.usage_gate import RateLimitGate

    info = RateLimitGate().current()
    if info is None:
        return {"rate_limited": False, "retry_at": None}
    return {
        "rate_limited": True,
        "retry_at": info.reset_at.isoformat() if info.reset_at else None,
        "rate_limit_scope": info.scope,
    }


def _daemon_status_payload() -> dict[str, Any]:
    pid_file, log_file = _daemon_paths()
    pid = _read_daemon_pid(pid_file)
    return {
        **_rate_gate_payload(),
        "running": bool(pid is not None and _is_process_running(pid)),
        "pid": pid,
        "log_path": str(log_file),
    }


def _daemon_action_message(status: str) -> str:
    messages = {
        "started": "デーモンを起動しました。",
        "already_running": "デーモンはすでに起動しています。",
        "stopped": "デーモンを停止しました。",
        "already_stopped": "デーモンはすでに停止しています。",
        "not_running": "デーモンは起動していません。",
    }
    return messages.get(status, "デーモンの操作が完了しました。")


def _init_message(already_initialized: bool, meta_name: str | None) -> str:
    if already_initialized:
        return "プラットフォームはすでに初期化されています。"
    if meta_name:
        return f"プラットフォームを初期化しました。メタ組織: {meta_name}"
    return "プラットフォームを初期化しました。"


def _serialize_generated_proposal(proposal: ImprovementProposal) -> dict[str, Any]:
    return {
        "id": str(proposal.id),
        "priority": proposal.priority,
        "category": proposal.category,
        "title": proposal.title,
        "description": proposal.description,
        "file_path": proposal.file_path,
        "expected_impact": proposal.expected_impact,
        "code_preview": proposal.code_preview,
        "status": proposal.status,
    }


def _goal_record(req: GoalRunRequest, result: Any) -> dict[str, Any]:
    summary = result.summary() if callable(getattr(result, "summary", None)) else str(result)
    return _normalize_goal_history_item(
        {
            "goal_text": req.goal_text,
            "summary": summary,
            "success": result.success,
            "goal_type": result.goal.goal_type,
            "scale": result.goal.scale,
            "organization": result.org_result.organization.name,
            "done_count": result.execution_progress.done_count,
            "total": result.execution_progress.total,
            "failed_count": result.execution_progress.failed_count,
            "achievement_pct": result.verification.achievement_pct,
            "recommendations": result.verification.recommendations,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _stream_error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)


async def _perform_analyze(req: AnalyzeRequest) -> dict[str, Any]:
    from agents.base import AgentTask
    from agents.orchestrator_agent import OrchestratorAgent
    from core.runtime.claude_code import claude_available

    # 実データのみ: 生成バックエンド（claude CLI）が無い時にテンプレートの偽提案を
    # 本物として永続化しない。利用不可なら明示的にエラーを返す。
    if not claude_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "生成バックエンド（claude CLI）が利用できないため、実コード分析を実行できません。"
                "`claude` を導入・ログインしてから再実行してください。"
            ),
        )

    psm = _psm()
    org = psm.load_organization_by_name(req.org_name)
    if not org:
        raise HTTPException(
            status_code=404, detail=f"Organization '{req.org_name}' が見つかりません"
        )

    repo_path = Path(org.target_repo_path) if org.target_repo_path else Path(".")
    # 直接 CodeReviewAgent を生成せず、中央 OrchestratorAgent（=PreTaskOrchestrator）
    # 経由でルーティング・実行する。これによりパターン学習が蓄積される。
    task = AgentTask(
        task_type="code_review",
        description=f"{org.name} のコードレビューと改善提案生成",
        input={"repo_path": str(repo_path), "max_files": req.max_files},
    )

    result = await OrchestratorAgent.create().run(task)
    if not result.success:
        status_code = 422 if result.error and "found" in result.error.lower() else 500
        raise HTTPException(status_code=status_code, detail=result.error)

    sm = psm.get_org_state_manager(org)
    generated_proposals: list[dict[str, Any]] = []
    for suggestion in result.output.get("suggestions", []):
        proposal = ImprovementProposal.from_suggestion(suggestion, review_id=uuid4())
        sm.save_improvement_proposal(proposal)
        serialized = _serialize_generated_proposal(proposal)
        generated_proposals.append(serialized)
        await _record_execution_event(
            "proposal_created",
            proposal.title,
            status="pending",
            details=proposal.description,
            org_name=org.name,
            entity_type="proposal",
            entity_id=str(proposal.id),
            route=f"/proposals?org={quote(org.name)}",
            metadata={"file_path": proposal.file_path, "priority": proposal.priority},
        )

    await _record_execution_event(
        "analysis_completed",
        f"{org.name} の分析が完了しました",
        status="success",
        details=f"{len(generated_proposals)} 件の改善提案を生成しました",
        org_name=org.name,
        entity_type="organization",
        entity_id=str(org.id),
        route="/orgs",
        metadata={
            "files_reviewed": result.output.get("files_reviewed", 0),
            "proposals_generated": len(generated_proposals),
        },
    )

    return {
        "org_name": org.name,
        "files_reviewed": result.output.get("files_reviewed", 0),
        "proposals_generated": len(generated_proposals),
        "generated_proposals": generated_proposals,
    }


async def _perform_goal_run(req: GoalRunRequest, progress_callback: Any = None) -> dict[str, Any]:
    from core.goals.abstract_goal_pipeline import AbstractGoalPipeline

    pipeline = AbstractGoalPipeline(progress_callback=progress_callback)
    result = await pipeline.run(req.goal_text)
    record = _goal_record(req, result)
    _save_goal_history(record)
    await _updates_hub.broadcast(
        {
            "type": "goal_completed",
            "status": "success" if record.get("success", True) else "error",
            "title": record.get("goal") or req.goal_text,
            "details": record.get("result") or record.get("summary") or "",
            "org_name": record.get("org_name") or record.get("organization"),
            "entity_type": "goal",
            "entity_id": record.get("id"),
            "route": "/data",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    return record


def _find_org(org_name: str):
    org = _psm().load_organization_by_name(org_name)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{org_name}' が見つかりません")
    return org


def _generate_pixel_art_svg(seed_text: str, size: int = 8) -> str:
    """組織名から決定論的なピクセルアートSVGを生成する。"""
    h = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    nums = [int(h[i : i + 2], 16) for i in range(0, 64, 2)]

    hue1 = nums[0] * 360 // 256
    hue2 = (hue1 + 120 + nums[1] * 60 // 256) % 360

    def hsl_to_hex(hue: int, saturation: int, lightness: int) -> str:
        red, green, blue = colorsys.hls_to_rgb(hue / 360, lightness / 100, saturation / 100)
        return f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"

    bg_color = "#1e1e2e"
    color1 = hsl_to_hex(hue1, 70, 65)
    color2 = hsl_to_hex(hue2, 60, 55)
    colors = [bg_color, color1, color2]

    half = size // 2
    grid: list[list[int]] = []
    idx = 4
    for _row in range(size):
        row_data: list[int] = []
        for _col in range(half):
            value = nums[idx % len(nums)]
            idx += 1
            if value < 100:
                row_data.append(0)
            elif value < 200:
                row_data.append(1)
            else:
                row_data.append(2)
        grid.append(row_data)

    cell = 4
    total = size * cell
    svg_cells: list[str] = []
    for row in range(size):
        for col in range(half):
            color_index = grid[row][col]
            if color_index == 0:
                continue
            x = col * cell
            y = row * cell
            mirror_x = (size - 1 - col) * cell
            svg_cells.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{colors[color_index]}"/>'
            )
            if col != size - 1 - col:
                svg_cells.append(
                    f'<rect x="{mirror_x}" y="{y}" width="{cell}" height="{cell}" fill="{colors[color_index]}"/>'
                )

    cells_str = "\n  ".join(svg_cells)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {total}" width="{total}" height="{total}">\n'
        f'  <rect width="{total}" height="{total}" fill="{bg_color}" rx="2"/>\n'
        f"  {cells_str}\n"
        "</svg>"
    )


def _pending_proposals_for(org_name: str) -> tuple[Any, Any, list[dict[str, Any]]]:
    psm = _psm()
    org = _find_org(org_name)
    sm = psm.get_org_state_manager(org)
    proposals = sm.get_pending_improvement_proposals(limit=100)
    return psm, sm, proposals


def _find_pending_proposal(org_name: str, proposal_id: str) -> tuple[Any, Any, dict[str, Any]]:
    psm, sm, proposals = _pending_proposals_for(org_name)
    target = next(
        (p for p in proposals if str(p.get("id", "")).startswith(proposal_id)),
        None,
    )
    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"ID '{proposal_id}' に一致する未対応提案が見つかりません",
        )
    return psm, sm, target


def _load_all_proposals() -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    psm = _psm()
    for org in psm.load_organizations():
        sm = psm.get_org_state_manager(org)
        improvements_dir = sm.state_dir / "improvements"
        if not improvements_dir.exists():
            continue
        for path in sorted(improvements_dir.glob("*.json"), reverse=True):
            try:
                proposal = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(proposal, dict):
                continue
            proposal["org_name"] = org.name
            proposals.append(proposal)
    return sorted(
        proposals,
        key=lambda item: str(item.get("last_updated") or item.get("created_at") or ""),
        reverse=True,
    )


def _serialize_org_structure(org: Any) -> list[dict[str, Any]]:
    divisions: list[dict[str, Any]] = []
    for division_index, division in enumerate(org.divisions):
        teams: list[dict[str, Any]] = []
        previous_team_name: str | None = None
        previous_division_name = (
            org.divisions[division_index - 1].name if division_index > 0 else None
        )
        for team in division.teams:
            teams.append(
                {
                    "id": str(team.id),
                    "name": team.name,
                    "mission": team.mission,
                    "depends_on": previous_team_name or previous_division_name,
                    "agents": [
                        {
                            "id": str(agent.id),
                            "name": agent.name,
                            "description": agent.description,
                            "skills": [str(skill) for skill in agent.skills],
                        }
                        for agent in team.agents
                    ],
                }
            )
            previous_team_name = team.name
        divisions.append(
            {
                "id": str(division.id),
                "name": division.name,
                "type": str(
                    division.type.value if hasattr(division.type, "value") else division.type
                ),
                "mission": division.mission,
                "teams": teams,
            }
        )
    return divisions


def _search_results(query: str, limit: int = 20) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    psm = _psm()
    organizations = psm.load_organizations()

    for org in organizations:
        if _matches_search_text(
            query, org.name, org.purpose, org.target_repo_path, org.status.value
        ):
            results.append(
                {
                    "id": f"organization:{org.id}",
                    "type": "organization",
                    "title": org.name,
                    "subtitle": org.purpose,
                    "route": "/orgs",
                    "org_name": org.name,
                    "status": org.status.value,
                    "metadata": {"target_repo_path": org.target_repo_path},
                }
            )
        for division in org.divisions:
            for team in division.teams:
                for agent in team.agents:
                    skills = [str(skill) for skill in agent.skills]
                    if _matches_search_text(
                        query,
                        agent.name,
                        agent.description,
                        *skills,
                        team.name,
                        division.name,
                        org.name,
                    ):
                        results.append(
                            {
                                "id": f"agent:{agent.id}",
                                "type": "agent",
                                "title": agent.name,
                                "subtitle": f"{org.name} / {team.name}",
                                "route": "/agents",
                                "org_name": org.name,
                                "status": None,
                                "metadata": {
                                    "team": team.name,
                                    "division": division.name,
                                    "skills": skills,
                                },
                            }
                        )

    for proposal in _load_all_proposals():
        if _matches_search_text(
            query,
            proposal.get("title"),
            proposal.get("description"),
            proposal.get("file_path"),
            proposal.get("category"),
            proposal.get("org_name"),
            proposal.get("status"),
        ):
            org_name = str(proposal.get("org_name") or "")
            results.append(
                {
                    "id": f"proposal:{proposal.get('id')}",
                    "type": "proposal",
                    "title": str(proposal.get("title") or "改善提案"),
                    "subtitle": str(proposal.get("description") or proposal.get("file_path") or ""),
                    "route": f"/proposals?org={quote(org_name)}",
                    "org_name": org_name or None,
                    "status": proposal.get("status"),
                    "metadata": {
                        "file_path": proposal.get("file_path"),
                        "priority": proposal.get("priority"),
                        "category": proposal.get("category"),
                    },
                }
            )

    for goal in _load_goal_history():
        if _matches_search_text(
            query,
            goal.get("goal"),
            goal.get("goal_text"),
            goal.get("result"),
            goal.get("summary"),
            goal.get("org_name"),
        ):
            results.append(
                {
                    "id": f"goal:{goal.get('id') or hashlib.sha1(json.dumps(goal, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:12]}",
                    "type": "goal",
                    "title": str(goal.get("goal") or goal.get("goal_text") or "Goal"),
                    "subtitle": str(goal.get("result") or goal.get("summary") or ""),
                    "route": "/data",
                    "org_name": goal.get("org_name") or goal.get("organization"),
                    "status": "success" if goal.get("success", True) else "error",
                    "metadata": {"goal_type": goal.get("goal_type"), "scale": goal.get("scale")},
                }
            )

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        result_id = str(result.get("id"))
        if result_id in seen:
            continue
        seen.add(result_id)
        deduped.append(result)
        if len(deduped) >= limit:
            break
    return deduped


def _serialize_agent(defn) -> dict[str, Any]:
    return {
        "name": defn.name,
        "capability_id": defn.capability_id,
        "description": defn.description,
        "skills": list(defn.skills),
        "tools": list(defn.tools),
        "implementation": defn.implementation,
        "behavior": defn.behavior,
        "source_file": defn.source_file,
        "schema_version": getattr(defn, "schema_version", ""),
        "configuration": {
            "response_format": getattr(defn, "response_format", {}),
            "tools": list(getattr(defn, "tools", [])),
            "skills": list(getattr(defn, "skills", [])),
            "behavior": getattr(defn, "behavior", ""),
        },
    }


def _serialize_skill(defn) -> dict[str, Any]:
    return {
        "id": defn.id,
        "name": defn.name,
        "description": defn.description,
        "persona": defn.persona,
        "focus": defn.focus,
        "output_hint": defn.output_hint,
        "tags": list(defn.tags),
        "schema_version": getattr(defn, "schema_version", ""),
    }


def _serialize_org_tree(org: Any) -> list[dict[str, Any]]:
    divisions: list[dict[str, Any]] = []
    for division in getattr(org, "divisions", []):
        divisions.append(
            {
                "id": str(division.id),
                "name": division.name,
                "type": getattr(division.type, "value", division.type),
                "mission": getattr(division, "mission", ""),
                "teams": [
                    {
                        "id": str(team.id),
                        "name": team.name,
                        "division_type": getattr(team.division_type, "value", team.division_type),
                        "mission": getattr(team, "mission", ""),
                        "agents": [
                            {
                                "id": str(agent.id),
                                "name": agent.name,
                                "skills": [
                                    getattr(skill, "value", skill)
                                    for skill in getattr(agent, "skills", [])
                                ],
                                "performance_score": getattr(agent, "performance_score", 0.0),
                                "current_task": getattr(agent, "current_task", None),
                            }
                            for agent in getattr(team, "agents", [])
                        ],
                    }
                    for team in getattr(division, "teams", [])
                ],
            }
        )
    return divisions


def _collect_runtime_agents() -> list[dict[str, Any]]:
    runtime_agents: list[dict[str, Any]] = []
    for org in _psm().load_organizations():
        for division in getattr(org, "divisions", []):
            for team in getattr(division, "teams", []):
                for agent in getattr(team, "agents", []):
                    runtime_agents.append(
                        {
                            "id": str(agent.id),
                            "name": agent.name,
                            "organization": org.name,
                            "division": division.name,
                            "team": team.name,
                            "skills": [
                                getattr(skill, "value", skill)
                                for skill in getattr(agent, "skills", [])
                            ],
                            "status": "running" if getattr(agent, "current_task", None) else "idle",
                            "current_task": getattr(agent, "current_task", None),
                            "proficiency": float(getattr(agent, "performance_score", 0.0)),
                            "configuration": {
                                "organization": org.name,
                                "division": division.name,
                                "team": team.name,
                                "skills": [
                                    getattr(skill, "value", skill)
                                    for skill in getattr(agent, "skills", [])
                                ],
                                "description": getattr(agent, "description", ""),
                                "performance_score": getattr(agent, "performance_score", 0.0),
                                "current_task": getattr(agent, "current_task", None),
                            },
                        }
                    )
    return runtime_agents


def _extract_proposal_diff_text(proposal: dict[str, Any]) -> str:
    for key in ("diff_text", "diff", "patch"):
        value = proposal.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    file_changes = proposal.get("file_changes")
    if isinstance(file_changes, list):
        patches: list[str] = []
        for change in file_changes:
            if not isinstance(change, dict):
                continue
            patch = change.get("patch") or change.get("diff")
            if isinstance(patch, str) and patch.strip():
                patches.append(patch.strip())
        if patches:
            return "\n\n".join(patches)

    return ""


@app.get(
    "/api/platform/status",
    response_model=PlatformStatusResponse,
    tags=["platform"],
    responses={200: {"content": {"application/json": {"example": PLATFORM_STATUS_EXAMPLE}}}},
)
async def api_platform_status() -> Dict[str, Any]:
    """プラットフォーム全体のステータス（指標は実リポジトリ状態から都度計算）"""
    from core.metrics.live_metrics import compute_live_group_metrics, compute_live_org_metrics

    psm = _psm()
    orgs = psm.load_organizations()
    items = []
    for org in orgs:
        sm = psm.get_org_state_manager(org)
        items.append((org, compute_live_org_metrics(org, sm)))

    group = compute_live_group_metrics(items)
    return {
        "group_health_score": group.group_health_score,
        "balance_score": group.balance_score,
        "total_organizations": group.total_organizations,
        "active_organizations": group.active_organizations,
        "weakest_organization": group.weakest_organization,
        "strongest_organization": group.strongest_organization,
        "platform_home": str(psm.platform_home),
        "initialized": psm.is_initialized(),
        "has_llm": _has_llm(),
        **{k: v for k, v in resolve_environment().items() if k in ("environment", "env_label")},
    }


@app.get(
    "/api/daemon/status",
    response_model=DaemonStatusResponse,
    response_model_exclude_none=True,
    tags=["platform"],
    responses={200: {"content": {"application/json": {"example": DAEMON_STATUS_EXAMPLE}}}},
)
async def api_daemon_status() -> Dict[str, Any]:
    return _daemon_status_payload()


@app.post(
    "/api/daemon/start",
    response_model=DaemonStatusResponse,
    response_model_exclude_none=True,
    tags=["platform"],
    responses={200: {"content": {"application/json": {"example": DAEMON_ACTION_EXAMPLE}}}},
)
async def api_daemon_start(req: DaemonStartRequest | None = None) -> Dict[str, Any]:
    from core.runtime.daemon_registry import spawn_daemon

    req = req or DaemonStartRequest()
    result = spawn_daemon(
        "improvement",
        args=[f"--interval={req.interval}", f"--max-files={req.max_files}"],
    )
    status = result["status"]
    if status == "already_running":
        return {
            "status": status,
            "message": _daemon_action_message(status),
            **_daemon_status_payload(),
            "interval": req.interval,
            "max_files": req.max_files,
        }
    return {
        "status": status,
        "message": _daemon_action_message(status),
        "running": True,
        "pid": result["pid"],
        "log_path": result["log_path"],
        "interval": req.interval,
        "max_files": req.max_files,
    }


@app.post(
    "/api/daemon/stop",
    response_model=DaemonStatusResponse,
    response_model_exclude_none=True,
    tags=["platform"],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {**DAEMON_ACTION_EXAMPLE, "status": "stopped", "running": False}
                }
            }
        }
    },
)
async def api_daemon_stop() -> Dict[str, Any]:
    from core.runtime.daemon_registry import stop_daemon

    result = stop_daemon("improvement")
    return {
        "status": result["status"],
        "message": _daemon_action_message(result["status"]),
        "running": False,
        "pid": result["pid"],
        "log_path": result["log_path"],
    }


# --------------------------------------------------------------------------- #
# 統合 daemon API（registry ベース） — 個別 API（/api/daemon, /api/content-daemon）
# は後方互換のため残し、新規利用はこちらを推奨。
# --------------------------------------------------------------------------- #
def _require_daemon(name: str) -> None:
    from core.runtime.daemon_registry import KNOWN_DAEMONS

    if name not in KNOWN_DAEMONS:
        raise HTTPException(status_code=404, detail=f"Daemon '{name}' が見つかりません")


@app.get("/api/daemons/status", tags=["platform"])
async def api_daemons_status() -> Dict[str, Any]:
    """全 daemon の health（pid 生死 × heartbeat 鮮度 × desired state）＋レート制限状態。"""
    from core.runtime.daemon_registry import all_statuses

    return {**_rate_gate_payload(), "daemons": all_statuses()}


@app.get("/api/usage/summary", tags=["platform"])
async def api_usage_summary() -> Dict[str, Any]:
    """実測トークン使用量（5h/7d 窓）＋クォータガバナーの状態。"""
    from core.runtime.quota_governor import QuotaGovernor
    from core.runtime.token_ledger import TokenLedger

    return {
        "usage": TokenLedger().summary(),
        "governor": QuotaGovernor().status(),
        **_rate_gate_payload(),
    }


@app.get("/api/observability/summary", tags=["platform"])
async def api_observability_summary(limit: int = 20) -> Dict[str, Any]:
    """直近トレースのコスト/品質/レイテンシ集計（C1 spans を読むだけ・read-only）。"""
    from core.observability.span import TraceStore

    return TraceStore().summary(limit=max(1, min(200, limit)))


@app.get("/api/observability/traces", tags=["platform"])
async def api_observability_traces(limit: int = 20, trace_id: str | None = None) -> Dict[str, Any]:
    """直近トレース一覧、または trace_id 指定時はその span 詳細（read-only）。"""
    from core.observability.span import TraceStore

    store = TraceStore()
    if trace_id:
        return {"trace_id": trace_id, "spans": [s.to_dict() for s in store.get_trace(trace_id)]}
    return {
        "traces": [t.to_dict() for t in store.recent_traces(limit=max(1, min(200, limit)))],
    }


@app.get("/api/design-styles", tags=["org"])
async def api_list_design_styles() -> List[Dict[str, Any]]:
    """利用可能なデザインスタイル（id/name/description/palette）の一覧。"""
    from core.content.design_style_loader import list_style_summaries

    return list_style_summaries()


@app.get("/api/personas", tags=["org"])
async def api_list_personas() -> List[Dict[str, Any]]:
    """利用可能なペルソナ（id/name/role）の一覧。"""
    from core.intelligence.persona_loader import PersonaLoader

    loader = PersonaLoader()
    out: List[Dict[str, Any]] = []
    for pid in loader.list_personas():
        p = loader.load_persona(pid) or {}
        out.append({"id": pid, "name": p.get("name", pid), "role": p.get("role", "")})
    return out


@app.get("/api/trends", tags=["trends"])
async def api_list_trends(
    limit: int = 50, source: str | None = None, genre: str | None = None, min_score: float = 0.0
) -> List[Dict[str, Any]]:
    """収集済みトレンドをスコア順に返す。"""
    from core.trends.store import TrendStore

    items = TrendStore().list(limit=limit, source=source, genre=genre, min_score=min_score)
    return [i.to_dict() for i in items]


@app.post("/api/trends/collect", tags=["trends"])
async def api_collect_trends() -> Dict[str, Any]:
    """トレンドを今すぐ収集・採点・保存する（手動トリガー）。"""
    from core.trends.runner import collect_and_store

    return await collect_and_store()


@app.post("/api/trends/convert", tags=["trends"])
async def api_convert_trends() -> Dict[str, Any]:
    """高スコアトレンドを承認ゲート付き ContentJob/提案へ変換する。"""
    from core.trends.trend_to_jobs import convert_trends

    return convert_trends()


@app.post("/api/daemons/{name}/start", tags=["platform"])
async def api_daemons_start(name: str, req: DaemonsActionRequest | None = None) -> Dict[str, Any]:
    from core.runtime.daemon_registry import get_spec, spawn_daemon

    _require_daemon(name)
    req = req or DaemonsActionRequest()
    spec = get_spec(name)
    args = [f"--interval={req.interval or spec.default_interval}"]
    if name == "improvement":
        args.append(f"--max-files={req.max_files or 10}")
    if name == "revenue":
        # target>0 で自律経営 cadence（ポートフォリオ提案＋HQ介入）が起動する。
        # CLI（pantheon daemons start revenue --target …）と同じ desired-state に記録され、
        # watchdog/再起動でも復元される。未指定は idle 安全既定（分析ログのみ）。
        args.append(f"--target={req.target if req.target is not None else 0.0}")
        args.append(f"--source-org-name={req.source_org or 'HQ'}")
        args.append(f"--min-reach={req.min_reach if req.min_reach is not None else 0.0}")
    result = spawn_daemon(name, args=args)
    return {"name": name, **result}


@app.post("/api/daemons/{name}/stop", tags=["platform"])
async def api_daemons_stop(name: str) -> Dict[str, Any]:
    from core.runtime.daemon_registry import stop_daemon

    _require_daemon(name)
    result = stop_daemon(name)
    return {"name": name, **result}


# ============================================================
# Content jobs (定期投稿生成) + Content/PDCA daemon
# ============================================================


class ContentJobRequest(ApiRequestModel):
    org_name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="content_brief", max_length=40)
    theme: str = Field(default="", max_length=500)
    interval_seconds: int = Field(default=86400, ge=60, le=60 * 60 * 24 * 30)
    enabled: bool = True
    publish_platform: str = Field(default="", max_length=40)
    publish_mode: str = Field(default="assisted", max_length=20)


class ContentJobUpdateRequest(ApiRequestModel):
    theme: str | None = Field(default=None, max_length=500)
    interval_seconds: int | None = Field(default=None, ge=60, le=60 * 60 * 24 * 30)
    enabled: bool | None = None
    kind: str | None = Field(default=None, max_length=40)
    publish_platform: str | None = Field(default=None, max_length=40)
    publish_mode: str | None = Field(default=None, max_length=20)


class ContentDaemonStartRequest(ApiRequestModel):
    interval: int = Field(default=600, ge=30, le=60 * 60 * 24)


def _content_job_store():
    from core.content.content_jobs import ContentJobStore

    return ContentJobStore(get_platform_home())


def _content_daemon_paths() -> tuple[Path, Path, Path]:
    home = get_platform_home()
    return (
        home / "content_daemon.pid",
        home / "content_daemon.log",
        home / "content_scheduler_state.json",
    )


def _content_daemon_status_payload() -> dict[str, Any]:
    pid_file, log_file, state_file = _content_daemon_paths()
    pid = _read_daemon_pid(pid_file)
    running = bool(pid is not None and _is_process_running(pid))
    state: dict[str, Any] = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
    gate = _rate_gate_payload()
    return {
        "running": running,
        "pid": pid,
        "log_path": str(log_file),
        # scheduler 自身の state とプロセス横断ゲートのどちらかが制限中なら制限中。
        "rate_limited": bool(state.get("rate_limited", False)) or gate["rate_limited"],
        "retry_at": state.get("retry_at") or gate["retry_at"],
        # "status" はアクション系応答（{"status": "started", **payload}）の
        # アクション結果キーと衝突するため、scheduler の状態は別名で返す。
        "scheduler_status": state.get("status"),
        "cycle_count": state.get("cycle_count", 0),
        "interval_seconds": state.get("interval_seconds"),
    }


@app.get("/api/content-jobs", tags=["content"])
async def api_list_content_jobs() -> List[Dict[str, Any]]:
    """定期コンテンツ生成ジョブの一覧。"""
    return [job.to_dict() for job in _content_job_store().list_jobs()]


@app.post("/api/content-jobs", tags=["content"])
async def api_create_content_job(req: ContentJobRequest) -> Dict[str, Any]:
    """定期コンテンツ生成ジョブを作成する（対象は実在の repo 紐づき組織）。"""
    psm = _psm()
    org = psm.load_organization_by_name(req.org_name)
    if org is None:
        raise HTTPException(
            status_code=404, detail=f"Organization '{req.org_name}' が見つかりません"
        )
    if not getattr(org, "target_repo_path", None):
        raise HTTPException(
            status_code=400, detail=f"Organization '{req.org_name}' に repo が未設定です"
        )
    from core.content.content_jobs import ContentJob

    job = ContentJob(
        org_name=req.org_name,
        kind=req.kind,
        theme=req.theme,
        interval_seconds=req.interval_seconds,
        enabled=req.enabled,
        publish_platform=req.publish_platform,
        publish_mode=req.publish_mode,
    )
    _content_job_store().add_job(job)
    return job.to_dict()


@app.patch("/api/content-jobs/{job_id}", tags=["content"])
async def api_update_content_job(job_id: str, req: ContentJobUpdateRequest) -> Dict[str, Any]:
    store = _content_job_store()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    if req.theme is not None:
        job.theme = req.theme
    if req.interval_seconds is not None:
        job.interval_seconds = req.interval_seconds
    if req.enabled is not None:
        job.enabled = req.enabled
    if req.kind is not None:
        job.kind = req.kind
    if req.publish_platform is not None:
        job.publish_platform = req.publish_platform
    if req.publish_mode is not None:
        job.publish_mode = req.publish_mode
    store.update_job(job)
    return job.to_dict()


@app.delete("/api/content-jobs/{job_id}", tags=["content"])
async def api_delete_content_job(job_id: str) -> Dict[str, Any]:
    if not _content_job_store().delete_job(job_id):
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    return {"status": "deleted", "job_id": job_id}


@app.post("/api/content-jobs/{job_id}/run", tags=["content"])
async def api_run_content_job(job_id: str) -> Dict[str, Any]:
    """ジョブを即時実行し、投稿ドラフト（content_asset 提案・人間承認待ち）を生成する。"""
    from core.content.content_runner import run_content_job

    store = _content_job_store()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    result = await run_content_job(job, _psm())
    store.mark_run(job_id, status=result.get("status", "done"), detail=result.get("detail", ""))
    return result


@app.get("/api/content-jobs/health", tags=["content"])
async def api_content_jobs_health() -> Dict[str, Any]:
    """コンテンツ生成ジョブの健全性サマリ（成功率・要対応・滞留の検知）。

    last_status=="generated" を成功とみなし、実行済み（run_count>0）ジョブ中の成功率を出す。
    サイレント失敗（"scheduled" のまま滞留・繰り返しエラー）を一望できる。
    """
    jobs = _content_job_store().list_jobs()
    by_status: Dict[str, int] = {}
    succeeded = ran = 0
    failures: List[Dict[str, Any]] = []
    for j in jobs:
        by_status[j.last_status] = by_status.get(j.last_status, 0) + 1
        if j.run_count > 0:
            ran += 1
            if j.last_status == "generated":
                succeeded += 1
            else:
                failures.append(
                    {
                        "job_id": j.job_id,
                        "org_name": j.org_name,
                        "last_status": j.last_status,
                        "last_detail": j.last_detail,
                        "last_run_at": j.last_run_at,
                    }
                )
    failures.sort(key=lambda f: f.get("last_run_at") or "", reverse=True)
    return {
        "total_jobs": len(jobs),
        "enabled_jobs": sum(1 for j in jobs if j.enabled),
        "jobs_due_now": sum(1 for j in jobs if j.is_due()),
        "total_runs": sum(j.run_count for j in jobs),
        "generation_success_rate": round(succeeded / ran, 4) if ran else None,
        "jobs_by_status": by_status,
        "recent_failures": failures[:5],
    }


@app.get("/api/content-daemon/status", tags=["content"])
async def api_content_daemon_status() -> Dict[str, Any]:
    return _content_daemon_status_payload()


@app.post("/api/content-daemon/start", tags=["content"])
async def api_content_daemon_start(req: ContentDaemonStartRequest | None = None) -> Dict[str, Any]:
    from core.runtime.daemon_registry import spawn_daemon

    req = req or ContentDaemonStartRequest()
    result = spawn_daemon("content", args=[f"--interval={req.interval}"])
    # 注意: "status" はアクション結果。payload 側の scheduler 状態は scheduler_status。
    return {**_content_daemon_status_payload(), "status": result["status"]}


@app.post("/api/content-daemon/stop", tags=["content"])
async def api_content_daemon_stop() -> Dict[str, Any]:
    from core.runtime.daemon_registry import stop_daemon

    result = stop_daemon("content")
    return {**_content_daemon_status_payload(), "status": result["status"]}


@app.get("/api/content-daemon/logs", tags=["content"])
async def api_content_daemon_logs(limit: int = 20) -> List[Dict[str, Any]]:
    from core.content.content_scheduler import ContentScheduler

    return ContentScheduler(get_platform_home()).get_recent_logs(n=max(1, min(limit, 200)))


# ---------- 投稿（publishing）: PublishJob・接続・インボックス・収益メトリクス ----------


def _publish_job_store():
    from core.publishing.publish_jobs import PublishJobStore

    return PublishJobStore(platform_home=get_platform_home())


def _session_store():
    from core.publishing.session import SessionStore

    return SessionStore(platform_home=get_platform_home())


@app.get("/api/publish-jobs", tags=["publishing"])
async def api_list_publish_jobs(
    status: str | None = None, org_name: str | None = None
) -> List[Dict[str, Any]]:
    """投稿ジョブ一覧（任意で status / org_name で絞り込み）。"""
    jobs = _publish_job_store().list_jobs()
    if status:
        jobs = [j for j in jobs if j.status == status]
    if org_name:
        jobs = [j for j in jobs if j.org_name == org_name]
    return [j.to_dict() for j in jobs]


@app.post("/api/publish-jobs/{job_id}/run", tags=["publishing"])
async def api_run_publish_job(job_id: str, dry_run: bool = False) -> Dict[str, Any]:
    """投稿ジョブを実行する。dry_run=true ならプレビューのみ（ジョブ status 不変）。"""
    from core.publishing.runner import run_publish_job

    store = _publish_job_store()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="投稿ジョブが見つかりません")
    if job.status == "handed_off" and not dry_run:
        # 防御の深層化: フロントはボタンを隠すが、API 直叩きでも再ハンドオフ
        # （二重下書き流し込み）を起こさせない。出口は /confirm だけ。
        raise HTTPException(
            status_code=409,
            detail="人間の最終公開待ち（handed_off）のジョブは再実行できません。"
            "公開済みなら確認（confirm）してください",
        )
    result = await run_publish_job(
        job, store=store, platform_home=get_platform_home(), dry_run=dry_run
    )
    if not dry_run:
        handed_off = bool(result.get("ok")) and bool(result.get("handed_off"))
        if handed_off:
            event_type, title_prefix = "publish_handed_off", "下書きを引き渡しました"
        elif result["ok"]:
            event_type, title_prefix = "publish_succeeded", "投稿成功"
        else:
            event_type, title_prefix = "publish_failed", "投稿失敗"
        await _updates_hub.broadcast(
            {
                "type": event_type,
                "status": "success" if result["ok"] else "error",
                "title": f"{title_prefix}: {job.title or job.platform}",
                "details": result.get("url") or result.get("detail") or result.get("error") or "",
                "org_name": job.org_name,
                "entity_type": "publish_job",
                "entity_id": job.job_id,
                "platform": job.platform,
                "route": "/inbox",
            }
        )
    return result


class ConfirmPublishBody(BaseModel):
    """公開確認の任意情報（実際に公開された URL があれば成果に紐づける）。"""

    result_url: str = ""


@app.post("/api/publish-jobs/{job_id}/confirm", tags=["publishing"])
async def api_confirm_publish_job(
    job_id: str, body: Optional[ConfirmPublishBody] = None
) -> Dict[str, Any]:
    """handed_off（人間の最終公開待ち）のジョブを公開済みとして確定する。

    人間がブラウザで実際に公開した後の確認ステップ。ここで初めて published に遷移し、
    成果（posts）が記録される。handed_off 以外の status は 409。
    """
    from core.publishing.runner import confirm_handed_off

    store = _publish_job_store()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="投稿ジョブが見つかりません")
    result = confirm_handed_off(
        job_id,
        store=store,
        platform_home=get_platform_home(),
        result_url=(body.result_url if body else ""),
    )
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=result.get("error") or "確認できません")
    await _updates_hub.broadcast(
        {
            "type": "publish_succeeded",
            "status": "success",
            "title": f"公開を確認: {job.title or job.platform}",
            "details": result.get("url") or "",
            "org_name": job.org_name,
            "entity_type": "publish_job",
            "entity_id": job.job_id,
            "platform": job.platform,
            "route": "/inbox",
        }
    )
    return result


@app.delete("/api/publish-jobs/{job_id}", tags=["publishing"])
async def api_delete_publish_job(job_id: str) -> Dict[str, Any]:
    if not _publish_job_store().delete_job(job_id):
        raise HTTPException(status_code=404, detail="投稿ジョブが見つかりません")
    return {"status": "deleted", "job_id": job_id}


@app.get("/api/publishing/connections", tags=["publishing"])
async def api_list_publishing_connections() -> List[Dict[str, Any]]:
    """各プラットフォームのブラウザセッション接続状態（資格情報は保持しない）。"""
    from dataclasses import asdict

    return [asdict(c) for c in _session_store().list_connections()]


class AutoSendRequest(BaseModel):
    """無人実送信フラグ（PUB-AUTO）の切り替え。"""

    enabled: bool


@app.get("/api/publishing/auto", tags=["publishing"])
async def api_get_publish_auto() -> Dict[str, Any]:
    """無人実送信フラグの状態を返す（PUB-AUTO・既定 OFF＝最終送信は人手 handed_off）。"""
    from core.publishing.auto_gate import auto_send_enabled

    return {"auto_send_enabled": auto_send_enabled(get_platform_home())}


@app.post("/api/publishing/auto", tags=["publishing"])
async def api_set_publish_auto(body: AutoSendRequest) -> Dict[str, Any]:
    """無人実送信フラグを設定する。ON でも実 auto 送信対応アダプタが揃うまで送信はされない。"""
    from core.publishing.auto_gate import set_auto_send_enabled

    value = set_auto_send_enabled(body.enabled, platform_home=get_platform_home())
    return {"ok": True, "auto_send_enabled": value}


# 進行中の手動ログインフロー（platform → asyncio.Task）。同一プラットフォームへの
# 多重起動でヘッドフルブラウザが乱立しないようにする。
_login_tasks: Dict[str, "asyncio.Task[Any]"] = {}


@app.post("/api/publishing/connections/{platform}/login", tags=["publishing"])
async def api_publishing_login(platform: str) -> Dict[str, Any]:
    """手動ログイン接続フローを背景で起動する（ヘッドフルブラウザ）。

    サーバはユーザーの PC 上（既定 127.0.0.1）で動くため、ヘッドフルブラウザを
    そのまま開ける。完了は GET /api/publishing/connections のポーリングで観測する。
    """
    from core.publishing.base import SUPPORTED_PLATFORMS, playwright_available
    from core.publishing.connect import LOGIN_URLS, interactive_login

    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=404, detail=f"未対応のプラットフォーム: {platform}")
    if platform not in LOGIN_URLS:
        return {
            "platform": platform,
            "status": "unsupported",
            "detail": "このプラットフォームは接続フロー未対応です（wordpress は Phase 2 で REST 接続を予定）。",
        }
    if not playwright_available():
        return {
            "platform": platform,
            "status": "unavailable",
            "detail": (
                "Playwright 未導入（または PANTHEON_NO_BROWSER=1）のため接続フローを起動できません。"
                "`pip install playwright && playwright install chromium` で導入できます。"
            ),
        }

    existing = _login_tasks.get(platform)
    if existing is not None and not existing.done():
        return {
            "platform": platform,
            "status": "login_in_progress",
            "detail": "ログインフローは既に進行中です。開いているブラウザでログインしてください。",
        }

    task = asyncio.create_task(interactive_login(platform, session_store=_session_store()))

    def _log_result(t: "asyncio.Task[Any]") -> None:
        try:
            r = t.result()
            logger.info("publishing login %s: ok=%s %s", r.platform, r.ok, r.error or r.detail)
        except asyncio.CancelledError:
            logger.info("publishing login %s: cancelled", platform)
        except Exception:  # noqa: BLE001 — interactive_login は例外を返さない契約だが念のため
            logger.exception("publishing login %s: unexpected failure", platform)
        finally:
            # 完了したフローはレジストリから除く（後続の login で上書きされた場合は触らない）。
            if _login_tasks.get(platform) is t:
                _login_tasks.pop(platform, None)

    task.add_done_callback(_log_result)
    _login_tasks[platform] = task
    return {
        "platform": platform,
        "status": "login_started",
        "detail": "ヘッドフルブラウザを起動しました。開いたウィンドウでログインしてください（完了は接続一覧に反映されます）。",
    }


@app.delete("/api/publishing/connections/{platform}", tags=["publishing"])
async def api_publishing_disconnect(platform: str) -> Dict[str, Any]:
    """セッション state を削除して切断する。"""
    from core.publishing.base import SUPPORTED_PLATFORMS

    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=404, detail=f"未対応のプラットフォーム: {platform}")
    cleared = _session_store().clear(platform)
    return {"platform": platform, "cleared": cleared, "status": "disconnected"}


@app.get("/api/inbox", tags=["inbox"])
async def api_inbox() -> Dict[str, Any]:
    """承認インボックス: 保留中の提案＋handoff＋投稿待ちを 1 つの優先度付きキューに集約する。

    収益インパクト（revenue_impact: 収益化に直結する HQ 提案ほど高い）と優先度で並べ替え、
    収益を動かすアクションを上位に押し上げる（Phase 1 収益駆動の提案キュー）。
    """
    from core.metrics.revenue_intelligence import revenue_impact_rank

    psm = _psm()
    items: List[Dict[str, Any]] = []

    for org in psm.load_organizations():
        try:
            sm = psm.get_org_state_manager(org)
            for p in sm.get_pending_improvement_proposals(limit=50):
                items.append(
                    {
                        "kind": "proposal",
                        "id": str(p.get("id", "")),
                        "org_name": org.name,
                        "title": p.get("title", ""),
                        "category": p.get("category", "general"),
                        "priority": p.get("priority", "medium"),
                        "revenue_impact": revenue_impact_rank(p),
                        "route": f"/proposals?org={quote(org.name)}",
                    }
                )
        except Exception:  # noqa: BLE001 — 1 組織の読み取り失敗で全体を落とさない
            continue

    for h in _handoff_store().list_handoffs(status="pending"):
        hd = _handoff_dict(h)
        items.append(
            {
                "kind": "handoff",
                "id": hd.get("handoff_id", ""),
                "org_name": hd.get("target_org", ""),
                "title": hd.get("title", ""),
                "category": "cross_org_handoff",
                "priority": hd.get("priority", "medium"),
                "revenue_impact": 1,  # 集客→収益化の橋渡し（リーチ→収益の入口）
                "route": "/handoffs",
            }
        )

    # queued（これから投稿）に加え handed_off（人間が公開→確認待ち）も人間アクション
    # 待ちとして集約する（dead end にしない — 確認で初めて published+成果記録）。
    for j in _publish_job_store().list_jobs():
        if j.status not in ("queued", "handed_off"):
            continue
        items.append(
            {
                "kind": "publish",
                "id": j.job_id,
                "org_name": j.org_name,
                "title": j.title or j.platform,
                "category": "external_action",
                "priority": "high",
                "revenue_impact": 1,  # 実投稿＝リーチ獲得（収益の手前の外部アクション）
                "platform": j.platform,
                "scheduled_at": j.scheduled_at,
                "status": j.status,
                "route": "/inbox",
            }
        )

    # 人間専用タスク（open）も「あなたが対応すべきこと」として同じキューに集約する。
    # （承認インボックスを唯一の対応ハブにする — /human-tasks 画面の代替集約・C006）
    for t in _human_task_store().list_tasks("open"):
        items.append(
            {
                "kind": "human_task",
                "id": t.task_id,
                "org_name": t.org_name,
                "title": t.title,
                "category": t.kind,
                "priority": "high",  # 人間アクション待ち＝対応必須
                "revenue_impact": 1,
                "ref": t.ref,
                "created_at": t.created_at,
                "route": "/human-tasks",
            }
        )

    # 収益インパクト → 優先度の順でキューを並べ替え（収益を動かすアクションを上位へ）。
    _priority_rank = {"high": 3, "medium": 2, "low": 1}
    items.sort(
        key=lambda i: (
            i.get("revenue_impact", 0),
            _priority_rank.get(str(i.get("priority", "medium")), 2),
        ),
        reverse=True,
    )

    counts = {
        "proposal": sum(1 for i in items if i["kind"] == "proposal"),
        "handoff": sum(1 for i in items if i["kind"] == "handoff"),
        "publish": sum(1 for i in items if i["kind"] == "publish"),
        "human_task": sum(1 for i in items if i["kind"] == "human_task"),
        "total": len(items),
    }
    return {"items": items, "counts": counts}


@app.get("/api/metrics/revenue", tags=["metrics"])
async def api_revenue_metrics() -> Dict[str, Any]:
    """収益メトリクス: 組織別の reach / revenue / 投稿数と「リーチ有・収益0」検知。"""
    psm = _psm()
    store = _outcome_store()
    orgs_payload: List[Dict[str, Any]] = []
    total_revenue = 0.0
    total_reach = 0.0
    for org in psm.load_organizations():
        summary = store.summary_for_org(org.name)
        posts = summary.by_metric.get("posts", {}).get("sum", 0.0)
        reach = summary.total_reach
        revenue = summary.total_revenue
        total_revenue += revenue
        total_reach += reach
        orgs_payload.append(
            {
                "org_name": org.name,
                "reach": reach,
                "revenue": revenue,
                "posts": posts,
                "reach_but_no_revenue": reach > 0 and revenue == 0,
            }
        )
    return {
        "orgs": orgs_payload,
        "total_revenue": total_revenue,
        "total_reach": total_reach,
    }


@app.get("/api/metrics/efficiency", tags=["metrics"])
async def api_metrics_efficiency() -> Dict[str, Any]:
    """組織別の収益効率（ROI = revenue/reach）とランクを返す。

    どの org がリーチを効率よく収益化しているか/リーチを無駄にしているかを一望できる。
    ``recommend_allocation`` の ROI 計算（決定論）を再利用し、効率ランク（ROI 降順 1 始まり）を付す。
    """
    from core.metrics.portfolio import recommend_allocation

    psm = _psm()
    store = _outcome_store()
    org_stats: List[Dict[str, Any]] = []
    for org in psm.load_organizations():
        if getattr(org, "is_system", False):
            continue
        summary = store.summary_for_org(org.name)
        org_stats.append(
            {
                "org_name": org.name,
                "revenue": summary.total_revenue,
                "reach": summary.total_reach,
                "posts": summary.by_metric.get("posts", {}).get("sum", 0.0),
            }
        )
    alloc = {a["org_name"]: a for a in recommend_allocation(org_stats)}
    # ROI 降順でランク付け（同 ROI は org 名で安定化）。
    ranked = sorted(
        org_stats, key=lambda s: (-alloc.get(s["org_name"], {}).get("roi", 0.0), s["org_name"])
    )
    orgs_payload = [
        {
            "org_name": s["org_name"],
            "revenue": s["revenue"],
            "reach": s["reach"],
            "roi": alloc.get(s["org_name"], {}).get("roi", 0.0),
            "action": alloc.get(s["org_name"], {}).get("action", "grow_audience"),
            "efficiency_rank": rank,
        }
        for rank, s in enumerate(ranked, start=1)
    ]
    return {"orgs": orgs_payload, "count": len(orgs_payload)}


@app.get("/api/metrics/revenue/report", tags=["metrics"])
async def api_revenue_report(
    org_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """収益の月次（YYYY-MM）簡易レポート。``org_name`` 指定で単一 org、省略で全 org 横断。

    ``start_date``/``end_date``（YYYY-MM-DD）で期間を絞れる（期間比較ダッシュボード用）。
    """
    store = _outcome_store()
    by_month = store.revenue_by_month(org_name, start_date=start_date, end_date=end_date)
    return {
        "org_name": org_name,
        "by_month": by_month,
        "total_revenue": sum(by_month.values()),
        "months": list(by_month.keys()),
    }


@app.get("/api/metrics/revenue/intelligence", tags=["metrics"])
async def api_revenue_intelligence(
    org_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """収益インテリジェンス: 月次系列から前月比・トレンド・翌月予測を返す。

    ``start_date``/``end_date``（YYYY-MM-DD）で対象期間を絞り、期間別のトレンド比較を可能にする。
    """
    from core.metrics.revenue_intelligence import analyze_revenue

    store = _outcome_store()
    by_month = store.revenue_by_month(org_name, start_date=start_date, end_date=end_date)
    analysis = analyze_revenue(by_month)
    return {"org_name": org_name, **analysis}


@app.get("/api/metrics/revenue/projection", tags=["metrics"])
async def api_revenue_projection(
    target: float,
    org_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """月次目標 ``target`` への到達射影（現トレンドで何か月か・到達可否・3か月後予測）。

    回帰 run-rate を外挿する決定論計算（LLM 非依存）。「自律経営プラン」の手前で
    「今のペースで目標に届くか／いつ届くか」を一目で示す。
    """
    from core.metrics.revenue_intelligence import project_to_target

    store = _outcome_store()
    by_month = store.revenue_by_month(org_name, start_date=start_date, end_date=end_date)
    projection = project_to_target(by_month, target)
    return {"org_name": org_name, **projection}


@app.get("/api/hq/portfolio", tags=["hq"])
async def api_hq_portfolio() -> Dict[str, Any]:
    """ポートフォリオ資源配分・連携の HQ 提案（収益/リーチから invest/monetize/送客 等を提案）。"""
    from core.hierarchy.portfolio_advisor import build_portfolio_proposals

    psm = _psm()
    store = _outcome_store()
    org_stats: List[Dict[str, Any]] = []
    for org in psm.load_organizations():
        if org.is_system:  # HQ/メタ自身はポートフォリオ配分の対象外
            continue
        summary = store.summary_for_org(org.name)
        org_stats.append(
            {
                "org_name": org.name,
                "revenue": summary.total_revenue,
                "reach": summary.total_reach,
                "posts": summary.by_metric.get("posts", {}).get("sum", 0.0),
            }
        )
    return {"proposals": build_portfolio_proposals(org_stats)}


class BusinessScanRequest(BaseModel):
    """高スコアトレンド → 新規会社候補提案 を起票するスキャンのリクエスト。"""

    min_score: float = 7.0
    max_per_run: int = 5


@app.post("/api/hq/business-proposals/scan", tags=["hq"])
async def api_scan_business_proposals(body: BusinessScanRequest | None = None) -> Dict[str, Any]:
    """高スコアトレンドを新規会社候補提案へ変換し承認キューへ積む（WIRE-B・自動採用しない）。"""
    from core.trends.business_pipeline import scan_business_proposals

    req = body or BusinessScanRequest()
    return scan_business_proposals(min_score=req.min_score, max_per_run=req.max_per_run)


@app.get("/api/hq/business-proposals", tags=["hq"])
async def api_list_business_proposals() -> Dict[str, Any]:
    """承認待ちの新規会社候補提案（category=new_business）を一覧する。"""
    psm = _psm()
    items: List[Dict[str, Any]] = []
    for org in psm.load_organizations():
        try:
            sm = psm.get_org_state_manager(org)
            for p in sm.get_pending_improvement_proposals(limit=50):
                if p.get("category") != "new_business":
                    continue
                items.append(
                    {
                        "id": str(p.get("id", "")),
                        "org_name": org.name,
                        "title": p.get("title", ""),
                        "priority": p.get("priority", "medium"),
                        # 生 dict の expected_impact は null になりうる（``.get(k, "")`` は
                        # null 値存在時に "" でなく None を返す）。型契約 str に揃えて coerce。
                        "expected_impact": p.get("expected_impact") or "",
                        "route": f"/proposals?org={quote(org.name)}",
                    }
                )
        except Exception:  # noqa: BLE001 — 1 組織の読み取り失敗で全体を落とさない
            continue
    return {"items": items, "count": len(items)}


# --------------------------------------------------------------------------- #
# Phase 4: 自律経営（P4.1 目標→計画→提案）/ ジャンル自動発見（P4.2）              #
# --------------------------------------------------------------------------- #


class PortfolioScanRequest(BaseModel):
    """月収益目標に向けたポートフォリオ計画を承認ゲートで起票するリクエスト（P4.1）。"""

    target: float
    source_org_name: str = "HQ"
    org_name: Optional[str] = None
    min_reach: float = 0.0


@app.post("/api/hq/portfolio/scan", tags=["hq"])
async def api_scan_portfolio_plan(body: PortfolioScanRequest) -> Dict[str, Any]:
    """月収益目標→ギャップ→打ち手群 を承認ゲート提案として起票する（P4.1・LLM 非依存）。"""
    from core.hierarchy.portfolio_pipeline import scan_portfolio_proposals

    return scan_portfolio_proposals(
        target=body.target,
        source_org_name=body.source_org_name,
        org_name=body.org_name,
        min_reach=body.min_reach,
    )


@app.get("/api/hq/portfolio/plan", tags=["hq"])
async def api_preview_portfolio_plan(
    target: float, source_org_name: str = "HQ", min_reach: float = 0.0
) -> Dict[str, Any]:
    """月収益目標に対するギャップと計画を返す（**起票しない** プレビュー・P4.1）。

    ``min_reach`` を受けて POST /scan と同じ計画（new_business エスカレーション含む）を返す。
    """
    from core.hierarchy.portfolio_pipeline import preview_portfolio_plan

    return preview_portfolio_plan(
        target=target, source_org_name=source_org_name, min_reach=min_reach
    )


class UntappedGenreScanRequest(BaseModel):
    """未開拓ジャンル発見→新会社候補提案を承認ゲートで起票するリクエスト（P4.2）。"""

    min_score: float = 7.0
    min_evidence: int = 1
    max_per_run: int = 5
    org_name: Optional[str] = None


@app.post("/api/hq/untapped-genres/scan", tags=["hq"])
async def api_scan_untapped_genres(body: UntappedGenreScanRequest | None = None) -> Dict[str, Any]:
    """未開拓ジャンルを発見し新会社候補提案を承認ゲートで起票する（P4.2・LLM 非依存）。"""
    from core.trends.untapped_genre import scan_untapped_genre_proposals

    req = body or UntappedGenreScanRequest()
    return scan_untapped_genre_proposals(
        min_score=req.min_score,
        min_evidence=req.min_evidence,
        max_per_run=req.max_per_run,
        org_name=req.org_name,
    )


@app.get("/api/hq/untapped-genres", tags=["hq"])
async def api_list_untapped_genres(min_score: float = 7.0, min_evidence: int = 1) -> Dict[str, Any]:
    """未開拓ジャンルの一覧（証拠件数・最高スコア付き）を返す（**起票しない** プレビュー・P4.2）。"""
    from core.trends.store import TrendStore
    from core.trends.untapped_genre import (
        _covered_genres,
        enumerate_genre_evidence,
        find_untapped_genres,
    )

    home = get_platform_home()
    evidence = enumerate_genre_evidence(TrendStore(home), min_score=min_score)
    covered = _covered_genres(_psm())
    untapped = find_untapped_genres(
        evidence, covered, min_evidence=min_evidence, min_score=min_score
    )
    items = [
        {
            "genre": g,
            "count": int(evidence[g]["count"]),
            "max_score": float(evidence[g]["max_score"]),
            "top_title": getattr(evidence[g]["top_trend"], "title", ""),
        }
        for g in untapped
    ]
    return {"items": items, "covered": sorted(covered), "count": len(items)}


# --------------------------------------------------------------------------- #
# Plugins / Marketplace（2階層プラグイン: 会社プラグイン / 事業部プラグイン）        #
# --------------------------------------------------------------------------- #


class DivisionInstallRequest(BaseModel):
    """既存 Organization に事業部プラグインを追加するリクエスト。"""

    plugin_id: str


@app.get("/api/division-plugins", tags=["plugins"])
async def api_list_division_plugins() -> Dict[str, Any]:
    """事業部プラグインのカタログ（既存 org に追加できる Division 定義）。"""
    from core.orchestration.division_plugins import load_division_plugins

    return {"plugins": load_division_plugins()}


@app.get("/api/company-plugins", tags=["plugins"])
async def api_list_company_plugins() -> Dict[str, Any]:
    """install できる会社プラグイン（manifest）の一覧。

    ``/api/company-plugins/{id}/install`` で起動できる id と一致させる（list したものが
    install できる）。リッチな manifest 全文は ``/api/company-plugin-manifests`` でも取得可能。
    """
    from core.orchestration.company_plugins import load_company_plugin_manifests

    return {"plugins": load_company_plugin_manifests()}


@app.post("/api/organizations/{org_name}/divisions", tags=["plugins"])
async def api_install_division(org_name: str, body: DivisionInstallRequest) -> Dict[str, Any]:
    """事業部プラグインを既存 Organization に追加する（install → add_division → save）。"""
    from core.orchestration.division_plugins import add_division_plugin

    psm = _psm()
    org = psm.load_organization_by_name(org_name)
    if org is None:
        raise HTTPException(status_code=404, detail=f"Organization '{org_name}' が見つかりません")
    try:
        division = add_division_plugin(org, body.plugin_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    psm.save_organization(org)
    return {
        "ok": True,
        "org_name": org.name,
        "division": {
            "name": division.name,
            "type": division.type.value,
            "teams": [t.name for t in division.teams],
            "agents": [a.name for t in division.teams for a in t.agents],
        },
        "division_count": len(org.divisions),
    }


class CompanyInstallRequest(BaseModel):
    """会社プラグインを install して完全な Organization を起動するリクエスト。"""

    name: str = ""  # 省略時は manifest の label
    repo_path: str = ""  # 省略時は workspaces_root 配下に自動


@app.get("/api/company-plugin-manifests", tags=["plugins"])
async def api_list_company_plugin_manifests() -> Dict[str, Any]:
    """会社プラグイン manifest 一覧（初期KPI/週次レビュー/Humanタスク/事業部を含む正式定義）。"""
    from core.orchestration.company_plugins import load_company_plugin_manifests

    return {"manifests": load_company_plugin_manifests()}


@app.post("/api/company-plugins/{plugin_id}/install", tags=["plugins"])
async def api_install_company_plugin(plugin_id: str, body: CompanyInstallRequest) -> Dict[str, Any]:
    """会社プラグイン manifest から完全な Organization を起動する（事業部・Humanタスク seed 込み）。"""
    from core.orchestration.company_plugins import install_company_plugin

    try:
        return install_company_plugin(
            plugin_id,
            psm=_psm(),
            name=body.name or None,
            repo_path=body.repo_path or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/init",
    response_model=PlatformInitResponse,
    tags=["platform"],
    responses={200: {"content": {"application/json": {"example": INIT_RESPONSE_EXAMPLE}}}},
)
async def api_init_platform() -> Dict[str, Any]:
    bootstrap = globals().get("bootstrap_platform")
    if bootstrap is None:
        from core.bootstrap import bootstrap_platform as bootstrap

    already_initialized = _psm().is_initialized()
    psm = bootstrap()
    meta_id = psm.load_platform_config().get("meta_improvement_org_id")
    meta_name = None
    if meta_id:
        meta = psm.load_organization_by_id(meta_id)
        meta_name = meta.name if meta else None
    status = "already_initialized" if already_initialized else "initialized"
    return {
        "status": status,
        "message": _init_message(already_initialized, meta_name),
        "platform_home": str(psm.platform_home),
        "meta_improvement_org": meta_name,
        "initialized": psm.is_initialized(),
    }


@app.post("/api/welcome")
async def api_create_welcome_data() -> Dict[str, Any]:
    """サンプル組織の自動生成は廃止（実データのみ）。

    以前は 'Sample Organization'（Pantheon 自身の repo を指す）をデモ用に作成していたが、
    GUI には実ワークスペースのみを表示する方針のため、何も作成せず案内を返す。
    """
    return {
        "created": [],
        "skipped": [],
        "message": (
            "サンプル組織の自動生成は廃止しました。実際の git リポジトリ（ワークスペース）を"
            "指定して組織を作成するか、`pantheon org scan` で既存リポジトリを登録してください。"
        ),
    }


@app.get("/api/tasks")
async def api_list_tasks(
    org_name: str | None = None, status: str | None = None, limit: int = 50
) -> Dict[str, Any]:
    """タスクキューの一覧を返す"""
    queue = _task_queue()
    tasks = queue.list_tasks(org_name=org_name, status=status, limit=limit)
    all_tasks = queue.list_tasks(limit=None)
    stats = {
        "total": len(all_tasks),
        "pending": sum(1 for task in all_tasks if task["status"] == "pending"),
        "running": sum(1 for task in all_tasks if task["status"] == "running"),
        "done": sum(1 for task in all_tasks if task["status"] == "done"),
        "failed": sum(1 for task in all_tasks if task["status"] == "failed"),
    }
    return {"tasks": tasks, "stats": stats}


@app.post("/api/tasks")
async def api_queue_task(body: TaskQueueRequest) -> Dict[str, Any]:
    """タスクをキューに追加する"""
    queue = _task_queue()
    task = queue.add_task(
        task_type=body.task_type,
        org_name=body.org_name,
        description=body.description,
        payload=body.payload,
        priority=body.priority,
    )
    await _record_execution_event(
        "task_queued",
        body.description,
        status="pending",
        details=f"{body.task_type} task queued",
        org_name=body.org_name,
        entity_type="task",
        entity_id=str(task.get("id")),
        route="/dashboard",
        metadata={"task_type": body.task_type, "priority": body.priority},
    )
    return task


@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: str) -> Dict[str, Any]:
    """タスクの詳細を返す"""
    queue = _task_queue()
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    return task


@app.delete("/api/tasks/{task_id}")
async def api_cancel_task(task_id: str) -> Dict[str, Any]:
    """タスクをキャンセルする"""
    queue = _task_queue()
    task = queue.get_task(task_id)
    # 不在は 404（姉妹の GET /api/tasks/{id} と同セマンティクス）。cancel_task は「不在」と
    # 「PENDING でない（実行中/完了済）」の両方で False を返すため、先に不在を 404 で切り分け、
    # 400 は「存在するがキャンセル不可」だけに絞る（誤って 400 を返さない REST 整合）。
    if task is None:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    if not queue.cancel_task(task_id):
        raise HTTPException(
            status_code=400, detail="タスクをキャンセルできません（実行中または完了済み）"
        )
    # 上の 404 ガードで task は非 None 確定（`if task else` の旧フォールバックは不要）。
    await _record_execution_event(
        "task_cancelled",
        str(task.get("description") or "Task cancelled"),
        status="success",
        details="Task cancelled",
        org_name=task.get("org_name"),
        entity_type="task",
        entity_id=task_id,
        route="/dashboard",
        metadata={"task_type": task.get("type")},
    )
    return {"status": "cancelled", "task_id": task_id}


# --------------------------------------------------------------------------- #
# Sessions — wmux/headless agent orchestration (AI operation dashboard)         #
# --------------------------------------------------------------------------- #
def _session_orchestrator(prefer: str | None = None):
    from core.runtime.session_orchestrator import SessionOrchestrator

    return SessionOrchestrator(repo_root=PROJECT_ROOT, prefer=prefer)


class SessionAgentRequest(ApiRequestModel):
    agent_id: str = Field(max_length=120)
    title: str = Field(max_length=120)
    prompt: str = Field(max_length=20000)
    system_prompt: str | None = Field(default=None, max_length=20000)
    model: str | None = Field(default=None, max_length=120)
    role: str = Field(default="agent", max_length=64)


class SessionStartRequest(ApiRequestModel):
    name: str = Field(max_length=120)
    prefer: Literal["wmux", "cmux", "headless"] | None = None
    agents: List[SessionAgentRequest] = Field(default_factory=list)


@app.get("/api/sessions", tags=["sessions"])
async def api_list_sessions() -> Dict[str, Any]:
    """All Pantheon sessions (session = workspace group, agent = surface/tab)."""
    orch = _session_orchestrator()
    sessions = [rec.to_dict() for rec in orch.list_sessions()]
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/api/dashboard/orchestra", tags=["dashboard"])
async def api_dashboard_orchestra() -> Dict[str, Any]:
    """オーケストラ可視化用の集約。

    実行中セッション × エージェント（surface）のライブツリーと、組織横断 handoff
    フライホイール（集客→販売→収益化）を 1 レスポンスにまとめる。Dashboard が
    ``/ws/updates`` の session 系イベントを購読してこれを再取得する。
    """
    orch = _session_orchestrator()
    sessions = await asyncio.to_thread(orch.list_sessions)
    active_states = {"running", "rate_limited"}
    session_views: List[Dict[str, Any]] = []
    for rec in sessions:
        session_views.append(
            {
                "id": rec.id,
                "name": rec.name,
                "status": rec.status,
                "driver": rec.driver,
                "agents": [
                    {
                        "agent_id": s.get("agent_id"),
                        "title": s.get("title"),
                        "role": s.get("role"),
                        "status": s.get("status"),
                        "exit_code": s.get("exit_code"),
                    }
                    for s in rec.surfaces
                ],
            }
        )

    handoffs: List[Dict[str, Any]] = []
    try:
        for h in _handoff_store().list_handoffs():
            handoffs.append(
                {
                    "id": h.handoff_id,
                    "source": h.source_org,
                    "target": h.target_org,
                    "kind": h.kind,
                    "status": h.status,
                    "title": h.title,
                    "priority": h.priority,
                }
            )
    except Exception:  # noqa: BLE001 - handoff 未設定でもオーケストラは表示する
        logger.debug("orchestra: handoff load failed", exc_info=True)

    agents_total = sum(len(s["agents"]) for s in session_views)
    return {
        "sessions": session_views,
        "handoffs": handoffs,
        "counts": {
            "sessions": len(session_views),
            "active_sessions": sum(1 for s in session_views if s["status"] in active_states),
            "agents": agents_total,
            "handoffs": len(handoffs),
            "pending_handoffs": sum(1 for h in handoffs if h["status"] == "pending"),
        },
    }


@app.get("/api/sessions/runtime", tags=["sessions"])
async def api_sessions_runtime() -> Dict[str, Any]:
    """Live runtime status: claude CLI + multiplexer (wmux/cmux/headless)."""
    from core.runtime.claude_code import claude_available, claude_binary
    from core.runtime.multiplexer import get_driver
    from core.runtime.multiplexer.wmux_rpc import (
        WmuxClient,
        WmuxNotConfirmedError,
        is_wmux_running,
    )

    wmux_state = "not-running"
    if is_wmux_running():
        try:
            WmuxClient().verify()
            wmux_state = "connected"
        except WmuxNotConfirmedError:
            wmux_state = "awaiting-approval"
        except Exception:
            wmux_state = "error"
    try:
        driver_name = get_driver().name
    except Exception:
        driver_name = "headless"
    return {
        "claude": {"available": claude_available(), "binary": claude_binary()},
        "wmux": {"running": is_wmux_running(), "state": wmux_state},
        "driver": driver_name,
    }


@app.get("/api/sessions/{session_id}", tags=["sessions"])
async def api_get_session(session_id: str) -> Dict[str, Any]:
    orch = _session_orchestrator()
    rec = orch.poll_session(session_id) or orch.get_session(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    return rec.to_dict()


@app.get("/api/sessions/{session_id}/agents/{agent_id}/log", tags=["sessions"])
async def api_get_session_agent_log(
    session_id: str, agent_id: str, tail: int = 8000
) -> Dict[str, Any]:
    orch = _session_orchestrator()
    rec = orch.get_session(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    return {
        "session_id": session_id,
        "agent_id": agent_id,
        "log": orch.agent_log(session_id, agent_id, tail=tail),
    }


@app.post("/api/sessions", tags=["sessions"])
async def api_start_session(body: SessionStartRequest) -> Dict[str, Any]:
    from core.runtime.session_orchestrator import AgentTask

    # デモ用のダミーエージェント（greeter/summarizer）生成は廃止。実セッションは
    # 明示的なエージェント定義、または /analyze・/goal（wmux）から起動する。
    if not body.agents:
        raise HTTPException(
            status_code=400,
            detail="agents を1件以上指定してください。実作業は /analyze・/goal から起動します。",
        )
    orch = _session_orchestrator(prefer=body.prefer)
    tasks = [
        AgentTask(
            agent_id=a.agent_id,
            title=a.title,
            prompt=a.prompt,
            system_prompt=a.system_prompt,
            model=a.model,
            role=a.role,
        )
        for a in body.agents
    ]
    rec = await asyncio.to_thread(orch.start_session, body.name, tasks)
    await _updates_hub.broadcast(
        {
            "type": "session_started",
            "session_id": rec.id,
            "name": rec.name,
            "driver": rec.driver,
            "agents": len(rec.surfaces),
        }
    )
    return rec.to_dict()


@app.post("/api/sessions/{session_id}/stop", tags=["sessions"])
async def api_stop_session(session_id: str) -> Dict[str, Any]:
    orch = _session_orchestrator()
    rec = await asyncio.to_thread(orch.stop_session, session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    await _updates_hub.broadcast({"type": "session_stopped", "session_id": session_id})
    return rec.to_dict()


@app.post("/api/sessions/{session_id}/resume", tags=["sessions"])
async def api_resume_session(session_id: str, force: bool = False) -> Dict[str, Any]:
    """Resume agents that hit a Claude usage limit (auto when the window reopens)."""
    orch = _session_orchestrator()
    rec = await asyncio.to_thread(orch.resume_session, session_id, force=force)
    if rec is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    await _updates_hub.broadcast({"type": "session_resumed", "session_id": session_id})
    return rec.to_dict()


class SettingsUpdateRequest(ApiRequestModel):
    llm_provider: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    llm_model: str | None = Field(default=None, max_length=120)
    anthropic_api_key: str | None = Field(default=None, max_length=512)
    openai_api_key: str | None = Field(default=None, max_length=512)
    groq_api_key: str | None = Field(default=None, max_length=512)
    github_models_api_key: str | None = Field(default=None, max_length=512)
    gemini_api_key: str | None = Field(default=None, max_length=512)
    daemon_interval: int | None = Field(default=None, ge=1)
    daemon_max_files: int | None = Field(default=None, ge=1, le=1000)
    model_configurations: dict[str, Any] | None = None
    prompt_templates: dict[str, str] | None = None
    policy_rules: dict[str, Any] | None = None
    # SET-EXPOSE: トークンクォータ上限・通知設定をアプリ設定から変更可能にする（§4 P2-5/P3-12）。
    token_quota: dict[str, Any] | None = None
    notification_settings: dict[str, Any] | None = None


@app.get(
    "/api/settings",
    response_model=SettingsResponse,
    tags=["settings"],
    responses={200: {"content": {"application/json": {"example": SETTINGS_RESPONSE_EXAMPLE}}}},
)
async def api_get_settings() -> Dict[str, Any]:
    """現在の GUI 設定を返す（APIキーはマスク表示）"""
    s = _load_gui_settings()
    return {
        "llm_provider": s.get("llm_provider", "anthropic"),
        "llm_model": s.get("llm_model", "claude-3-5-sonnet-20241022"),
        "anthropic_api_key_masked": _mask_key(
            s.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")
        ),
        "openai_api_key_masked": _mask_key(
            s.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")
        ),
        "groq_api_key_masked": _mask_key(s.get("groq_api_key") or os.getenv("GROQ_API_KEY", "")),
        "github_models_api_key_masked": _mask_key(
            s.get("github_models_api_key") or os.getenv("GITHUB_TOKEN", "")
        ),
        "gemini_api_key_masked": _mask_key(
            s.get("gemini_api_key") or os.getenv("GOOGLE_API_KEY", "")
        ),
        "anthropic_api_key_set": bool(s.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY")),
        "openai_api_key_set": bool(s.get("openai_api_key") or os.getenv("OPENAI_API_KEY")),
        "groq_api_key_set": bool(s.get("groq_api_key") or os.getenv("GROQ_API_KEY")),
        "github_models_api_key_set": bool(
            s.get("github_models_api_key") or os.getenv("GITHUB_TOKEN")
        ),
        "gemini_api_key_set": bool(s.get("gemini_api_key") or os.getenv("GOOGLE_API_KEY")),
        "daemon_interval": s.get("daemon_interval", 3600),
        "daemon_max_files": s.get("daemon_max_files", 10),
        "model_configurations": s.get(
            "model_configurations", deepcopy(DEFAULT_MODEL_CONFIGURATIONS)
        ),
        "prompt_templates": s.get("prompt_templates", deepcopy(DEFAULT_PROMPT_TEMPLATES)),
        "policy_rules": s.get("policy_rules", deepcopy(DEFAULT_POLICY)),
        "token_quota": _current_token_quota(),
        "notification_settings": _notification_center().get_settings(),
        "settings_file": str(_settings_file()),
        "has_llm": _has_llm(s),
    }


def _current_token_quota() -> Dict[str, Any]:
    """現在のトークンクォータ上限（token_quota.yaml）を dict で返す（SET-EXPOSE）。"""
    from core.runtime.quota_governor import load_rules

    rules = load_rules()
    return {
        "window_hours": rules.window_hours,
        "soft_limit_tokens": rules.soft_limit_tokens,
        "hard_limit_tokens": rules.hard_limit_tokens,
    }


@app.get("/api/storage/info")
async def get_storage_info() -> Dict[str, Any]:
    """~/.pantheon/ 配下の永続化データ情報を返す"""
    platform_home = get_platform_home()

    def dir_info(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {"exists": False, "file_count": 0, "size_bytes": 0, "last_modified": None}

        files = list(path.rglob("*")) if path.is_dir() else [path]
        file_paths = [file_path for file_path in files if file_path.is_file()]

        size_bytes = 0
        modified_times: list[float] = []
        for file_path in file_paths:
            try:
                stat = file_path.stat()
            except OSError:
                continue
            size_bytes += stat.st_size
            modified_times.append(stat.st_mtime)

        last_modified = max(modified_times) if modified_times else None
        return {
            "exists": True,
            "file_count": len(file_paths),
            "size_bytes": size_bytes,
            "last_modified": datetime.fromtimestamp(last_modified, tz=timezone.utc).isoformat()
            if last_modified
            else None,
        }

    return {
        "platform_home": str(platform_home),
        "note": "サーバーを再起動しても以下のデータはすべて保持されます",
        "storage": {
            "settings": {
                "label": "GUI設定（LLMプロバイダー・APIキー等）",
                "path": str(_settings_file()),
                **dir_info(_settings_file()),
            },
            "organizations": {
                "label": "組織定義",
                "path": str(platform_home / "organizations"),
                **dir_info(platform_home / "organizations"),
            },
            "chat_sessions": {
                "label": "チャットセッション履歴",
                "path": str(_chat_sessions_dir()),
                **dir_info(_chat_sessions_dir()),
            },
            "task_queue": {
                "label": "タスクキュー",
                "path": str(platform_home / "task_queue.json"),
                **dir_info(platform_home / "task_queue.json"),
            },
            "goal_history": {
                "label": "ゴール実行履歴",
                "path": str(platform_home / "goal_history.json"),
                **dir_info(platform_home / "goal_history.json"),
            },
            "knowledge": {
                "label": "ナレッジファイル",
                "path": str(KNOWLEDGE_DIR),
                **dir_info(KNOWLEDGE_DIR),
            },
        },
    }


@app.put("/api/settings")
async def api_update_settings(req: SettingsUpdateRequest) -> Dict[str, Any]:
    """GUI 設定を保存し、実行中の環境変数にも即時反映する"""
    s = _load_gui_settings()

    if req.llm_provider is not None:
        s["llm_provider"] = req.llm_provider
        os.environ["PANTHEON_DEFAULT_LLM_PROVIDER"] = req.llm_provider
    if req.llm_model is not None:
        s["llm_model"] = req.llm_model
        os.environ["PANTHEON_DEFAULT_MODEL"] = req.llm_model
    if req.anthropic_api_key is not None and req.anthropic_api_key != "":
        s["anthropic_api_key"] = req.anthropic_api_key
        os.environ["ANTHROPIC_API_KEY"] = req.anthropic_api_key
    if req.openai_api_key is not None and req.openai_api_key != "":
        s["openai_api_key"] = req.openai_api_key
        os.environ["OPENAI_API_KEY"] = req.openai_api_key
    if req.groq_api_key is not None and req.groq_api_key != "":
        s["groq_api_key"] = req.groq_api_key
        os.environ["GROQ_API_KEY"] = req.groq_api_key
    if req.github_models_api_key is not None and req.github_models_api_key != "":
        s["github_models_api_key"] = req.github_models_api_key
        os.environ["GITHUB_TOKEN"] = req.github_models_api_key
    if req.gemini_api_key is not None and req.gemini_api_key != "":
        s["gemini_api_key"] = req.gemini_api_key
        os.environ["GOOGLE_API_KEY"] = req.gemini_api_key
    if req.daemon_interval is not None:
        s["daemon_interval"] = req.daemon_interval
    if req.daemon_max_files is not None:
        s["daemon_max_files"] = req.daemon_max_files
    if req.model_configurations is not None:
        s["model_configurations"] = req.model_configurations
    if req.prompt_templates is not None:
        s["prompt_templates"] = req.prompt_templates
    if req.policy_rules is not None:
        s["policy_rules"] = req.policy_rules

    _save_gui_settings(s)

    # SET-EXPOSE: トークンクォータ上限は token_quota.yaml へ、通知設定は通知センターへ反映する
    # （GUI 設定ファイルではなく各サブシステムの正準ストアに書く）。
    if req.token_quota is not None:
        from core.runtime.quota_governor import save_rules

        tq = req.token_quota
        save_rules(
            window_hours=tq.get("window_hours"),
            soft_limit_tokens=tq.get("soft_limit_tokens"),
            hard_limit_tokens=tq.get("hard_limit_tokens"),
        )
    if req.notification_settings is not None:
        _notification_center().update_settings(req.notification_settings)

    return {"status": "saved", "has_llm": _has_llm(s)}


#: Claude model ids the local Claude Code CLI can target (Pantheon is
#: Claude-Code-only; there are no hosted-provider model lists).
CLAUDE_MODELS = [
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]


@app.get(
    "/api/providers/{provider}/models",
    response_model=ProviderModelsResponse,
    tags=["settings"],
)
async def get_provider_models(provider: str) -> Dict[str, Any]:
    """Pantheon runs exclusively through the local Claude Code CLI, so there are
    no hosted-provider model lists. Return the Claude models the CLI can target."""
    from core.runtime.claude_code import claude_available

    models = list(CLAUDE_MODELS)
    default = os.getenv("PANTHEON_DEFAULT_MODEL")
    if default and default not in models:
        models.insert(0, default)
    return {
        "provider": "claude_code",
        "models": models,
        "source": "claude-code" if claude_available() else "unavailable",
    }


@app.get("/api/organizations")
async def api_list_organizations() -> List[Dict[str, Any]]:
    """Organization 一覧（指標は実リポジトリ状態から都度計算）"""
    from core.metrics.live_metrics import compute_live_org_metrics

    psm = _psm()
    orgs = psm.load_organizations()
    result = []
    for org in orgs:
        sm = psm.get_org_state_manager(org)
        live = compute_live_org_metrics(org, sm)
        result.append(
            {
                "id": str(org.id),
                "name": org.name,
                "purpose": org.purpose,
                "target_repo_path": org.target_repo_path,
                "management_mode": org.management_mode,
                "workspace_path": org.workspace_path,
                "initial_kpis": list(org.initial_kpis),
                "status": org.status.value,
                "health_score": live.health_score,
                "autonomy_score": live.autonomy_score,
                "improvement_velocity": live.improvement_velocity,
                "total_agents": len(org.get_all_agents()),
                "pending_proposals": live.pending_proposals,
                "last_active": org.last_active.isoformat(),
                "is_system": org.is_system,
                "icon_data": org.icon_data,
            }
        )
    return result


def _workspace_root(psm) -> str:
    """workspace の親フォルダを決める（設定 → platform_home/workspaces フォールバック・WS-1）。"""
    from pathlib import Path

    return psm.get_workspaces_root() or str(Path(psm.platform_home) / "workspaces")


@app.get("/api/organizations/{org_name}/migration-plan", tags=["workspace"])
async def api_org_migration_plan(org_name: str) -> Dict[str, Any]:
    """repo→workspace 移行の計画を返す（副作用なし・WS-1）。"""
    from core.orchestration.org_migration import plan_repo_to_workspace_migration

    psm = _psm()
    org = psm.load_organization_by_name(org_name)
    if org is None:
        raise HTTPException(status_code=404, detail=f"Organization '{org_name}' が見つかりません")
    return plan_repo_to_workspace_migration(org, workspace_root=_workspace_root(psm))


@app.post("/api/organizations/{org_name}/migrate-to-workspace", tags=["workspace"])
async def api_org_migrate_to_workspace(org_name: str) -> Dict[str, Any]:
    """repo 紐付き組織を workspace モード（git 不要）へ移行して保存する（WS-1・冪等）。"""
    from core.orchestration.org_migration import (
        migrate_repo_org_to_workspace,
        plan_repo_to_workspace_migration,
    )

    psm = _psm()
    org = psm.load_organization_by_name(org_name)
    if org is None:
        raise HTTPException(status_code=404, detail=f"Organization '{org_name}' が見つかりません")

    workspace_root = _workspace_root(psm)
    plan = plan_repo_to_workspace_migration(org, workspace_root=workspace_root)
    already = plan["already_workspace"]
    if not already:
        migrate_repo_org_to_workspace(org, workspace_root=workspace_root)
        psm.save_organization(org)
    return {
        "ok": True,
        "org_name": org.name,
        "already_workspace": already,
        "management_mode": org.management_mode,
        "workspace_path": org.workspace_path,
        "from_repo": org.target_repo_path,
        "data_location": org.data_location,
    }


@app.post("/api/organizations")
async def api_create_organization(req: OrgCreateRequest) -> Dict[str, Any]:
    """新しい Organization を登録する"""
    from core.bootstrap import bootstrap_platform
    from core.org_service import create_org

    psm = bootstrap_platform()
    existing = psm.load_organization_by_name(req.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Organization '{req.name}' はすでに存在します")

    # CLI/エージェントと同一の単一経路（OrgService）を通す。GUI でも isolation を第一級に扱う。
    org = create_org(
        req.name,
        req.purpose,
        isolation_level=req.isolation_level,
        allowed_path_scope=list(req.allowed_path_scope or []),
        target_repo_path=req.target_repo_path,
        psm=psm,
    )
    await _record_execution_event(
        "organization_created",
        f"{org.name} を作成しました",
        org_name=org.name,
        entity_type="organization",
        entity_id=str(org.id),
        route="/orgs",
        metadata={"target_repo_path": org.target_repo_path},
    )

    return {
        "id": str(org.id),
        "name": org.name,
        "purpose": org.purpose,
        "target_repo_path": org.target_repo_path,
        "status": "created",
    }


@app.delete("/api/organizations/{org_name}")
async def api_delete_organization(org_name: str) -> Dict[str, Any]:
    """Organization を削除する"""
    psm = _psm()
    org = psm.load_organization_by_name(org_name)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{org_name}' が見つかりません")
    if org.is_system:
        raise HTTPException(status_code=403, detail=f"システム組織「{org_name}」は削除できません。")
    psm.remove_organization(str(org.id))
    await _record_execution_event(
        "organization_deleted",
        f"{org_name} を削除しました",
        org_name=org_name,
        entity_type="organization",
        entity_id=str(org.id),
        route="/orgs",
    )
    return {"status": "deleted", "name": org_name}


class OrgUpdateRequest(ApiRequestModel):
    purpose: str | None = Field(default=None, max_length=2000)
    target_repo_path: str | None = Field(default=None, max_length=4096)

    @field_validator("target_repo_path")
    @classmethod
    def validate_target_repo_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_request_path(value, "target_repo_path", allow_empty=False)


@app.get("/api/organizations/{org_name}")
async def api_get_organization(org_name: str) -> Dict[str, Any]:
    """Organization の詳細を返す（指標は実リポジトリ状態から都度計算）"""
    from core.metrics.live_metrics import compute_live_org_metrics

    psm = _psm()
    org = psm.load_organization_by_name(org_name)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{org_name}' が見つかりません")

    sm = psm.get_org_state_manager(org)
    live = compute_live_org_metrics(org, sm)
    pending = live.pending_proposals
    agents = [
        {
            "id": str(a.id),
            "name": a.name,
            "capability_id": getattr(a, "capability_id", a.name),
            "skills": getattr(a, "skills", []),
        }
        for a in org.get_all_agents()
    ]
    return {
        "id": str(org.id),
        "name": org.name,
        "purpose": org.purpose,
        "target_repo_path": org.target_repo_path,
        "management_mode": org.management_mode,
        "workspace_path": org.workspace_path,
        "data_location": org.data_location,
        "initial_kpis": list(org.initial_kpis),
        "status": org.status.value,
        "health_score": live.health_score,
        "autonomy_score": live.autonomy_score,
        "improvement_velocity": live.improvement_velocity,
        "total_agents": len(agents),
        "agents": agents,
        "divisions": _serialize_org_structure(org),
        "pending_proposals": pending,
        "last_active": org.last_active.isoformat(),
        "is_system": org.is_system,
        "icon_data": org.icon_data,
    }


@app.put("/api/organizations/{org_name}")
async def api_update_organization(org_name: str, req: OrgUpdateRequest) -> Dict[str, Any]:
    """Organization の目的・リポジトリパスを更新する"""
    psm = _psm()
    org = psm.load_organization_by_name(org_name)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{org_name}' が見つかりません")

    if req.purpose is not None:
        org.purpose = req.purpose
    if req.target_repo_path is not None:
        org.target_repo_path = req.target_repo_path

    psm.save_organization(org)
    await _record_execution_event(
        "organization_updated",
        f"{org.name} を更新しました",
        org_name=org.name,
        entity_type="organization",
        entity_id=str(org.id),
        route="/orgs",
        metadata={"target_repo_path": org.target_repo_path},
    )
    return {
        "id": str(org.id),
        "name": org.name,
        "purpose": org.purpose,
        "target_repo_path": org.target_repo_path,
        "status": "updated",
    }


@app.get("/api/organizations/{org_name}/icon")
async def api_get_org_icon(org_name: str) -> Response:
    """組織のアイコンを返す。カスタムがなければ自動生成SVGを返す。"""
    try:
        org = _find_org(org_name)
        icon_data = getattr(org, "icon_data", "") or ""
        stripped = icon_data.lstrip()
        if stripped:
            if stripped.startswith("<svg") or stripped.startswith("<?xml"):
                return Response(content=icon_data, media_type="image/svg+xml")
            if stripped.startswith("data:") and "," in stripped:
                header, data = stripped.split(",", 1)
                media_type = (
                    header.split(";", 1)[0].removeprefix("data:") or "application/octet-stream"
                )
                # ユーザ管理値: 不正な media_type は CRLF 注入/500 を招くので token 検証
                if not re.fullmatch(r"[\w.+-]+/[\w.+-]+", media_type):
                    media_type = "application/octet-stream"
                return Response(content=base64.b64decode(data), media_type=media_type)
    except HTTPException:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load custom org icon for %s: %s", org_name, exc)

    return Response(content=_generate_pixel_art_svg(org_name), media_type="image/svg+xml")


@app.put("/api/organizations/{org_name}/icon")
async def api_set_org_icon(org_name: str, body: OrgIconRequest) -> Dict[str, str]:
    """組織のカスタムアイコンを設定する。"""
    org = _find_org(org_name)
    if len(body.icon_data) > 512 * 1024:
        raise HTTPException(status_code=400, detail="アイコンデータが大きすぎます（500KB以下）")

    org.icon_data = body.icon_data
    _psm().save_organization(org)
    return {"status": "ok"}


@app.delete("/api/organizations/{org_name}/icon")
async def api_delete_org_icon(org_name: str) -> Dict[str, str]:
    """組織のカスタムアイコンを削除する。"""
    org = _find_org(org_name)
    org.icon_data = ""
    _psm().save_organization(org)
    return {"status": "ok"}


@app.delete("/api/goals/history")
async def api_clear_goal_history() -> Dict[str, Any]:
    """ゴール実行履歴を消去する"""
    path = _goal_history_path()
    if path.exists():
        # 同じ履歴 state ファイルの writer なので _save_goal_history と同様に原子的に。
        atomic_write_text(path, "[]")
    return {"status": "cleared"}


@app.get("/api/organizations/{org_name}/proposals")
async def api_list_proposals(org_name: str) -> List[Dict[str, Any]]:
    """Organization の未完了改善提案一覧"""
    _, _, proposals = _pending_proposals_for(org_name)
    active_proposals = [
        proposal
        for proposal in proposals
        if is_active_improvement_proposal_status(proposal.get("status"))
    ]
    return [
        {
            # generated_code（適用用の全文）は一覧 payload を肥大化させるので除外する。
            # 表示には切り詰め版の code_preview を使う。全文は承認時に disk から読む。
            **{k: v for k, v in proposal.items() if k != "generated_code"},
            "diff_text": _extract_proposal_diff_text(proposal),
            "approval_notes": str(proposal.get("approval_notes") or ""),
        }
        for proposal in active_proposals
    ]


def _policy_engine() -> PolicyEngine:
    """承認ポリシーエンジン。bootstrap が書く <platform_home>/policy.yaml を読む。

    リクエストごとに ``_psm()`` の platform_home を基準にするので、テストでの
    monkeypatch（tmp_path）とも一貫する。ファイルが無ければ DEFAULT_POLICY。
    """
    policy_path = _psm().platform_home / "policy.yaml"
    return PolicyEngine(policy_path if policy_path.exists() else None)


def _git_remote_github_repo(repo_path: Path) -> str | None:
    """target_repo の origin リモートから owner/repo を推定する（best-effort）。

    パースは ``github_integration.repo_resolver.parse_github_owner_repo`` に集約
    （host 厳密検証つき・偽装ホスト受理を防ぐ）。subprocess は本モジュール側で実行する
    （テストが server.subprocess を monkeypatch するため）。
    """
    from core.runtime.process_utils import no_window_kwargs
    from github_integration.repo_resolver import parse_github_owner_repo

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            **no_window_kwargs(),
        )
    except Exception:  # noqa: BLE001 - git 不在/非リポジトリ等は推定不能として扱う
        return None
    return parse_github_owner_repo(result.stdout or "")


def _resolve_github_repo(org: Any, repo_path: Path) -> str | None:
    """PR 作成用 GitHub リポジトリ (owner/repo) を解決する。

    優先順位: Organization.github_repo > 環境変数 GITHUB_REPO > target_repo の git remote。
    """
    explicit = getattr(org, "github_repo", None)
    if explicit:
        return str(explicit)
    env_repo = os.getenv("GITHUB_REPO")
    if env_repo:
        return env_repo
    return _git_remote_github_repo(repo_path)


def _policy_payload(verdict: Any) -> Dict[str, Any]:
    return {
        "decision": verdict.decision.value,
        "reason": verdict.reason,
        "rule": verdict.rule_name,
    }


async def _enqueue_publish_from_proposal(
    target: Dict[str, Any], org_name: str
) -> Optional[Dict[str, Any]]:
    """承認済み content_asset に投稿指定があれば PublishJob を enqueue し、WS 通知する。

    投稿指定が無ければ何もせず None を返す（通常の content_asset 承認はこれまで通り）。
    enqueue の失敗で承認フロー全体を落とさない（投稿は後から再試行できる）。
    """
    try:
        from core.publishing.publish_jobs import enqueue_from_proposal

        job = enqueue_from_proposal(target, org_name, platform_home=_psm().platform_home)
    except Exception as exc:  # noqa: BLE001 — enqueue 失敗で承認は壊さない
        logger.warning("PublishJob の enqueue に失敗: %s", exc)
        return None
    if job is None:
        return None
    payload = job.to_dict()
    await _updates_hub.broadcast(
        {
            "type": "publish_queued",
            "status": "queued",
            "title": f"投稿待ち: {job.title or job.platform}",
            "org_name": org_name,
            "entity_type": "publish_job",
            "entity_id": job.job_id,
            "platform": job.platform,
            "route": "/inbox",
        }
    )
    return payload


async def _approve_proposal_internal(
    org_name: str,
    proposal_id: str,
    req: ProposalApproveRequest | None = None,
) -> Dict[str, Any]:
    from agents.base import AgentTask
    from agents.orchestrator_agent import OrchestratorAgent

    psm, sm, target = _find_pending_proposal(org_name, proposal_id)

    # すべての承認は PolicyEngine を必ず通す（人間起点・AI起点ともに）。
    # 提案元 Organization の分離コンテキストを渡し、external 組織の境界逸脱を汎用ガードする
    # （CLI 経路 cmd_proposal_apply と挙動を揃える）。
    from core.policy.engine import OrgBoundaryContext

    _src_org = psm.load_organization_by_name(org_name)
    _org_context = (
        OrgBoundaryContext(
            isolation_level=getattr(_src_org, "isolation_level", "standard"),
            allowed_path_scope=getattr(_src_org, "allowed_path_scope", []),
        )
        if _src_org is not None
        else None
    )
    verdict = _policy_engine().evaluate(target, org_context=_org_context)
    sm.update_proposal_fields(
        str(target.get("id", "")),
        policy_decision=verdict.decision.value,
        policy_reason=verdict.reason,
        policy_rule=verdict.rule_name,
    )
    if verdict.decision == ApprovalDecision.REJECT:
        # 空 file_path（meta-level）や無効化カテゴリはポリシーで自動棄却される。
        # CLI 経路と同様にステータスも rejected に落として一貫させる。
        sm.update_proposal_status(str(target.get("id", "")), "rejected")
        raise HTTPException(
            status_code=409, detail=f"ポリシーにより承認できません: {verdict.reason}"
        )

    # cross-org 構造介入は file_path を持たない。empty-file_path ブロックの前に、
    # 専用の構造介入 executor へ（PolicyEngine 通過後・PreTask 経由で）委任する。
    # 判定は PolicyEngine と同じ 4-way 述語に揃える（取りこぼし防止）。
    from core.models.organization import is_structural_intervention_dict

    if is_structural_intervention_dict(target):
        from core.orchestration.structural_intervention import execute_structural_intervention

        sm.update_proposal_status(str(target.get("id", "")), "in_progress")
        result = await execute_structural_intervention(target, psm=psm)
        if not result.success:
            sm.update_proposal_status(str(target.get("id", "")), "failed")
            raise HTTPException(
                status_code=500, detail=result.error or "構造介入の適用に失敗しました"
            )
        sm.update_proposal_status(str(target.get("id", "")), "done")
        return {
            "status": "done",
            "proposal_id": str(target.get("id", "")),
            "title": target.get("title"),
            "intervention_type": target.get("intervention_type"),
            "target_org_name": target.get("target_org_name"),
            "output": result.output,
            "policy": _policy_payload(verdict),
        }

    # content_asset（ワークスペース内資産）は専用 executor で安全に書き込む。
    # file_path を持つが「既存ファイルの LLM 書換」ではないため、通常 executor の前に分岐。
    from core.models.organization import is_content_asset_dict

    if is_content_asset_dict(target):
        org = _find_org(org_name)
        if not org.target_repo_path:
            raise HTTPException(
                status_code=400,
                detail="content_asset 提案には Organization の target_repo（ワークスペース）が必要です。",
            )
        from core.orchestration.asset_application import execute_content_asset

        sm.update_proposal_status(str(target.get("id", "")), "in_progress")
        result = await execute_content_asset(target, repo_path=org.target_repo_path)
        if not result.success:
            sm.update_proposal_status(str(target.get("id", "")), "failed")
            raise HTTPException(
                status_code=500, detail=result.error or "コンテンツ資産の適用に失敗しました"
            )
        sm.update_proposal_status(str(target.get("id", "")), "done")
        # ワークスペース書き込み成功後、投稿指定（intervention_spec.publish）があれば
        # PublishJob を enqueue する。承認＝外部投稿の人間ゲートを通過した証なので、
        # ここで初めて投稿ジョブが生まれる（承認なしの投稿は決して作られない）。
        publish_job_payload = await _enqueue_publish_from_proposal(target, org_name)
        return {
            "status": "done",
            "proposal_id": str(target.get("id", "")),
            "title": target.get("title"),
            "output": result.output,
            "policy": _policy_payload(verdict),
            "publish_job": publish_job_payload,
        }

    # ポリシーは通ったが file_path が無い提案は直接適用できない（meta 提案は
    # 自己改善ループ / Meta-Improvement Org が扱う）。executor に渡して 500 になる前に明示ブロック。
    if not target.get("file_path"):
        raise HTTPException(
            status_code=400,
            detail="この提案は file_path がないため直接適用できません（meta-level 提案は自己改善ループで処理されます）。",
        )

    approval_notes = (
        str(req.approval_notes).strip() if req and req.approval_notes is not None else ""
    )
    if approval_notes:
        sm.update_proposal_fields(str(target.get("id", "")), approval_notes=approval_notes)
        target["approval_notes"] = approval_notes

    org = _find_org(org_name)
    repo_path = Path(org.target_repo_path) if org.target_repo_path else psm.platform_home
    github_repo = await asyncio.to_thread(_resolve_github_repo, org, repo_path)
    sm.update_proposal_status(str(target.get("id", "")), "in_progress")
    await _record_execution_event(
        "proposal_started",
        str(target.get("title") or "改善提案を実行中"),
        status="pending",
        details=str(target.get("description") or ""),
        org_name=org_name,
        entity_type="proposal",
        entity_id=str(target.get("id", "")),
        route=f"/proposals?org={quote(org_name)}",
        metadata={"file_path": target.get("file_path")},
    )

    task = AgentTask(
        task_type="improvement_execution",
        description=f"改善提案の適用: {target.get('title')}",
        input={
            "repo_path": str(repo_path),
            "suggestion": target,
            "github_token": os.getenv("GITHUB_TOKEN"),
            "github_repo": github_repo,
        },
    )
    result = await OrchestratorAgent.create().run(task)
    if not result.success:
        sm.update_proposal_status(str(target.get("id", "")), "failed")
        await _record_execution_event(
            "proposal_failed",
            str(target.get("title") or "改善提案の適用に失敗"),
            status="error",
            details=result.error or "改善提案の適用に失敗しました",
            org_name=org_name,
            entity_type="proposal",
            entity_id=str(target.get("id", "")),
            route=f"/proposals?org={quote(org_name)}",
            metadata={"file_path": target.get("file_path")},
        )
        raise HTTPException(status_code=500, detail=result.error or "改善提案の適用に失敗しました")

    next_status = "done"
    sm.update_proposal_status(str(target.get("id", "")), next_status)
    payload = {
        "status": next_status,
        "proposal_id": str(target.get("id", "")),
        "title": target.get("title"),
        "approval_notes": approval_notes,
        "change_summary": result.output.get("change_summary", ""),
        "branch": result.output.get("branch"),
        "pr_url": result.output.get("pr_url"),
        "output": result.output,
        "policy": _policy_payload(verdict),
    }
    await _record_execution_event(
        "proposal_approved",
        str(target.get("title") or "改善提案を承認"),
        status="success",
        details=result.output.get("change_summary", "") or str(target.get("description") or ""),
        org_name=org_name,
        entity_type="proposal",
        entity_id=str(target.get("id", "")),
        route=f"/proposals?org={quote(org_name)}",
        metadata={
            "file_path": target.get("file_path"),
            "branch": result.output.get("branch"),
            "pr_url": result.output.get("pr_url"),
        },
    )
    await _updates_hub.broadcast(
        {
            "type": "task_complete",
            "status": "success",
            "title": str(target.get("title") or "改善提案を承認"),
            "details": result.output.get("change_summary", "")
            or str(target.get("description") or ""),
            "org_name": org_name,
            "entity_type": "proposal",
            "entity_id": str(target.get("id", "")),
            "route": f"/proposals?org={quote(org_name)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    return payload


async def _reject_proposal_internal(org_name: str, proposal_id: str) -> Dict[str, Any]:
    _, sm, target = _find_pending_proposal(org_name, proposal_id)
    # 却下も PolicyEngine を通して判定を監査記録する（却下自体は常に許可）。
    verdict = _policy_engine().evaluate(target)
    sm.update_proposal_fields(
        str(target.get("id", "")),
        policy_decision=verdict.decision.value,
        policy_reason=verdict.reason,
        policy_rule=verdict.rule_name,
    )
    sm.update_proposal_status(str(target.get("id", "")), "rejected")
    payload = {
        "status": "rejected",
        "proposal_id": str(target.get("id", "")),
        "title": target.get("title"),
        "policy": _policy_payload(verdict),
    }
    await _record_execution_event(
        "proposal_rejected",
        str(target.get("title") or "改善提案を却下"),
        status="success",
        details=str(target.get("description") or ""),
        org_name=org_name,
        entity_type="proposal",
        entity_id=str(target.get("id", "")),
        route=f"/proposals?org={quote(org_name)}",
        metadata={"file_path": target.get("file_path")},
    )
    return payload


@app.post("/api/proposals/{org_name}/{proposal_id}/approve")
async def api_approve_proposal(
    org_name: str,
    proposal_id: str,
    req: ProposalApproveRequest | None = None,
) -> Dict[str, Any]:
    return await _approve_proposal_internal(org_name, proposal_id, req)


@app.post("/api/proposals/{org_name}/{proposal_id}/reject")
async def api_reject_proposal(org_name: str, proposal_id: str) -> Dict[str, Any]:
    return await _reject_proposal_internal(org_name, proposal_id)


@app.post("/api/proposals/{org_name}/batch")
async def api_batch_update_proposals(org_name: str, body: ProposalBatchRequest) -> Dict[str, Any]:
    results = []
    for proposal_id in body.proposal_ids:
        try:
            result = (
                await _approve_proposal_internal(org_name, proposal_id)
                if body.action == "approve"
                else await _reject_proposal_internal(org_name, proposal_id)
            )
            results.append({"proposal_id": proposal_id, "ok": True, **result})
        except HTTPException as exc:
            results.append({"proposal_id": proposal_id, "ok": False, "detail": exc.detail})
        except Exception as exc:  # noqa: BLE001 — 1 件の予期せぬ失敗でバッチ全体を落とさない
            results.append(
                {
                    "proposal_id": proposal_id,
                    "ok": False,
                    "detail": str(exc) or type(exc).__name__,
                }
            )

    updated = [item for item in results if item.get("ok")]
    failed = [item for item in results if not item.get("ok")]
    return {
        "action": body.action,
        "updated": len(updated),
        "failed": len(failed),
        "results": results,
    }


# --------------------------------------------------------------------------- #
# Business（会社の合成で事業を表す第一級実体）                                    #
# --------------------------------------------------------------------------- #


def _business_store():
    from core.platform.business_store import BusinessStore

    return BusinessStore(platform_home=_psm().platform_home)


@app.get("/api/businesses", tags=["businesses"])
async def api_list_businesses() -> Dict[str, Any]:
    businesses = _business_store().list_businesses()
    return {"businesses": [b.model_dump(mode="json") for b in businesses]}


@app.post("/api/businesses", tags=["businesses"])
async def api_create_business(req: BusinessCreateRequest) -> Dict[str, Any]:
    from core.models.business import Business

    store = _business_store()
    if store.get(req.name):
        raise HTTPException(status_code=409, detail=f"Business '{req.name}' はすでに存在します")
    business = Business(
        name=req.name,
        purpose=req.purpose,
        member_orgs=list(req.member_orgs or []),
        roles=dict(req.roles or {}),
        handoff_routes=[r.model_dump() for r in (req.handoff_routes or [])],
        kpis=list(req.kpis or []),
    )
    store.save(business)
    return business.model_dump(mode="json")


@app.get("/api/businesses/{business_id}", tags=["businesses"])
async def api_get_business(business_id: str) -> Dict[str, Any]:
    business = _business_store().get(business_id)
    if business is None:
        raise HTTPException(status_code=404, detail=f"Business '{business_id}' が見つかりません")
    return business.model_dump(mode="json")


@app.get("/api/businesses/{business_id}/outcomes", tags=["businesses"])
async def api_business_outcomes(business_id: str) -> Dict[str, Any]:
    from core.metrics.outcomes import OutcomeStore

    business = _business_store().get(business_id)
    if business is None:
        raise HTTPException(status_code=404, detail=f"Business '{business_id}' が見つかりません")
    summary = OutcomeStore(platform_home=_psm().platform_home).summary_for_orgs(
        business.member_orgs, label=business.name
    )
    return {
        "business": business.name,
        "member_orgs": business.member_orgs,
        "by_metric": summary.by_metric,
        "event_count": summary.event_count,
        "total_revenue": summary.total_revenue,
        "total_reach": summary.total_reach,
    }


@app.post("/api/businesses/{business_id}/compose", tags=["businesses"])
async def api_compose_business(business_id: str) -> Dict[str, Any]:
    """handoff_routes から保留ハンドオフを作成する（合成の実体化）。"""
    store = _business_store()
    business = store.get(business_id)
    if business is None:
        raise HTTPException(status_code=404, detail=f"Business '{business_id}' が見つかりません")
    created = store.compose_handoffs(business)
    return {"created": len(created), "handoff_ids": [h.handoff_id for h in created]}


# 状態は active / paused / archived のみ（status を「飾り」から実効化する・P17）。
_BUSINESS_STATUSES = ("active", "paused", "archived")


@app.patch("/api/businesses/{business_id}", tags=["businesses"])
async def api_update_business(business_id: str, req: BusinessUpdateRequest) -> Dict[str, Any]:
    """Business を部分更新する（name/purpose/status/member_orgs/roles/kpis）。"""
    store = _business_store()
    business = store.get(business_id)
    if business is None:
        raise HTTPException(status_code=404, detail=f"Business '{business_id}' が見つかりません")
    if req.status is not None and req.status not in _BUSINESS_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status は {'/'.join(_BUSINESS_STATUSES)} のいずれかです",
        )
    if req.name is not None and req.name != business.name:
        clash = store.get(req.name)
        if clash is not None and str(clash.id) != str(business.id):
            raise HTTPException(status_code=409, detail=f"Business '{req.name}' はすでに存在します")
        business.name = req.name
    if req.purpose is not None:
        business.purpose = req.purpose
    if req.status is not None:
        business.status = req.status
    if req.member_orgs is not None:
        business.member_orgs = list(req.member_orgs)
    if req.roles is not None:
        business.roles = dict(req.roles)
    if req.kpis is not None:
        business.kpis = list(req.kpis)
    store.save(business)
    return business.model_dump(mode="json")


@app.delete("/api/businesses/{business_id}", tags=["businesses"])
async def api_delete_business(business_id: str) -> Dict[str, Any]:
    """Business を削除する（member 会社や成果データには触れない）。"""
    deleted = _business_store().delete(business_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Business '{business_id}' が見つかりません")
    return {"ok": True, "deleted": business_id}


@app.get("/api/businesses/{business_id}/performance", tags=["businesses"])
async def api_business_performance(business_id: str) -> Dict[str, Any]:
    """Business のヘルスサマリ（収益トレンド/handoff 成功率/KPI 状況）を 1 画面分で返す。

    member org を個別ドリルせずに事業全体の健康度を見るための集約（既存の OutcomeStore /
    revenue_intelligence / OrgHandoffStore を合成するだけ・新規ドメインロジックなし）。
    """
    from core.hierarchy.org_handoff import (
        HANDOFF_APPROVED,
        HANDOFF_CONSUMED,
        HANDOFF_REJECTED,
        OrgHandoffStore,
    )
    from core.metrics.outcomes import OutcomeStore
    from core.metrics.revenue_intelligence import analyze_revenue

    business = _business_store().get(business_id)
    if business is None:
        raise HTTPException(status_code=404, detail=f"Business '{business_id}' が見つかりません")

    home = _psm().platform_home
    store = OutcomeStore(platform_home=home)
    summary = store.summary_for_orgs(business.member_orgs, label=business.name)

    # member 横断で月次収益を合算し、トレンド/予測を出す。
    combined: Dict[str, float] = {}
    for org in business.member_orgs:
        for month, val in store.revenue_by_month(org).items():
            combined[month] = combined.get(month, 0.0) + val
    analysis = analyze_revenue(combined)

    # handoff の成功率（却下を除く実行可能 handoff のうち pending を越えて進んだ割合）。
    members = set(business.member_orgs)
    handoffs = [
        h
        for h in OrgHandoffStore(platform_home=home).list_handoffs()
        if h.source_org in members or h.target_org in members
    ]
    progressed = sum(1 for h in handoffs if h.status in (HANDOFF_APPROVED, HANDOFF_CONSUMED))
    actionable = sum(1 for h in handoffs if h.status != HANDOFF_REJECTED)
    success_rate = round(progressed / actionable, 4) if actionable else 0.0

    # KPI は目標値を持たないので「データ追跡できているか」を正直に返す（met と詐称しない）。
    kpi_status: Dict[str, str] = {}
    metrics_present = set(summary.by_metric)
    for kpi in business.kpis:
        key = str(kpi).strip().lower()
        tracked = any(key in m or m in key for m in metrics_present) if key else False
        kpi_status[kpi] = "tracked" if tracked else "no_data"

    return {
        "business": business.name,
        "member_org_count": len(business.member_orgs),
        "total_revenue": summary.total_revenue,
        "total_reach": summary.total_reach,
        "revenue_trend": analysis["trend"],
        "forecast_next": analysis["forecast_next"],
        "handoff_count": len(handoffs),
        "handoff_success_rate": success_rate,
        "kpi_status": kpi_status,
    }


# --------------------------------------------------------------------------- #
# Cross-org handoff（集客→販売→収益化の引き渡し / 承認ボタン）                    #
# --------------------------------------------------------------------------- #


class HandoffCreateRequest(BaseModel):
    source_org: str
    target_org: str
    kind: str
    title: str
    payload: Dict[str, Any] = {}
    priority: str = "medium"
    note: str = ""


class HandoffConsumeRequest(BaseModel):
    ref: str = ""


class HandoffApproveRequest(BaseModel):
    # True なら承認と同時に本文ドラフト（claude 生成）まで作る（承認1ボタンで本文まで）。
    draft: bool = False


def _handoff_store():
    from core.hierarchy.org_handoff import OrgHandoffStore

    return OrgHandoffStore(platform_home=_psm().platform_home)


def _handoff_dict(handoff) -> Dict[str, Any]:
    from dataclasses import asdict

    return asdict(handoff)


@app.get("/api/handoffs", tags=["handoffs"])
async def api_list_handoffs(
    source_org: str | None = None,
    target_org: str | None = None,
    status: str | None = None,
) -> List[Dict[str, Any]]:
    store = _handoff_store()
    return [
        _handoff_dict(h)
        for h in store.list_handoffs(source_org=source_org, target_org=target_org, status=status)
    ]


@app.post("/api/handoffs", tags=["handoffs"])
async def api_create_handoff(body: HandoffCreateRequest) -> Dict[str, Any]:
    store = _handoff_store()
    try:
        handoff = store.create(
            source_org=body.source_org,
            target_org=body.target_org,
            kind=body.kind,
            title=body.title,
            payload=body.payload,
            priority=body.priority,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _handoff_dict(handoff)


@app.post("/api/handoffs/{handoff_id}/approve", tags=["handoffs"])
async def api_approve_handoff(
    handoff_id: str, body: HandoffApproveRequest | None = None
) -> Dict[str, Any]:
    """承認ボタン: pending→approved ＋ 受け手 org に提案を自動生成。

    既定はブリーフ（決定論・即時）。``draft=true`` なら本文ドラフト（claude 生成）まで
    一括で作る（承認1ボタンで本文まで）。
    """
    from core.hierarchy.org_handoff import draft_handoff, materialize_handoff

    store = _handoff_store()
    try:
        handoff = store.approve(handoff_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"引き渡しが見つかりません: {handoff_id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    want_draft = bool(body.draft) if body else False
    materialized = None
    proposal = (
        await draft_handoff(handoff, psm=_psm())
        if want_draft
        else materialize_handoff(handoff, psm=_psm())
    )
    if proposal is not None:
        store.record_materialization(handoff.handoff_id, str(proposal.id))
        materialized = {
            "proposal_id": str(proposal.id),
            "org_name": handoff.target_org,
            "title": proposal.title,
            "file_path": proposal.file_path,
            "kind": "draft" if want_draft else "brief",
        }
    result = _handoff_dict(store.get(handoff.handoff_id))
    result["materialized"] = materialized
    return result


@app.post("/api/handoffs/{handoff_id}/draft", tags=["handoffs"])
async def api_draft_handoff(handoff_id: str) -> Dict[str, Any]:
    """本文ドラフト生成: 受け手 org に本文ドラフトの content_asset 提案を作る（claude 経由 / 不在時は決定論）。"""
    from core.hierarchy.org_handoff import draft_handoff

    store = _handoff_store()
    handoff = store.get(handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail=f"引き渡しが見つかりません: {handoff_id}")
    proposal = await draft_handoff(handoff, psm=_psm())
    if proposal is None:
        raise HTTPException(
            status_code=400,
            detail=f"受け手 '{handoff.target_org}' が未登録/repo 未設定のため本文生成できません。",
        )
    return {
        "handoff_id": handoff_id,
        "proposal_id": str(proposal.id),
        "org_name": handoff.target_org,
        "title": proposal.title,
        "file_path": proposal.file_path,
    }


@app.post("/api/handoffs/{handoff_id}/reject", tags=["handoffs"])
async def api_reject_handoff(handoff_id: str) -> Dict[str, Any]:
    store = _handoff_store()
    try:
        return _handoff_dict(store.reject(handoff_id))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"引き渡しが見つかりません: {handoff_id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/handoffs/{handoff_id}/consume", tags=["handoffs"])
async def api_consume_handoff(
    handoff_id: str, body: HandoffConsumeRequest | None = None
) -> Dict[str, Any]:
    store = _handoff_store()
    ref = body.ref if body else ""
    try:
        return _handoff_dict(store.mark_consumed(handoff_id, consumed_ref=ref))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"引き渡しが見つかりません: {handoff_id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --------------------------------------------------------------------------- #
# Outcomes（成果イベントの一括取り込み / サマリ）                                 #
# --------------------------------------------------------------------------- #


class OutcomeImportRequest(BaseModel):
    rows: List[Dict[str, Any]] = []
    org_name: str = ""


class OutcomeRecordRequest(BaseModel):
    """成果イベントを GUI から単件記録する（手動入力フォーム用）。"""

    org_name: str
    metric: str
    value: float
    unit: str = ""
    source: str = "manual"
    note: str = ""
    occurred_at: str = ""


def _outcome_store():
    from core.metrics.outcomes import OutcomeStore

    return OutcomeStore(platform_home=_psm().platform_home)


# --------------------------------------------------------------------------- #
# 通知センター（P3.3）: 集約・既読・設定（時間帯/最小レベル）                       #
# --------------------------------------------------------------------------- #


def _notification_center():
    from core.notifications import NotificationCenter

    return NotificationCenter(platform_home=get_platform_home())


class NotificationSettingsRequest(BaseModel):
    """通知設定の更新（部分更新可）。"""

    min_level: Optional[str] = None
    quiet_hours_start: Optional[int] = None
    quiet_hours_end: Optional[int] = None


class NotificationCreateRequest(BaseModel):
    """通知を 1 件追加する（手動/テスト・WS イベント連携用）。"""

    level: str = "info"
    message: str
    org_name: str = ""


@app.get("/api/notifications", tags=["notifications"])
async def api_list_notifications(limit: int = 50, unread_only: bool = False) -> Dict[str, Any]:
    """通知を新しい順に返す（``unread_only=true`` で未読のみ）+ 未読件数。"""
    center = _notification_center()
    return {
        "items": center.list(limit=max(1, min(limit, 200)), unread_only=unread_only),
        "unread": center.unread_count(),
    }


@app.get("/api/notifications/unread-count", tags=["notifications"])
async def api_notifications_unread_count() -> Dict[str, Any]:
    """未読通知件数（ベルバッジ用）。"""
    return {"unread": _notification_center().unread_count()}


@app.post("/api/notifications", tags=["notifications"])
async def api_create_notification(body: NotificationCreateRequest) -> Dict[str, Any]:
    """通知を 1 件追加する（未読として記録）。"""
    msg = body.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message は必須です")
    note = _notification_center().add(level=body.level, message=msg, org_name=body.org_name)
    return {"ok": True, "notification": note}


@app.post("/api/notifications/{notification_id}/read", tags=["notifications"])
async def api_mark_notification_read(notification_id: str) -> Dict[str, Any]:
    """通知を 1 件既読にする（存在しない id は 404）。"""
    center = _notification_center()
    if not center.mark_read(notification_id):
        # 既読化できない＝未知 id（既に既読は ok 扱い）。存在チェックで 404 を返す。
        known = {i["id"] for i in center.list(limit=200)}
        if notification_id not in known:
            raise HTTPException(status_code=404, detail="通知が見つかりません")
    return {"ok": True, "unread": center.unread_count()}


@app.post("/api/notifications/read-all", tags=["notifications"])
async def api_mark_all_notifications_read() -> Dict[str, Any]:
    """全通知を既読にする。"""
    center = _notification_center()
    marked = center.mark_all_read()
    return {"ok": True, "marked": marked, "unread": center.unread_count()}


@app.get("/api/notifications/settings", tags=["notifications"])
async def api_get_notification_settings() -> Dict[str, Any]:
    """通知設定（最小レベル・静音時間帯）を返す。"""
    return _notification_center().get_settings()


@app.put("/api/notifications/settings", tags=["notifications"])
async def api_update_notification_settings(body: NotificationSettingsRequest) -> Dict[str, Any]:
    """通知設定を部分更新する。"""
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return _notification_center().update_settings(patch)


# --------------------------------------------------------------------------- #
# Layered Memory / Playbook（WIRE-MEM）: 過去の学びの参照・蓄積                  #
# --------------------------------------------------------------------------- #


class PlaybookCaptureRequest(BaseModel):
    """施策ノート（Playbook）を 1 件蓄積するリクエスト。"""

    title: str
    content: str
    category: str = "general"
    org_name: str = ""


@app.get("/api/memory/playbook", tags=["memory"])
async def api_list_playbook(limit: int = 10, category: Optional[str] = None) -> Dict[str, Any]:
    """有用度上位の Playbook（過去の学び）を返す。"""
    from dataclasses import asdict

    from core.intelligence.memory_bank import MemoryBank

    bank = MemoryBank(get_platform_home())
    entries = bank.recall(category=category, limit=max(1, min(limit, 100)))
    return {"items": [asdict(e) for e in entries], "count": len(entries)}


@app.post("/api/memory/playbook", tags=["memory"])
async def api_capture_playbook(body: PlaybookCaptureRequest) -> Dict[str, Any]:
    """施策ノートを蓄積する（冪等: 同 title/category/org は二重追加しない）。"""
    from dataclasses import asdict

    from core.intelligence.memory_bank import MemoryBank

    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title は必須です")
    entry = MemoryBank(get_platform_home()).capture(
        title, body.content, category=body.category, org_name=body.org_name
    )
    return {"ok": True, "entry": asdict(entry)}


@app.post("/api/revenue/collect", tags=["outcomes"])
async def api_collect_revenue() -> Dict[str, Any]:
    """外部プラットフォームから収益を自動収集する（REV-COLLECT・接続済みのみ）。

    接続済みアダプタの売上を OutcomeStore へ記録し、未接続は「接続」人間タスクを一度だけ起票する
    （実 API 認証は human-gate）。LLM 非依存。
    """
    from core.metrics.revenue_collectors import run_revenue_collection

    return run_revenue_collection(platform_home=get_platform_home())


@app.post("/api/workspace-db/sync", tags=["workspace"])
async def api_workspace_db_sync() -> Dict[str, Any]:
    """JSON 正準から Workspace 集計 SQLite ミラーを再構築する（WS-2・非破壊・冪等）。"""
    from core.state.workspace_db import sync_workspace_db

    return sync_workspace_db(platform_home=get_platform_home())


@app.get("/api/workspace-db/stats", tags=["workspace"])
async def api_workspace_db_stats() -> Dict[str, Any]:
    """Workspace ミラーの件数・最終同期時刻・org 別累計収益を返す（WS-2）。"""
    from pathlib import Path

    from core.state.workspace_db import WorkspaceDB, _default_db_path

    db = WorkspaceDB(_default_db_path(Path(get_platform_home())))
    try:
        return {"stats": db.stats(), "revenue_by_org": db.revenue_by_org()}
    finally:
        db.close()


@app.post("/api/outcomes", tags=["outcomes"])
async def api_record_outcome(body: OutcomeRecordRequest) -> Dict[str, Any]:
    """成果イベントを 1 件記録する（GUI の手動入力フォーム用）。

    収益（revenue/sales/conversions）やリーチ等の任意メトリクスを単件で追記する。
    org_name / metric が空、value が数値化できない場合は 400。
    """
    from dataclasses import asdict

    org_name = body.org_name.strip()
    metric = body.metric.strip()
    if not org_name or not metric:
        raise HTTPException(status_code=400, detail="org_name と metric は必須です")
    store = _outcome_store()
    event = store.record(
        org_name,
        metric,
        body.value,
        unit=body.unit,
        source=body.source or "manual",
        note=body.note,
        occurred_at=body.occurred_at,
    )
    return {"ok": True, "event": asdict(event)}


@app.post("/api/outcomes/import", tags=["outcomes"])
async def api_import_outcomes(body: OutcomeImportRequest) -> Dict[str, Any]:
    """成果イベントを一括取り込みする（ダッシュボードの CSV/JSON エクスポートを行 dict で渡す）。"""
    store = _outcome_store()
    added, skipped = store.record_many(body.rows, default_org=body.org_name)
    return {
        "imported": len(added),
        "skipped": skipped,
        "orgs": sorted({event.org_name for event in added}),
    }


@app.get("/api/outcomes/export", tags=["outcomes"])
async def api_export_outcomes(
    org_name: Optional[str] = None,
    metric: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """成果イベントを CSV で書き出す（外部 BI/分析向け・curl > file.csv で保存可能）。

    注: この固定パスは ``/api/outcomes/{org_name}`` より先に登録する（後だと "export" が
    org_name として食われてシャドウされる）。
    """
    from fastapi.responses import PlainTextResponse

    csv_text = _outcome_store().export_events_csv(
        org_name, metric=metric, start_date=start_date, end_date=end_date
    )
    return PlainTextResponse(content=csv_text, media_type="text/csv")


@app.get("/api/outcomes/{org_name}", tags=["outcomes"])
async def api_outcome_summary(org_name: str) -> Dict[str, Any]:
    store = _outcome_store()
    summary = store.summary_for_org(org_name)
    return {
        "org_name": org_name,
        "event_count": summary.event_count,
        "by_metric": summary.by_metric,
        "by_source": summary.by_source,  # 収益チャネル別内訳（note/x/affiliate/manual…）
        "total_reach": summary.total_reach,
        "total_revenue": summary.total_revenue,
    }


# --------------------------------------------------------------------------- #
# Human Member タスク（人間専用作業のキュー）                                      #
# --------------------------------------------------------------------------- #


class HumanTaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    kind: str = "general"
    org_name: str = ""
    ref: str = ""


def _human_task_store():
    from core.humans.human_tasks import HumanTaskStore

    return HumanTaskStore(platform_home=_psm().platform_home)


@app.get("/api/human-tasks", tags=["humans"])
async def api_list_human_tasks(status: Optional[str] = None) -> Dict[str, Any]:
    """人間専用タスクの一覧（status=open/done で絞り込み可）。"""
    from dataclasses import asdict

    tasks = _human_task_store().list_tasks(status)
    items = [asdict(t) for t in tasks]
    return {
        "items": items,
        "open": sum(1 for t in tasks if t.status == "open"),
        "total": len(tasks),
    }


@app.post("/api/human-tasks", tags=["humans"])
async def api_create_human_task(body: HumanTaskCreateRequest) -> Dict[str, Any]:
    """人間専用タスクを 1 件積む。"""
    from dataclasses import asdict

    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title は必須です")
    task = _human_task_store().add(
        title,
        description=body.description,
        kind=body.kind,
        org_name=body.org_name,
        ref=body.ref,
    )
    return {"ok": True, "task": asdict(task)}


@app.post("/api/human-tasks/{task_id}/complete", tags=["humans"])
async def api_complete_human_task(task_id: str) -> Dict[str, Any]:
    """人間専用タスクを完了にする。存在しなければ 404。"""
    task = _human_task_store().complete(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    return {"ok": True, "task_id": task_id, "status": task.status}


@app.post(
    "/api/analyze",
    response_model=AnalyzeResponse,
    tags=["analysis"],
    responses={200: {"content": {"application/json": {"example": ANALYZE_RESPONSE_EXAMPLE}}}},
)
async def api_analyze(req: AnalyzeRequest) -> Dict[str, Any]:
    """Organization の担当リポジトリを分析して改善提案を生成"""
    return await _perform_analyze(req)


@app.post("/api/analyze/stream", tags=["analysis"])
async def api_analyze_stream(req: AnalyzeRequest) -> StreamingResponse:
    async def event_generator():
        try:
            yield _format_sse(
                {
                    "type": "start",
                    "org": req.org_name,
                    "org_name": req.org_name,
                    "content": f"{req.org_name} の分析を開始します",
                }
            )
            await asyncio.sleep(0)
            yield _format_sse(
                {
                    "type": "progress",
                    "message": "Loading organization...",
                    "content": "Loading organization...",
                }
            )
            await asyncio.sleep(0)
            yield _format_sse(
                {
                    "type": "progress",
                    "message": "Running code review...",
                    "content": "Running code review...",
                }
            )
            await asyncio.sleep(0)
            result = await _perform_analyze(req)
            yield _format_sse(
                {
                    "type": "progress",
                    "message": "Saving generated proposals...",
                    "content": "Saving generated proposals...",
                }
            )
            await asyncio.sleep(0)
            for proposal in result["generated_proposals"]:
                yield _format_sse(
                    {
                        "type": "proposal",
                        "org_name": result["org_name"],
                        "title": proposal.get("title"),
                        "file_path": proposal.get("file_path"),
                        "content": proposal.get("title") or "改善提案を生成しました",
                        "data": proposal,
                    }
                )
                await asyncio.sleep(0)
            yield _format_sse(
                {
                    "type": "done",
                    "org_name": result["org_name"],
                    "files_reviewed": result["files_reviewed"],
                    "proposals_generated": result["proposals_generated"],
                    "count": result["proposals_generated"],
                    "content": f"{result['files_reviewed']} 件のファイルを確認し、{result['proposals_generated']} 件の提案を生成しました",
                }
            )
            await asyncio.sleep(0)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Analyze stream failed", exc_info=exc)
            yield _format_sse({"type": "error", "message": _stream_error_message(exc)})
            await asyncio.sleep(0)

    return _stream_response(event_generator())


@app.get("/api/agents")
async def api_agents() -> List[Dict[str, Any]]:
    from core.loaders.agent_loader import AgentLoader

    return [_serialize_agent(defn) for defn in AgentLoader().all()]


@app.get("/api/agents/runtime")
async def api_runtime_agents() -> List[Dict[str, Any]]:
    return _collect_runtime_agents()


@app.get("/api/skills")
async def api_skills() -> List[Dict[str, Any]]:
    from core.loaders.skill_loader import SkillLoader

    return [_serialize_skill(defn) for defn in SkillLoader().all()]


@app.post(
    "/api/goals/run",
    response_model=GoalHistoryItemResponse,
    tags=["goals"],
    responses={200: {"content": {"application/json": {"example": GOAL_HISTORY_EXAMPLE}}}},
)
async def api_run_goal(req: GoalRunRequest) -> Dict[str, Any]:
    return await _perform_goal_run(req)


@app.post("/api/goals/stream", tags=["goals"])
async def api_goals_stream(req: GoalRunRequest) -> StreamingResponse:
    async def event_generator():
        # 実 per-task 進捗を流すための橋渡し。ExecutionCoordinator は各タスクの
        # 状態遷移ごとに on_progress(ExecutionProgress) を**同じイベントループ上で**
        # 同期呼び出しするので、queue.put_nowait で安全にバッファし generator が drain する。
        queue: asyncio.Queue = asyncio.Queue()
        done_sentinel = object()

        def on_progress(progress: Any) -> None:
            try:
                done = int(getattr(progress, "done_count", 0))
                total = int(getattr(progress, "total", 0))
                message = f"{done}/{total} タスク完了"
                queue.put_nowait(
                    {
                        "type": "progress",
                        "done": done,
                        "total": total,
                        "failed": int(getattr(progress, "failed_count", 0)),
                        "progress_pct": round(float(getattr(progress, "progress_pct", 0.0)), 1),
                        "message": message,
                        "content": message,
                    }
                )
            except Exception:  # noqa: BLE001 - 進捗通知の失敗で実行を止めない
                pass

        async def run_to_queue() -> dict[str, Any]:
            try:
                return await _perform_goal_run(req, progress_callback=on_progress)
            finally:
                queue.put_nowait(done_sentinel)

        task: Optional[asyncio.Task] = None
        try:
            yield _format_sse(
                {
                    "type": "start",
                    "goal": req.goal_text,
                    "org_name": getattr(req, "org_name", None),
                }
            )
            await asyncio.sleep(0)
            task = asyncio.create_task(run_to_queue())
            # 実行中に到着する実 per-task 進捗を順次配信（sentinel で終端）。
            while True:
                item = await queue.get()
                if item is done_sentinel:
                    break
                yield _format_sse(item)
                await asyncio.sleep(0)
            result = await task
            result_text = str(result.get("result") or result.get("summary") or "")
            yield _format_sse(
                {
                    "type": "result",
                    "goal": result.get("goal") or req.goal_text,
                    "org_name": result.get("org_name") or result.get("organization"),
                    "result": result_text,
                    "summary": result.get("summary") or result_text,
                    "content": result_text,
                    "data": result,
                }
            )
            await asyncio.sleep(0)
            yield _format_sse(
                {
                    "type": "done",
                    "goal": result.get("goal") or req.goal_text,
                    "org_name": result.get("org_name") or result.get("organization"),
                    "result": result_text,
                    "content": "ゴール実行が完了しました",
                }
            )
            await asyncio.sleep(0)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Goal stream failed", exc_info=exc)
            yield _format_sse({"type": "error", "message": _stream_error_message(exc)})
            await asyncio.sleep(0)
        finally:
            # クライアント切断（async generator が GeneratorExit でクローズ）時に、
            # 切り離した実行タスクをそのまま走らせ続けると goal 実行（claude CLI）が
            # 無駄に背景で完走する。旧 inline-await と同じく切断でキャンセルする。
            if task is not None and not task.done():
                task.cancel()

    return _stream_response(event_generator())


@app.get(
    "/api/goals/history",
    response_model=List[GoalHistoryItemResponse],
    tags=["goals"],
    responses={200: {"content": {"application/json": {"example": [GOAL_HISTORY_EXAMPLE]}}}},
)
async def api_goal_history() -> List[Dict[str, Any]]:
    return _load_goal_history()


@app.get(
    "/api/execution-history",
    response_model=List[ExecutionHistoryItemResponse],
    tags=["history"],
    responses={200: {"content": {"application/json": {"example": [EXECUTION_HISTORY_EXAMPLE]}}}},
)
async def api_execution_history(search: str | None = None, limit: int = 50) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(limit, 200))
    return _combined_execution_history(search=search, limit=safe_limit)


@app.get(
    "/api/search",
    response_model=List[SearchResultItemResponse],
    tags=["search"],
    responses={200: {"content": {"application/json": {"example": [SEARCH_RESULT_EXAMPLE]}}}},
)
async def api_search(q: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    query = q.strip()
    if not query:
        return []
    safe_limit = max(1, min(limit, 50))
    return _search_results(query, limit=safe_limit)


@app.get("/api/knowledge/files")
async def list_knowledge_files() -> Dict[str, List[Dict[str, Any]]]:
    """knowledge ディレクトリ内の Markdown ファイル一覧を返す"""
    if not KNOWLEDGE_DIR.exists():
        return {"files": []}

    files = []
    for path in sorted(KNOWLEDGE_DIR.rglob("*")):
        if path.is_file() and not path.name.startswith(".") and path.suffix.lower() == ".md":
            rel = path.relative_to(KNOWLEDGE_DIR)
            stat = path.stat()
            files.append(
                {
                    # POSIX 正規化（as_posix）: Windows の str(rel) はバックスラッシュ区切りになり、
                    # フロントの encodeFilePath（'/' で split）が誤エンコード→ネストファイルの
                    # GET/PUT/DELETE が round-trip 失敗する。相対パスは常に '/' 区切りで返す
                    # （2026-06-12 に repo_reader/dependency_graph 等で確立した規約の取りこぼし修正）。
                    "path": rel.as_posix(),
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "extension": path.suffix.lower(),
                }
            )
    return {"files": files}


@app.get("/api/knowledge/files/{file_path:path}")
async def get_knowledge_file(file_path: str) -> Dict[str, Any]:
    """Markdown ファイル内容を返す"""
    full_path = _resolve_knowledge_path(file_path)
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    content = full_path.read_text(encoding="utf-8")
    stat = full_path.stat()
    return {
        "path": file_path,
        "name": full_path.name,
        "content": content,
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }


@app.put("/api/knowledge/files/{file_path:path}")
async def update_knowledge_file(file_path: str, body: KnowledgeFileUpdate) -> Dict[str, str]:
    """Markdown ファイル内容を更新する"""
    full_path = _resolve_knowledge_path(file_path)
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    full_path.write_text(body.content, encoding="utf-8")
    return {"status": "ok", "path": file_path}


@app.delete("/api/knowledge/files/{file_path:path}")
async def delete_knowledge_file(file_path: str) -> Dict[str, str]:
    """Markdown ファイルを削除する"""
    full_path = _resolve_knowledge_path(file_path)
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    full_path.unlink()
    return {"status": "ok", "path": file_path}


@app.post("/api/knowledge/files")
async def create_knowledge_file(body: KnowledgeFileCreate) -> Dict[str, str]:
    """knowledge ディレクトリに新しい Markdown ファイルを作成する"""
    name = Path(body.name).name
    if not name or name.startswith("."):
        raise HTTPException(status_code=400, detail="不正なファイル名です")
    if Path(name).suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Markdown ファイルのみ作成できます")

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    full_path = _resolve_knowledge_path(name)
    if full_path.exists():
        raise HTTPException(status_code=409, detail="同名のファイルが既に存在します")

    full_path.write_text(body.content, encoding="utf-8")
    return {"status": "ok", "path": name}


@app.get("/api/orchestration/analyze/{task_type}")
async def api_orchestration_analyze(task_type: str) -> Dict[str, Any]:
    from core.intelligence.capability_registry import CapabilityRegistry
    from core.loaders.agent_loader import AgentLoader
    from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator

    registry = CapabilityRegistry()
    registry.scan_and_register_all()
    analysis = PreTaskOrchestrator(capability_registry=registry).analyze(
        task_type,
        f"Web UI orchestration analysis for {task_type}",
    )
    loader = AgentLoader()
    recommended_agents = []
    for agent_id in analysis.recommended_agent_ids:
        defn = loader.get(agent_id)
        if defn:
            recommended_agents.append(_serialize_agent(defn))
        else:
            recommended_agents.append({"capability_id": agent_id, "name": agent_id, "skills": []})
    return {
        "task_type": task_type,
        "recommended_pattern": str(analysis.recommended_pattern),
        "recommended_agents": recommended_agents,
        "complexity": analysis.complexity,
        "reasoning": analysis.research_notes,
        "confidence": analysis.confidence,
        "estimated_tokens": analysis.estimated_tokens,
    }


@app.post("/api/chat")
async def api_chat(body: ChatRequest) -> Dict[str, str]:
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="メッセージを入力してください")
    return {"response": await _process_chat_message(message, body.session_context)}


@app.get("/api/chat/sessions")
async def list_chat_sessions(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    """チャットセッション一覧（mtime 降順）。limit/offset でページング（既定 100 件）。"""
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    total = sum(1 for _ in _chat_sessions_dir().glob("*.json"))
    return {
        "sessions": _list_sessions(limit=limit, offset=offset),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.post("/api/chat/sessions")
async def create_chat_session(body: ChatSessionCreate) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    session = {
        "id": str(uuid4()),
        "name": body.name or "新しいセッション",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    _save_session(session)
    return session


@app.get("/api/chat/sessions/{session_id}")
async def get_chat_session(session_id: str) -> Dict[str, Any]:
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    return session


@app.put("/api/chat/sessions/{session_id}")
async def update_chat_session(session_id: str, body: ChatSessionUpdate) -> Dict[str, str]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="セッション名は空にできません")

    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")

    session["name"] = name
    _save_session(session)
    return {"id": session["id"], "name": session["name"]}


@app.delete("/api/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str) -> Dict[str, str]:
    path = _get_session_path(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    path.unlink()
    return {"status": "ok"}


@app.post("/api/chat/sessions/{session_id}/messages")
async def add_chat_message(session_id: str, body: ChatMessageCreate) -> Dict[str, dict[str, Any]]:
    if body.role != "user":
        raise HTTPException(status_code=400, detail="ユーザーメッセージのみ追加できます")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="メッセージを入力してください")

    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")

    prior_messages = list(session.get("messages", []))
    now = datetime.now(timezone.utc).isoformat()
    user_message = {
        "id": str(uuid4()),
        "role": "user",
        "content": content,
        "timestamp": now,
    }
    session.setdefault("messages", []).append(user_message)

    if not prior_messages and session.get("name") in {"", "新しいセッション"}:
        session["name"] = content[:20] + ("..." if len(content) > 20 else "")

    assistant_response = await _process_chat_message(content, prior_messages)
    assistant_message = {
        "id": str(uuid4()),
        "role": "assistant",
        "content": assistant_response,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    session["messages"].append(assistant_message)
    _save_session(session)

    return {"user_message": user_message, "assistant_message": assistant_message}


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    from agents.chat_agent import ChatSession

    if await _reject_ws_if_unauthorized(websocket):
        return
    await websocket.accept()
    session = ChatSession(has_llm=_has_llm())
    await websocket.send_json({"type": "status", "has_llm": session.has_llm})

    try:
        while True:
            try:
                payload = ChatPayload.model_validate(await websocket.receive_json())
            except WebSocketDisconnect:
                raise
            except Exception:  # noqa: BLE001 — 不正/壊れたクライアントフレーム
                try:
                    await websocket.send_json(
                        {"type": "error", "content": "invalid message format"}
                    )
                except Exception:  # noqa: BLE001 — ソケットが既に閉じかけ
                    pass
                continue
            message = payload.message.strip()
            if not message:
                continue

            try:
                response = await _dispatch_chat_message(session, message, allow_exit=True)
            except SystemExit:
                await websocket.send_json({"type": "exit"})
                await websocket.close()
                return

            if response:
                await websocket.send_json(
                    {"type": "message", "role": "assistant", "content": response}
                )
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")


@app.websocket("/ws/updates")
async def ws_updates(websocket: WebSocket) -> None:
    if await _reject_ws_if_unauthorized(websocket):
        return
    await _updates_hub.connect(websocket)
    await websocket.send_json(
        {
            "type": "status",
            "status": "connected",
            "title": "リアルタイム更新に接続しました",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    # GUI が監視に入ったらライブセッション監視を起動する（run_server 有効時のみ）。
    _ensure_session_monitor()

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("Updates WebSocket client disconnected")
    finally:
        await _updates_hub.disconnect(websocket)


def _open_browser_when_ready(port: int, *, host: str = "localhost", timeout: float = 15.0) -> None:
    """サーバが listen を開始したらブラウザで GUI を開く（デーモンスレッド）。

    uvicorn.run() はブロッキングなので、別スレッドでポートの listen を待ってから
    既定ブラウザを開く。exe をダブルクリックした人がそのまま可視化サイトに入れる。

    ``host`` は表示用のわかりやすいホスト名（例: ``pantheon.localhost`` /
    ``dev.pantheon.localhost``）。``*.localhost`` は最新ブラウザが 127.0.0.1 に
    自動解決するため、サーバの束縛先（127.0.0.1）を変えずに使える。
    """
    import socket
    import threading
    import webbrowser

    url = f"http://{host}:{port}"

    def _wait_and_open() -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.25)
        try:
            webbrowser.open(url)
        except Exception:
            logger.debug("ブラウザの自動起動に失敗しました: %s", url)

    threading.Thread(target=_wait_and_open, daemon=True).start()


def run_server(host: str = "127.0.0.1", port: int = 7860, open_browser: bool = False) -> None:
    import uvicorn

    # 実サーバ起動時のみライブセッション監視と task drain を有効化する
    # （テストでは無効のまま）。drain は config auto_drain_tasks（既定 True）で制御。
    global _LIVE_MONITOR_ENABLED, _TASK_DRAIN_ENABLED
    _LIVE_MONITOR_ENABLED = True
    try:
        _TASK_DRAIN_ENABLED = bool(_psm().load_platform_config().get("auto_drain_tasks", True))
    except Exception:  # noqa: BLE001 - 設定読込失敗時は drain しない
        _TASK_DRAIN_ENABLED = False

    env = resolve_environment()
    friendly = env["friendly_host"]
    print("\nPantheon Web GUI を起動しています...")
    print(f"   環境: {env['env_label']}（{env['environment']}）")
    print(f"   URL: http://{friendly}:{port}/   (= http://localhost:{port}/)")
    print(f"   プラットフォーム: {PlatformStateManager().platform_home}")
    if open_browser:
        _open_browser_when_ready(port, host=friendly)
    uvicorn.run(app, host=host, port=port)


@app.get("/api/atlas", tags=["atlas"])
async def api_atlas() -> dict:
    """Repository Atlas モデルを返す。

    使用フローカタログ・モジュール依存グラフ・CLI コマンド木・FastAPI ルートマップ・
    サブシステム在庫を、読み取り専用イントロスペクションで集約する（生成系に非依存）。
    重い静的解析を含むため event loop をブロックしないよう別スレッドで実行する。
    """
    from core.atlas import build_atlas

    return await asyncio.to_thread(build_atlas)


# --- SPA routes (must be last so API routes take precedence) ---


@app.get("/")
async def root():
    index = _serve_dir / "index.html"
    return FileResponse(index if index.exists() else STATIC_DIR / "index.html")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """Serve React SPA for all non-API client-side routes.

    未マッチの ``/api/...`` ``/ws/...`` パスは SPA の index.html(200) で握り潰さず、
    明示的に JSON 404 を返す（明示的 404 ハンドリングの非交渉ルール）。
    """
    if (
        full_path == "api"
        or full_path.startswith("api/")
        or full_path == "ws"
        or full_path.startswith("ws/")
    ):
        raise HTTPException(status_code=404, detail=f"Not Found: /{full_path}")
    index = _serve_dir / "index.html"
    return FileResponse(index if index.exists() else STATIC_DIR / "index.html")
