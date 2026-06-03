"""
RepoCorp AI - Web Server (Platform Level)

PlatformStateManager を使ってプラットフォーム全体を管理する FastAPI サーバー。
"""

from __future__ import annotations

import asyncio
import atexit
import base64
import colorsys
import contextlib
import hashlib
import hmac
import json
import logging
import os
import signal
import stat
import subprocess
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from core.execution.cli_registry import (
    DEFAULT_CLI_TOOL,
    DEFAULT_EXECUTION_MODE,
    EXECUTION_MODES,
    all_cli_tools,
)
from core.llm.capabilities import all_capabilities, get_capabilities
from core.llm.model_registry import FALLBACK_MODELS
from core.logging_config import (
    SecretRedactingFilter,
    configure_logging,
    redact_secrets,
    request_id_var,
)
from core.metrics.request_metrics import get_request_metrics
from core.models.organization import ImprovementProposal, is_active_improvement_proposal_status
from core.platform.state import PlatformStateManager, get_platform_home
from core.policy.engine import DEFAULT_POLICY, PolicyEngine

# Core 自己改善などの承認ルーティング判定に使う共有エンジン（既定ポリシー）。
DEFAULT_POLICY_ENGINE = PolicyEngine()

# 埋め込みターミナル(PTY)のセッション管理（cmux 風ワークスペース）。既定 cwd は RepoCorp リポジトリ。
from web.terminal import TerminalManager, is_allowed_origin, is_loopback_host  # noqa: E402

_terminal_manager = TerminalManager(default_cwd=Path(__file__).resolve().parent.parent)
# サーバ終了時に PTY 子プロセスを確実に終了する（グレースフルシャットダウン）。
atexit.register(_terminal_manager.shutdown)

logger = logging.getLogger(__name__)

# 秘匿値マスキング（A6）/構造化ログ（J2）/相関ID（J3）は core/logging_config に集約。
# 後方互換のため server 名前空間にもエイリアスを残す（既存テスト・参照を壊さない）。
_redact_secrets = redact_secrets
_SecretRedactingFilter = SecretRedactingFilter
logging.getLogger().addFilter(_SecretRedactingFilter())


def _atomic_write_text(path: Path, text: str) -> None:
    """原子的書き込み（共有実装 core.io_utils.atomic_write_text に委譲, D4/D5）。"""
    from core.io_utils import atomic_write_text

    atomic_write_text(path, text)


app = FastAPI(title="RepoCorp AI Platform", version="2.0.0")

DIST_DIR = Path(__file__).parent / "dist"  # React build output (唯一の正典 UI)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
SYSTEM_ORG_NAMES = {"Meta-Improvement Organization", "RepoCorp Core", "meta-improvement"}
SETTINGS_FILE = Path.home() / ".repocorp" / "gui_settings.json"
CHAT_SESSIONS_DIR = Path.home() / ".repocorp" / "chat_sessions"
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)
CHAT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
_PROVIDER_KEY_MAPPING = {
    "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "groq": ("groq_api_key", "GROQ_API_KEY"),
    "github_models": ("github_models_api_key", "GITHUB_TOKEN"),
    "gemini": ("gemini_api_key", "GOOGLE_API_KEY"),
}
# モデル一覧は core/llm/model_registry.py を唯一の正典とする（上部 import 参照）。
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
        "llm_provider": os.getenv("REPOCORP_DEFAULT_LLM_PROVIDER", "anthropic"),
        "llm_model": os.getenv("REPOCORP_DEFAULT_MODEL", "claude-3-5-sonnet-20241022"),
        "anthropic_api_key": "",
        "openai_api_key": "",
        "groq_api_key": "",
        "github_models_api_key": "",
        "gemini_api_key": "",
        "execution_mode": DEFAULT_EXECUTION_MODE,
        "cli_tool": DEFAULT_CLI_TOOL,
        "cli_commands": {},
        "daemon_interval": 3600,
        "daemon_max_files": 10,
        "model_configurations": deepcopy(DEFAULT_MODEL_CONFIGURATIONS),
        "prompt_templates": deepcopy(DEFAULT_PROMPT_TEMPLATES),
        "policy_rules": deepcopy(DEFAULT_POLICY),
    }


_model_cache: dict[str, tuple[list[str], float]] = {}
_CACHE_TTL = 300


def _cors_allowed_origins() -> list[str]:
    raw_origins = os.getenv("REPOCORP_CORS_ORIGINS", "")
    if raw_origins.strip():
        origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
        if origins:
            return origins
    return list(DEFAULT_CORS_ORIGINS)


def _trusted_hosts() -> list[str]:
    """Host ヘッダ許可リスト（DNS リバインディング対策, A4）。

    既定は localhost 系のみ。LAN 公開時は REPOCORP_ALLOWED_HOSTS で明示追加する。
    'testclient' は Starlette TestClient 用（ネットワーク到達不可）。
    """
    # 'testserver' は Starlette TestClient の既定 Host ヘッダ、'testclient' は client アドレス。
    hosts = {"localhost", "127.0.0.1", "::1", "[::1]", "testserver", "testclient"}
    raw = os.getenv("REPOCORP_ALLOWED_HOSTS", "")
    for host in raw.split(","):
        host = host.strip()
        if host:
            hosts.add(host)
    return sorted(hosts)


# Host ヘッダ検証（DNS リバインディング / 0.0.0.0 経由攻撃の緩和）。CORS より先に評価させる。
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-RepoCorp-Token"],
)


@app.middleware("http")
async def _cache_hashed_assets(request: Request, call_next):
    """Vite がハッシュ付きファイル名で出力する /assets/* は長期 immutable キャッシュ可（E10）。"""
    response = await call_next(request)
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


_DEFAULT_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MiB


def _max_body_bytes() -> int:
    """リクエストボディの上限バイト数（A8）。REPOCORP_MAX_BODY_BYTES で上書き可。"""
    raw = os.getenv("REPOCORP_MAX_BODY_BYTES", "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return _DEFAULT_MAX_BODY_BYTES


def _resolve_api_token() -> str:
    """任意のローカル API トークンを解決する（A2）。

    REPOCORP_API_TOKEN（環境変数）> gui_settings.api_auth_token の順。いずれも
    未設定なら空文字を返し、認証は無効（＝既定の挙動は不変）。
    """
    token = os.getenv("REPOCORP_API_TOKEN", "").strip()
    if token:
        return token
    try:
        return str(_load_gui_settings().get("api_auth_token") or "").strip()
    except Exception:
        return ""


@app.middleware("http")
async def _enforce_body_size_limit(request: Request, call_next):
    """リクエストボディのサイズ上限（A8, DoS/メモリ枯渇の緩和）。

    Content-Length ヘッダで判定し、上限超過は 413 を返す（本文を読み込む前に拒否）。
    """
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared = int(content_length)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        if declared > _max_body_bytes():
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
    return await call_next(request)


@app.middleware("http")
async def _enforce_api_token(request: Request, call_next):
    """任意のローカル API トークン認証（A2, 既定は無効）。

    REPOCORP_API_TOKEN もしくは gui_settings.api_auth_token が設定されている時のみ、
    `/api/*`（`/api/health` を除く）に `X-RepoCorp-Token` か `Authorization: Bearer`
    での一致を要求する。未設定時は素通り＝既存の挙動を変えない。
    """
    token = _resolve_api_token()
    if token and request.method != "OPTIONS":
        path = request.url.path
        if path.startswith("/api/") and path != "/api/health":
            provided = request.headers.get("x-repocorp-token", "")
            if not provided:
                auth = request.headers.get("authorization", "")
                if auth.lower().startswith("bearer "):
                    provided = auth[7:].strip()
            if not hmac.compare_digest(provided, token):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def _request_context(request: Request, call_next):
    """相関ID（J3）の付与とリクエストメトリクス（J4）の記録。

    受信 `X-Request-ID` を尊重し、無ければ生成する。contextvar に載せてログへ自動付与し、
    応答に `X-Request-ID` を返す。処理時間/件数/ステータスを `RequestMetrics` に集計する。
    最外周（最後に定義）に置き、全ミドルウェア/ハンドラを計測対象にする。
    """
    request_id = request.headers.get("x-request-id") or uuid4().hex
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_var.reset(token)
        get_request_metrics().record(status_code, (time.perf_counter() - start) * 1000.0)

# React build (dist/) を唯一の正典 UI として配信する。
# 旧来の単一HTML UI は web/legacy/ にアーカイブ済みで配信しない。
# ビルド成果物が無い場合は import を壊さず、案内ページ(503)を返す。
_ASSETS_DIR = DIST_DIR / "assets"
if _ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")

_FRONTEND_NOT_BUILT_HTML = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>RepoCorp AI</title>
<style>body{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;display:flex;
min-height:100vh;align-items:center;justify-content:center;margin:0}.card{max-width:560px;
padding:32px;background:#161b22;border:1px solid #30363d;border-radius:16px}code{background:#0d1117;
padding:2px 6px;border-radius:6px;color:#58a6ff}h1{margin-top:0;font-size:20px}</style></head>
<body><div class="card"><h1>フロントエンドが未ビルドです</h1>
<p>React UI の成果物 (<code>web/dist</code>) が見つかりません。次を実行してビルドしてください:</p>
<p><code>npm --prefix web/frontend install &amp;&amp; npm --prefix web/frontend run build</code></p>
<p>API は <code>/docs</code> で利用できます。</p></div></body></html>"""


def _spa_index_response() -> Response:
    """React SPA の index.html を返す。未ビルドなら案内ページ(503)。"""
    index = DIST_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse(_FRONTEND_NOT_BUILT_HTML, status_code=503)


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
    if SETTINGS_FILE.exists():
        _warn_if_settings_permissions_too_open(SETTINGS_FILE)
        try:
            loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                merged = deepcopy(defaults)
                merged.update({k: v for k, v in loaded.items() if k not in {"model_configurations", "prompt_templates", "policy_rules"}})
                for key in ("model_configurations", "prompt_templates", "policy_rules"):
                    value = loaded.get(key)
                    if isinstance(value, dict):
                        merged[key] = value
                return merged
        except Exception:
            pass
    return defaults


def _save_gui_settings(data: Dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(SETTINGS_FILE, json.dumps(data, ensure_ascii=False, indent=2))
    _set_settings_file_permissions(SETTINGS_FILE)



def _ensure_chat_sessions_dir() -> None:
    CHAT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)



def _get_session_path(session_id: str) -> Path:
    _ensure_chat_sessions_dir()
    path = (CHAT_SESSIONS_DIR / f"{session_id}.json").resolve()
    try:
        path.relative_to(CHAT_SESSIONS_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="不正なセッションIDです") from exc
    return path



def _load_session(session_id: str) -> dict[str, Any] | None:
    path = _get_session_path(session_id)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)



def _save_session(session: dict[str, Any]) -> None:
    _ensure_chat_sessions_dir()
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = _get_session_path(session["id"])
    with path.open("w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)



def _list_sessions() -> list[dict[str, Any]]:
    _ensure_chat_sessions_dir()
    sessions = []
    for path in sorted(CHAT_SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
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


async def _process_chat_message(message: str, session_context: list[dict[str, Any]] | None = None) -> str:
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


def _get_provider_api_key(settings: Dict[str, Any], provider: str) -> str:
    api_keys = settings.get("api_keys", {})
    if not isinstance(api_keys, dict):
        api_keys = {}
    setting_key, env_key = _PROVIDER_KEY_MAPPING.get(provider, (None, None))
    if not setting_key or not env_key:
        return ""
    return str(api_keys.get(provider) or settings.get(setting_key) or os.getenv(env_key, ""))



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
    target_repo_path: str = Field(default="", max_length=4096)

    @field_validator("target_repo_path")
    @classmethod
    def validate_target_repo_path(cls, value: str) -> str:
        return _normalize_request_path(value, "target_repo_path")



class OrgIconRequest(ApiRequestModel):
    icon_data: str = Field(max_length=512 * 1024)



class AnalyzeRequest(ApiRequestModel):
    org_name: str = Field(min_length=1, max_length=120)
    max_files: int = Field(default=15, ge=1, le=50)



class ProposalApproveRequest(ApiRequestModel):
    approval_notes: str | None = Field(default=None, max_length=2000)



class GoalRunRequest(ApiRequestModel):
    goal_text: str = Field(min_length=1, max_length=4000)



class CoreImproveRequest(ApiRequestModel):
    instruction: str = Field(min_length=1, max_length=4000)
    file_path: str = Field(min_length=1, max_length=512)
    files: list[str] | None = Field(default=None, max_length=20)
    org_name: str | None = Field(default=None, max_length=120)
    max_iterations: int = Field(default=3, ge=1, le=6)

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        normalized = _normalize_request_path(value, "file_path", allow_empty=False)
        if Path(normalized).is_absolute():
            raise ValueError("file_path はリポジトリ相対パスで指定してください")
        return normalized

    @field_validator("files")
    @classmethod
    def validate_files(cls, value: list[str] | None) -> list[str] | None:
        if not value:
            return value
        normalized: list[str] = []
        for item in value:
            norm = _normalize_request_path(item, "files", allow_empty=False)
            if Path(norm).is_absolute():
                raise ValueError("files はリポジトリ相対パスで指定してください")
            normalized.append(norm)
        return normalized



class TerminalCreateRequest(ApiRequestModel):
    name: str | None = Field(default=None, max_length=80)
    cwd: str | None = Field(default=None, max_length=4096)
    command: str | None = Field(default=None, max_length=2000)
    cli_tool: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")


class TerminalRenameRequest(ApiRequestModel):
    name: str = Field(min_length=1, max_length=80)


class DaemonStartRequest(ApiRequestModel):
    interval: int = Field(default=3600, ge=1)
    max_files: int = Field(default=10, ge=1, le=1000)



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


class DaemonStatusResponse(BaseModel):
    status: str | None = None
    message: str | None = None
    running: bool
    pid: int | None
    log_path: str | None
    interval: int | None = None
    max_files: int | None = None


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
    execution_mode: str = DEFAULT_EXECUTION_MODE
    cli_tool: str = DEFAULT_CLI_TOOL
    daemon_interval: int
    daemon_max_files: int
    model_configurations: dict[str, Any] = Field(default_factory=dict)
    prompt_templates: dict[str, str] = Field(default_factory=dict)
    policy_rules: dict[str, Any] = Field(default_factory=dict)
    provider_capabilities: dict[str, Any] = Field(default_factory=dict)
    settings_file: str
    has_llm: bool


class ProviderModelsResponse(BaseModel):
    provider: str
    models: list[str] = Field(default_factory=list)
    source: str
    capabilities: dict[str, Any] = Field(default_factory=dict)


class ExecutionHistoryItemResponse(BaseModel):
    id: str
    timestamp: str
    operation: str
    status: str
    title: str
    details: str = ""
    actor: str = "system"
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
    "platform_home": str(Path.home() / ".repocorp"),
    "initialized": True,
    "has_llm": True,
}
DAEMON_STATUS_EXAMPLE = {
    "running": True,
    "pid": 4321,
    "log_path": str(Path.home() / ".repocorp" / "daemon.log"),
}
DAEMON_ACTION_EXAMPLE = {
    "status": "started",
    "message": "デーモンを起動しました。",
    "running": True,
    "pid": 4321,
    "log_path": str(Path.home() / ".repocorp" / "daemon.log"),
    "interval": 3600,
    "max_files": 10,
}
INIT_RESPONSE_EXAMPLE = {
    "status": "initialized",
    "message": "プラットフォームを初期化しました。",
    "platform_home": str(Path.home() / ".repocorp"),
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
    "settings_file": str(Path.home() / ".repocorp" / "gui_settings.json"),
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


def _ws_max_connections() -> int:
    """/ws/updates の同時接続上限（A9）。0 で無制限。REPOCORP_WS_MAX_CONNECTIONS で上書き。"""
    raw = os.getenv("REPOCORP_WS_MAX_CONNECTIONS", "").strip()
    if raw:
        try:
            value = int(raw)
            if value >= 0:
                return value
        except ValueError:
            pass
    return 50


class UpdateHub:
    def __init__(self, max_connections: int | None = None) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._max_connections = _ws_max_connections() if max_connections is None else max_connections

    async def connect(self, websocket: WebSocket) -> bool:
        """接続を受理する。上限超過なら 1013 で拒否し False を返す（A9）。"""
        async with self._lock:
            at_capacity = bool(self._max_connections) and len(self._connections) >= self._max_connections
        if at_capacity:
            await websocket.close(code=1013)  # try again later
            return False
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        return True

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


def _migrate_system_orgs(psm: PlatformStateManager | None = None) -> None:
    state_manager = psm or PlatformStateManager()
    meta_org_id = state_manager.load_platform_config().get("meta_improvement_org_id")

    for org in state_manager.load_organizations():
        should_protect = org.name in SYSTEM_ORG_NAMES or (meta_org_id and str(org.id) == meta_org_id)
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
    s = settings or _load_gui_settings()
    provider = s.get("llm_provider", os.getenv("REPOCORP_DEFAULT_LLM_PROVIDER", "anthropic"))
    return bool(_get_provider_api_key(s, provider))



def _goal_history_path() -> Path:
    return _psm().platform_home / "goal_history.json"



def _normalize_goal_history_item(item: dict[str, Any]) -> dict[str, Any]:
    goal = str(item.get("goal") or item.get("goal_text") or "")
    result = str(item.get("result") or item.get("summary") or "")
    timestamp = str(item.get("timestamp") or item.get("created_at") or "")
    org_name = item.get("org_name") or item.get("organization")
    normalized = dict(item)
    normalized.update({
        "goal": goal,
        "goal_text": str(item.get("goal_text") or goal),
        "result": result,
        "summary": str(item.get("summary") or result),
        "timestamp": timestamp,
        "created_at": str(item.get("created_at") or timestamp),
        "org_name": org_name,
        "organization": item.get("organization") or org_name,
        "recommendations": item.get("recommendations") if isinstance(item.get("recommendations"), list) else [],
    })
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
    _atomic_write_text(_goal_history_path(), json.dumps(history, ensure_ascii=False, indent=2))



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
        "title": str(item.get("title") or "RepoCorp event"),
        "details": str(item.get("details") or ""),
        "actor": str(item.get("actor") or "system"),
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
    _atomic_write_text(_execution_history_path(), json.dumps(normalized, ensure_ascii=False, indent=2))



def _append_execution_history(record: dict[str, Any], keep: int = 200) -> dict[str, Any]:
    normalized = _normalize_execution_history_item(record)
    _save_execution_history([normalized, *_load_execution_history()], keep=keep)
    return normalized



def _matches_search_text(query: str, *values: Any) -> bool:
    needle = query.strip().lower()
    if not needle:
        return True
    return any(needle in str(value).lower() for value in values if value is not None and value != "")



def _goal_history_execution_items() -> list[dict[str, Any]]:
    items = []
    for goal in _load_goal_history():
        items.append(_normalize_execution_history_item({
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
        }))
    return items



def _task_execution_items() -> list[dict[str, Any]]:
    items = []
    for task in _task_queue().list_tasks(limit=None):
        timestamp = task.get("completed_at") or task.get("started_at") or task.get("created_at")
        status = str(task.get("status") or "pending")
        items.append(_normalize_execution_history_item({
            "id": f"task-{task.get('id')}",
            "timestamp": timestamp,
            "operation": f"task_{status}",
            "status": "error" if status == "failed" else "success" if status in {"done", "cancelled"} else "pending",
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
        }))
    return items



def _combined_execution_history(search: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    records = [*_load_execution_history(), *_goal_history_execution_items(), *_task_execution_items()]
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: item.get("timestamp", ""), reverse=True):
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
    actor: str = "system",
    org_name: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    route: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = _append_execution_history({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "status": status,
        "title": title,
        "details": details,
        "actor": actor,
        "org_name": org_name,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "route": route,
        "metadata": metadata or {},
    })
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
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False



def _daemon_status_payload() -> dict[str, Any]:
    pid_file, log_file = _daemon_paths()
    pid = _read_daemon_pid(pid_file)
    return {
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
        "status": proposal.status,
    }



def _goal_record(req: GoalRunRequest, result: Any) -> dict[str, Any]:
    summary = result.summary() if callable(getattr(result, "summary", None)) else str(result)
    return _normalize_goal_history_item({
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
    })



def _stream_error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)



async def _perform_analyze(req: AnalyzeRequest) -> dict[str, Any]:
    from agents.base import AgentTask
    from agents.code_review_agent import CodeReviewAgent
    from core.llm import get_configured_llm_provider, resolve_default_provider
    from core.models.organization import AgentSkill, SpecialistAgent

    psm = _psm()
    org = psm.load_organization_by_name(req.org_name)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{req.org_name}' が見つかりません")

    repo_path = Path(org.target_repo_path) if org.target_repo_path else Path(".")
    specialist = SpecialistAgent(
        name="CodeReviewer",
        skills=[AgentSkill.DEEP_RESEARCH, AgentSkill.PERFORMANCE_ANALYSIS],
    )
    # GUI設定/環境変数で選ばれたプロバイダーとキーで構成（どのプロバイダーでも動く）。
    settings = _load_gui_settings()
    agent = CodeReviewAgent(
        specialist,
        provider_name=resolve_default_provider(settings),
        llm_provider=get_configured_llm_provider(settings=settings),
    )
    task = AgentTask(
        task_type="code_review",
        description=f"{org.name} のコードレビューと改善提案生成",
        input={"repo_path": str(repo_path), "max_files": req.max_files},
    )

    result = await agent.run(task)
    if not result.success:
        status_code = 422 if result.error and "found" in result.error.lower() else 500
        raise HTTPException(status_code=status_code, detail=result.error)

    sm = psm.get_org_state_manager(org)
    generated_proposals: list[dict[str, Any]] = []
    for suggestion in result.output.get("suggestions", []):
        proposal = ImprovementProposal(
            review_id=uuid4(),
            priority=suggestion.get("priority", "medium"),
            category=suggestion.get("category", "general"),
            title=suggestion.get("title", "改善提案"),
            description=suggestion.get("description", ""),
            file_path=suggestion.get("file_path", ""),
            expected_impact=suggestion.get("expected_impact", ""),
        )
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
            route=f"/proposals?org={org.name}",
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
        metadata={"files_reviewed": result.output.get("files_reviewed", 0), "proposals_generated": len(generated_proposals)},
    )

    return {
        "org_name": org.name,
        "files_reviewed": result.output.get("files_reviewed", 0),
        "proposals_generated": len(generated_proposals),
        "generated_proposals": generated_proposals,
    }



async def _perform_goal_run(req: GoalRunRequest) -> dict[str, Any]:
    from core.goals.abstract_goal_pipeline import AbstractGoalPipeline
    from core.llm import get_default_llm_client

    pipeline = AbstractGoalPipeline(llm_client=get_default_llm_client(settings=_load_gui_settings()))
    result = await pipeline.run(req.goal_text)
    record = _goal_record(req, result)
    _save_goal_history(record)
    await _updates_hub.broadcast({
        "type": "goal_completed",
        "status": "success" if record.get("success", True) else "error",
        "title": record.get("goal") or req.goal_text,
        "details": record.get("result") or record.get("summary") or "",
        "org_name": record.get("org_name") or record.get("organization"),
        "entity_type": "goal",
        "entity_id": record.get("id"),
        "route": "/data",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return record



def _resolve_self_improvement_org(psm: PlatformStateManager, preferred: str | None = None):
    """Core 自己改善提案の保存先 Organization を解決する。

    優先: 指定名 > RepoCorp-Self > システム組織 > メタ組織 > 先頭。
    """
    orgs = psm.load_organizations()
    if not orgs:
        raise HTTPException(status_code=404, detail="Organization がありません。先に作成してください。")

    by_name = {org.name: org for org in orgs}
    if preferred and preferred in by_name:
        return by_name[preferred]
    for name in ("RepoCorp-Self", *SYSTEM_ORG_NAMES):
        if name in by_name:
            return by_name[name]
    meta_id = psm.load_platform_config().get("meta_improvement_org_id")
    if meta_id:
        for org in orgs:
            if str(org.id) == str(meta_id):
                return org
    return orgs[0]


def _validated_changes_path(sm: Any, proposal_id: str) -> Path:
    return sm.state_dir / "improvements" / f"{proposal_id}.changes.json"


def _save_validated_changes(sm: Any, proposal_id: str, changes: list[dict[str, Any]], change_summary: str) -> None:
    """CoreImprovementAgent が検証した {file_path, new_content} をサイドカー保存する。"""
    files = [
        {"file_path": str(c.get("file_path")), "new_content": str(c.get("new_content"))}
        for c in changes
        if isinstance(c, dict) and c.get("file_path") and isinstance(c.get("new_content"), str)
    ]
    if not files:
        return
    path = _validated_changes_path(sm, proposal_id)
    _atomic_write_text(
        path,
        json.dumps({"files": files, "change_summary": change_summary}, ensure_ascii=False, indent=2),
    )


def _load_validated_changes(sm: Any, proposal_id: str) -> list[dict[str, Any]]:
    """サイドカーから検証済み変更を読み込む（無ければ空）。"""
    path = _validated_changes_path(sm, proposal_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    files = data.get("files") if isinstance(data, dict) else None
    return files if isinstance(files, list) else []


async def _perform_core_improve(req: CoreImproveRequest) -> dict[str, Any]:
    """RepoCorp 自身(Core)の改善を内蔵エージェントで検証し、人間承認用の提案にする。

    流れ: CoreImprovementAgent が LLM で編集→テスト検証(反復)→検証済み差分 →
    PolicyEngine で判定 → ImprovementProposal 化(既定で人間承認待ち)。
    本エンドポイントは作業ツリーへ自動適用しない（validate_only）。
    """
    from agents.base import AgentTask
    from agents.core_improvement_agent import CoreImprovementAgent
    from core.llm import get_default_llm_client

    psm = _psm()
    org = _resolve_self_improvement_org(psm, req.org_name)

    llm_client = get_default_llm_client(settings=_load_gui_settings())
    agent = CoreImprovementAgent(
        llm_client=llm_client,
        project_root=PROJECT_ROOT,
        max_iterations=req.max_iterations,
    )
    task = AgentTask(
        task_type="core_improvement",
        description=f"Core 改善: {req.instruction[:80]}",
        input={
            "instruction": req.instruction,
            "file_path": req.file_path,
            "files": req.files or None,
            "max_iterations": req.max_iterations,
            "auto_apply": False,
        },
    )
    result = await agent.run(task)

    if not result.success:
        await _record_execution_event(
            "core_improvement_failed",
            f"Core 改善の検証に失敗: {req.file_path}",
            status="error",
            details=str(result.error or ""),
            org_name=org.name,
            entity_type="core_improvement",
            route="/proposals",
            metadata={"file_path": req.file_path},
        )
        raise HTTPException(status_code=422, detail=result.error or "Core 改善の検証に失敗しました。")

    output = result.output or {}
    change_summary = str(output.get("change_summary") or "")
    diff = str(output.get("diff") or "")
    attempts = int(output.get("attempts") or 1)

    description = (
        f"【自己改善指示】\n{req.instruction}\n\n"
        f"【変更概要】\n{change_summary}\n\n"
        f"【検証】既存テストが緑であることを確認済み（{attempts} 回の試行）。\n\n"
        f"【検証済み差分】\n{diff[:8000]}"
    )

    proposal = ImprovementProposal(
        review_id=uuid4(),
        priority="high",
        category="core_self_improvement",
        title=f"Core 改善: {change_summary or req.instruction[:60]}",
        description=description,
        file_path=req.file_path,
        expected_impact="RepoCorp 自身のコード品質/機能の改善",
        implementation_difficulty="medium",
        status="proposed",
    )

    verdict = DEFAULT_POLICY_ENGINE.evaluate({
        "priority": proposal.priority,
        "category": proposal.category,
        "file_path": proposal.file_path,
    })

    sm = psm.get_org_state_manager(org)
    sm.save_improvement_proposal(proposal)

    # 検証済みの変更内容をサイドカー保存 → 承認時に LLM 再生成せず直接適用する。
    changes = output.get("changes") if isinstance(output.get("changes"), list) else []
    _save_validated_changes(sm, str(proposal.id), changes, change_summary)

    await _record_execution_event(
        "core_improvement_proposed",
        proposal.title,
        status="pending",
        actor="user",
        details=change_summary or req.instruction,
        org_name=org.name,
        entity_type="proposal",
        entity_id=str(proposal.id),
        route=f"/proposals?org={org.name}",
        metadata={
            "file_path": req.file_path,
            "policy_decision": verdict.decision.value,
            "validated": True,
            "attempts": attempts,
        },
    )

    return {
        "validated": True,
        "applied": False,
        "file_path": req.file_path,
        "files": output.get("files") or [req.file_path],
        "change_summary": change_summary,
        "diff": diff,
        "attempts": attempts,
        "proposal_id": str(proposal.id),
        "org_name": org.name,
        "policy_decision": verdict.decision.value,
        "policy_reason": verdict.reason,
    }



def _find_org(org_name: str):
    org = _psm().load_organization_by_name(org_name)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{org_name}' が見つかりません")
    return org


def _generate_pixel_art_svg(seed_text: str, size: int = 8) -> str:
    """組織名から決定論的なピクセルアートSVGを生成する。"""
    h = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    nums = [int(h[i:i + 2], 16) for i in range(0, 64, 2)]

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
        f'  {cells_str}\n'
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
    # 完全一致を優先し、無ければ前方一致（短縮ID）にフォールバックする（D8: 誤マッチ低減）。
    target = next(
        (p for p in proposals if str(p.get("id", "")) == proposal_id),
        None,
    ) or next(
        (p for p in proposals if str(p.get("id", "")).startswith(proposal_id)),
        None,
    )
    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"ID '{proposal_id}' に一致する未対応提案が見つかりません",
        )
    return psm, sm, target



# 全提案の横断ロードはコストが高い（全org・全ファイル read+parse, E3）。
# (org名, 件数, 最大mtime) のシグネチャでキャッシュし、追加/削除/上書きを検出して無効化する。
_proposals_cache: dict[str, Any] = {"signature": None, "data": None}


def _proposals_signature(psm: Any) -> tuple:
    parts: list[tuple[str, int, float]] = []
    for org in psm.load_organizations():
        sm = psm.get_org_state_manager(org)
        improvements_dir = sm.state_dir / "improvements"
        if not improvements_dir.exists():
            continue
        mtimes = [p.stat().st_mtime for p in improvements_dir.glob("*.json")]
        parts.append((org.name, len(mtimes), max(mtimes, default=0.0)))
    return tuple(parts)


def _invalidate_proposals_cache() -> None:
    _proposals_cache["signature"] = None
    _proposals_cache["data"] = None


def _load_all_proposals() -> list[dict[str, Any]]:
    psm = _psm()
    signature = _proposals_signature(psm)
    if _proposals_cache["data"] is not None and _proposals_cache["signature"] == signature:
        return _proposals_cache["data"]

    proposals: list[dict[str, Any]] = []
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
    result = sorted(
        proposals,
        key=lambda item: str(item.get("last_updated") or item.get("created_at") or ""),
        reverse=True,
    )
    _proposals_cache["signature"] = signature
    _proposals_cache["data"] = result
    return result



def _serialize_org_structure(org: Any) -> list[dict[str, Any]]:
    divisions: list[dict[str, Any]] = []
    for division_index, division in enumerate(org.divisions):
        teams: list[dict[str, Any]] = []
        previous_team_name: str | None = None
        previous_division_name = org.divisions[division_index - 1].name if division_index > 0 else None
        for team in division.teams:
            teams.append({
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
            })
            previous_team_name = team.name
        divisions.append({
            "id": str(division.id),
            "name": division.name,
            "type": str(division.type.value if hasattr(division.type, "value") else division.type),
            "mission": division.mission,
            "teams": teams,
        })
    return divisions



def _search_results(query: str, limit: int = 20) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    psm = _psm()
    organizations = psm.load_organizations()

    for org in organizations:
        if _matches_search_text(query, org.name, org.purpose, org.target_repo_path, org.status.value):
            results.append({
                "id": f"organization:{org.id}",
                "type": "organization",
                "title": org.name,
                "subtitle": org.purpose,
                "route": "/orgs",
                "org_name": org.name,
                "status": org.status.value,
                "metadata": {"target_repo_path": org.target_repo_path},
            })
        for division in org.divisions:
            for team in division.teams:
                for agent in team.agents:
                    skills = [str(skill) for skill in agent.skills]
                    if _matches_search_text(query, agent.name, agent.description, *skills, team.name, division.name, org.name):
                        results.append({
                            "id": f"agent:{agent.id}",
                            "type": "agent",
                            "title": agent.name,
                            "subtitle": f"{org.name} / {team.name}",
                            "route": "/agents",
                            "org_name": org.name,
                            "status": None,
                            "metadata": {"team": team.name, "division": division.name, "skills": skills},
                        })

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
            results.append({
                "id": f"proposal:{proposal.get('id')}",
                "type": "proposal",
                "title": str(proposal.get("title") or "改善提案"),
                "subtitle": str(proposal.get("description") or proposal.get("file_path") or ""),
                "route": f"/proposals?org={org_name}",
                "org_name": org_name or None,
                "status": proposal.get("status"),
                "metadata": {
                    "file_path": proposal.get("file_path"),
                    "priority": proposal.get("priority"),
                    "category": proposal.get("category"),
                },
            })

    for goal in _load_goal_history():
        if _matches_search_text(query, goal.get("goal"), goal.get("goal_text"), goal.get("result"), goal.get("summary"), goal.get("org_name")):
            results.append({
                "id": f"goal:{goal.get('id') or hashlib.sha1(json.dumps(goal, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:12]}",
                "type": "goal",
                "title": str(goal.get("goal") or goal.get("goal_text") or "Goal"),
                "subtitle": str(goal.get("result") or goal.get("summary") or ""),
                "route": "/data",
                "org_name": goal.get("org_name") or goal.get("organization"),
                "status": "success" if goal.get("success", True) else "error",
                "metadata": {"goal_type": goal.get("goal_type"), "scale": goal.get("scale")},
            })

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
                                "skills": [getattr(skill, "value", skill) for skill in getattr(agent, "skills", [])],
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
                            "skills": [getattr(skill, "value", skill) for skill in getattr(agent, "skills", [])],
                            "status": "running" if getattr(agent, "current_task", None) else "idle",
                            "current_task": getattr(agent, "current_task", None),
                            "proficiency": float(getattr(agent, "performance_score", 0.0)),
                            "configuration": {
                                "organization": org.name,
                                "division": division.name,
                                "team": team.name,
                                "skills": [getattr(skill, "value", skill) for skill in getattr(agent, "skills", [])],
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
    """プラットフォーム全体のステータス"""
    from core.metrics.balanced_growth import calculate_group_metrics, calculate_organization_metrics
    from core.models.organization import GroupHQState

    psm = _psm()
    orgs = psm.load_organizations()
    hq = GroupHQState()
    metrics_list = []
    for org in orgs:
        hq.add_organization(org)
        sm = psm.get_org_state_manager(org)
        pending = len(sm.get_pending_improvement_proposals(limit=100))
        metrics_list.append(calculate_organization_metrics(org, pending_proposals_count=pending))

    if metrics_list:
        group = calculate_group_metrics(hq, metrics_list)
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
        }

    return {
        "group_health_score": 0.0,
        "balance_score": 100.0,
        "total_organizations": 0,
        "active_organizations": 0,
        "weakest_organization": None,
        "strongest_organization": None,
        "platform_home": str(psm.platform_home),
        "initialized": psm.is_initialized(),
        "has_llm": _has_llm(),
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
    req = req or DaemonStartRequest()
    pid_file, log_file = _daemon_paths()
    pid = _read_daemon_pid(pid_file)
    if pid is not None and _is_process_running(pid):
        status = "already_running"
        return {
            "status": status,
            "message": _daemon_action_message(status),
            **_daemon_status_payload(),
            "interval": req.interval,
            "max_files": req.max_files,
        }
    if pid is not None:
        pid_file.unlink(missing_ok=True)

    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as log_handle:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "core._daemon_runner",
                f"--interval={req.interval}",
                f"--max-files={req.max_files}",
            ],
            cwd=PROJECT_ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    status = "started"
    return {
        "status": status,
        "message": _daemon_action_message(status),
        "running": True,
        "pid": proc.pid,
        "log_path": str(log_file),
        "interval": req.interval,
        "max_files": req.max_files,
    }


@app.post(
    "/api/daemon/stop",
    response_model=DaemonStatusResponse,
    response_model_exclude_none=True,
    tags=["platform"],
    responses={200: {"content": {"application/json": {"example": {**DAEMON_ACTION_EXAMPLE, "status": "stopped", "running": False}}}}},
)
async def api_daemon_stop() -> Dict[str, Any]:
    pid_file, log_file = _daemon_paths()
    pid = _read_daemon_pid(pid_file)
    if pid is None:
        pid_file.unlink(missing_ok=True)
        status = "not_running"
        return {
            "status": status,
            "message": _daemon_action_message(status),
            "running": False,
            "pid": None,
            "log_path": str(log_file),
        }

    try:
        os.kill(pid, signal.SIGTERM)
        status = "stopped"
    except OSError:
        status = "already_stopped"
    pid_file.unlink(missing_ok=True)
    return {
        "status": status,
        "message": _daemon_action_message(status),
        "running": False,
        "pid": pid,
        "log_path": str(log_file),
    }


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
    """ウェルカム用サンプル組織を作成する"""
    from core.org_factory import create_default_organization

    psm = _psm()
    created = []

    sample_orgs = [
        {
            "name": "Sample Organization",
            "purpose": "RepoCorp AI のデモ用サンプル組織です。実際のリポジトリを指定して編集してください。",
            "target_repo_path": str(PROJECT_ROOT),
        },
    ]

    for s in sample_orgs:
        existing = psm.load_organization_by_name(s["name"])
        if not existing:
            org = create_default_organization(s["name"], s["purpose"])
            org.target_repo_path = s["target_repo_path"]
            psm.save_organization(org)
            created.append(s["name"])
            await _record_execution_event(
                "organization_created",
                f"{s['name']} を作成しました",
                org_name=s["name"],
                entity_type="organization",
                entity_id=s["name"],
                route="/orgs",
                metadata={"source": "welcome", "target_repo_path": s["target_repo_path"]},
            )

    return {"created": created, "skipped": [s["name"] for s in sample_orgs if s["name"] not in created]}


@app.get("/api/tasks")
async def api_list_tasks(org_name: str | None = None, status: str | None = None, limit: int = 50) -> Dict[str, Any]:
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
    if not queue.cancel_task(task_id):
        raise HTTPException(status_code=400, detail="タスクをキャンセルできません（実行中または存在しない）")
    await _record_execution_event(
        "task_cancelled",
        str(task.get("description") if task else "Task cancelled"),
        status="success",
        details="Task cancelled",
        org_name=task.get("org_name") if task else None,
        entity_type="task",
        entity_id=task_id,
        route="/dashboard",
        metadata={"task_type": task.get("type") if task else None},
    )
    return {"status": "cancelled", "task_id": task_id}


class SettingsUpdateRequest(ApiRequestModel):
    llm_provider: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    llm_model: str | None = Field(default=None, max_length=120)
    anthropic_api_key: str | None = Field(default=None, max_length=512)
    openai_api_key: str | None = Field(default=None, max_length=512)
    groq_api_key: str | None = Field(default=None, max_length=512)
    github_models_api_key: str | None = Field(default=None, max_length=512)
    gemini_api_key: str | None = Field(default=None, max_length=512)
    execution_mode: str | None = Field(default=None, pattern=r"^(api|cli)$")
    cli_tool: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    cli_commands: dict[str, str] | None = None
    daemon_interval: int | None = Field(default=None, ge=1)
    daemon_max_files: int | None = Field(default=None, ge=1, le=1000)
    model_configurations: dict[str, Any] | None = None
    prompt_templates: dict[str, str] | None = None
    policy_rules: dict[str, Any] | None = None


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
        "anthropic_api_key_masked": _mask_key(s.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")),
        "openai_api_key_masked": _mask_key(s.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")),
        "groq_api_key_masked": _mask_key(s.get("groq_api_key") or os.getenv("GROQ_API_KEY", "")),
        "github_models_api_key_masked": _mask_key(s.get("github_models_api_key") or os.getenv("GITHUB_TOKEN", "")),
        "gemini_api_key_masked": _mask_key(s.get("gemini_api_key") or os.getenv("GOOGLE_API_KEY", "")),
        "anthropic_api_key_set": bool(s.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY")),
        "openai_api_key_set": bool(s.get("openai_api_key") or os.getenv("OPENAI_API_KEY")),
        "groq_api_key_set": bool(s.get("groq_api_key") or os.getenv("GROQ_API_KEY")),
        "github_models_api_key_set": bool(s.get("github_models_api_key") or os.getenv("GITHUB_TOKEN")),
        "gemini_api_key_set": bool(s.get("gemini_api_key") or os.getenv("GOOGLE_API_KEY")),
        "execution_mode": s.get("execution_mode", DEFAULT_EXECUTION_MODE),
        "cli_tool": s.get("cli_tool", DEFAULT_CLI_TOOL),
        "daemon_interval": s.get("daemon_interval", 3600),
        "daemon_max_files": s.get("daemon_max_files", 10),
        "model_configurations": s.get("model_configurations", deepcopy(DEFAULT_MODEL_CONFIGURATIONS)),
        "prompt_templates": s.get("prompt_templates", deepcopy(DEFAULT_PROMPT_TEMPLATES)),
        "policy_rules": s.get("policy_rules", deepcopy(DEFAULT_POLICY)),
        "provider_capabilities": all_capabilities(),
        "settings_file": str(SETTINGS_FILE),
        "has_llm": _has_llm(s),
    }


@app.get("/api/storage/info")
async def get_storage_info() -> Dict[str, Any]:
    """~/.repocorp/ 配下の永続化データ情報を返す"""
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
            "last_modified": datetime.fromtimestamp(last_modified, tz=timezone.utc).isoformat() if last_modified else None,
        }

    return {
        "platform_home": str(platform_home),
        "note": "サーバーを再起動しても以下のデータはすべて保持されます",
        "storage": {
            "settings": {
                "label": "GUI設定（LLMプロバイダー・APIキー等）",
                "path": str(SETTINGS_FILE),
                **dir_info(SETTINGS_FILE),
            },
            "organizations": {
                "label": "組織定義",
                "path": str(platform_home / "organizations"),
                **dir_info(platform_home / "organizations"),
            },
            "chat_sessions": {
                "label": "チャットセッション履歴",
                "path": str(CHAT_SESSIONS_DIR),
                **dir_info(CHAT_SESSIONS_DIR),
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
        os.environ["REPOCORP_DEFAULT_LLM_PROVIDER"] = req.llm_provider
    if req.llm_model is not None:
        s["llm_model"] = req.llm_model
        os.environ["REPOCORP_DEFAULT_MODEL"] = req.llm_model
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
    if req.execution_mode is not None:
        s["execution_mode"] = req.execution_mode
    if req.cli_tool is not None:
        s["cli_tool"] = req.cli_tool
    if req.cli_commands is not None:
        s["cli_commands"] = req.cli_commands
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
    return {"status": "saved", "has_llm": _has_llm(s)}


@app.get("/api/execution/modes", tags=["settings"])
async def api_execution_modes() -> Dict[str, Any]:
    """実行モード(API/CLI)と利用可能な外部CLIツール一覧を返す。

    各CLIツールには解決済みコマンドと PATH 上の可用性(available)が付く。
    """
    s = _load_gui_settings()
    return {
        "modes": EXECUTION_MODES,
        "default_mode": DEFAULT_EXECUTION_MODE,
        "current": {
            "execution_mode": s.get("execution_mode", DEFAULT_EXECUTION_MODE),
            "cli_tool": s.get("cli_tool", DEFAULT_CLI_TOOL),
        },
        "cli_tools": all_cli_tools(s),
    }


@app.get("/api/health", tags=["system"])
async def api_health() -> Dict[str, Any]:
    """liveness/readiness 用の軽量ヘルスチェック（J1）。"""
    running_terminals = sum(1 for s in _terminal_manager.list() if s.get("status") == "running")
    return {
        "status": "ok",
        "version": app.version,
        "has_llm": _has_llm(),
        "frontend_built": (DIST_DIR / "index.html").exists(),
        "terminal_sessions": running_terminals,
    }


@app.get("/api/usage", tags=["system"])
async def api_usage() -> Dict[str, Any]:
    """LLM トークン使用量の集計（provider/model 別 + 合計, B7）。"""
    from core.llm import get_usage_tracker

    return get_usage_tracker().snapshot()


@app.delete("/api/usage", tags=["system"])
async def api_reset_usage() -> Dict[str, Any]:
    """使用量カウンタをリセットする。"""
    from core.llm import reset_usage

    reset_usage()
    return {"status": "reset"}


@app.get("/api/metrics", tags=["system"])
async def api_metrics() -> Dict[str, Any]:
    """HTTP リクエストメトリクス（件数/エラー/平均処理時間/ステータス別, J4）。"""
    return get_request_metrics().snapshot()


@app.delete("/api/metrics", tags=["system"])
async def api_reset_metrics() -> Dict[str, Any]:
    """リクエストメトリクスをリセットする。"""
    get_request_metrics().reset()
    return {"status": "reset"}


@app.get(
    "/api/providers/{provider}/models",
    response_model=ProviderModelsResponse,
    tags=["settings"],
    responses={200: {"content": {"application/json": {"example": PROVIDER_MODELS_EXAMPLE}}}},
)
async def get_provider_models(provider: str) -> Dict[str, Any]:
    """プロバイダーから利用可能なモデル一覧と能力記述を取得する。"""
    capabilities = get_capabilities(provider).to_dict()
    cached = _get_cached_models(provider)
    if cached is not None:
        return {"provider": provider, "models": cached, "source": "cache", "capabilities": capabilities}

    if provider not in FALLBACK_MODELS:
        return {"provider": provider, "models": [], "source": "unknown", "capabilities": capabilities}

    settings = _load_gui_settings()
    models: list[str] | None = None
    source = "fallback"

    try:
        if provider == "anthropic":
            api_key = _get_provider_api_key(settings, provider)
            if api_key:
                import anthropic

                client = anthropic.Anthropic(api_key=api_key)
                response = await asyncio.to_thread(client.models.list, limit=100)
                models = sorted(model.id for model in response.data if getattr(model, "id", ""))
                source = "api"

        elif provider == "openai":
            api_key = _get_provider_api_key(settings, provider)
            if api_key:
                from openai import OpenAI

                client = OpenAI(api_key=api_key)
                response = await asyncio.to_thread(client.models.list)
                models = sorted(
                    model.id
                    for model in response.data
                    if getattr(model, "id", "").startswith(("gpt-", "o1", "o3", "o4"))
                    and "instruct" not in model.id
                    and "audio" not in model.id
                    and "vision" not in model.id
                )
                source = "api"

        elif provider == "groq":
            api_key = _get_provider_api_key(settings, provider)
            if api_key:
                from openai import OpenAI

                client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
                response = await asyncio.to_thread(client.models.list)
                models = sorted(model.id for model in response.data if getattr(model, "id", ""))
                source = "api"

        elif provider == "github_models":
            github_token = _get_provider_api_key(settings, provider)
            if github_token:
                import httpx

                response = await asyncio.to_thread(
                    lambda: httpx.get(
                        "https://models.inference.ai.azure.com/models",
                        headers={"Authorization": f"Bearer {github_token}"},
                        timeout=10,
                    )
                )
                if response.status_code == 200:
                    data = response.json()
                    items = data if isinstance(data, list) else data.get("data", [])
                    models = sorted(
                        item.get("id", item.get("name", ""))
                        for item in items
                        if isinstance(item, dict) and (item.get("id") or item.get("name"))
                    )
                    source = "api"

        elif provider == "gemini":
            api_key = _get_provider_api_key(settings, provider)
            if api_key:
                from core.llm.gemini_provider import GeminiProvider

                fetched = await asyncio.to_thread(GeminiProvider.list_models, api_key)
                if fetched:
                    models = fetched
                    source = "api"

    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch models for %s: %s", provider, exc)

    if not models:
        models = list(FALLBACK_MODELS.get(provider, []))
        source = "fallback"

    _set_cached_models(provider, models)
    return {"provider": provider, "models": models, "source": source, "capabilities": capabilities}


@app.get("/api/organizations")
async def api_list_organizations() -> List[Dict[str, Any]]:
    """Organization 一覧"""
    from core.metrics.balanced_growth import calculate_organization_metrics

    psm = _psm()
    orgs = psm.load_organizations()
    result = []
    for org in orgs:
        sm = psm.get_org_state_manager(org)
        pending = len(sm.get_pending_improvement_proposals(limit=100))
        m = calculate_organization_metrics(org, pending_proposals_count=pending)
        result.append({
            "id": str(org.id),
            "name": org.name,
            "purpose": org.purpose,
            "target_repo_path": org.target_repo_path,
            "status": org.status.value,
            "health_score": m.health_score,
            "autonomy_score": org.autonomy_score,
            "total_agents": len(org.get_all_agents()),
            "pending_proposals": pending,
            "last_active": org.last_active.isoformat(),
            "is_system": org.is_system,
            "icon_data": org.icon_data,
        })
    return result


@app.post("/api/organizations")
async def api_create_organization(req: OrgCreateRequest) -> Dict[str, Any]:
    """新しい Organization を登録する"""
    from core.bootstrap import bootstrap_platform
    from core.org_factory import create_default_organization

    psm = bootstrap_platform()
    existing = psm.load_organization_by_name(req.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Organization '{req.name}' はすでに存在します")

    org = create_default_organization(req.name, req.purpose)
    org.target_repo_path = req.target_repo_path
    psm.save_organization(org)
    await _record_execution_event(
        "organization_created",
        f"{org.name} を作成しました",
        actor="user",
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
        actor="user",
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
        return _normalize_request_path(value, "target_repo_path")


@app.get("/api/organizations/{org_name}")
async def api_get_organization(org_name: str) -> Dict[str, Any]:
    """Organization の詳細を返す"""
    from core.metrics.balanced_growth import calculate_organization_metrics

    psm = _psm()
    org = psm.load_organization_by_name(org_name)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{org_name}' が見つかりません")

    sm = psm.get_org_state_manager(org)
    pending = len(sm.get_pending_improvement_proposals(limit=100))
    m = calculate_organization_metrics(org, pending_proposals_count=pending)
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
        "status": org.status.value,
        "health_score": m.health_score,
        "autonomy_score": org.autonomy_score,
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
                media_type = header.split(";", 1)[0].removeprefix("data:") or "application/octet-stream"
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
        path.write_text("[]", encoding="utf-8")
    return {"status": "cleared"}


@app.get("/api/organizations/{org_name}/proposals")
async def api_list_proposals(org_name: str) -> List[Dict[str, Any]]:
    """Organization の未完了改善提案一覧"""
    _, _, proposals = _pending_proposals_for(org_name)
    active_proposals = [proposal for proposal in proposals if is_active_improvement_proposal_status(proposal.get("status"))]
    return [
        {
            **proposal,
            "diff_text": _extract_proposal_diff_text(proposal),
            "approval_notes": str(proposal.get("approval_notes") or ""),
        }
        for proposal in active_proposals
    ]


async def _approve_proposal_internal(
    org_name: str,
    proposal_id: str,
    req: ProposalApproveRequest | None = None,
) -> Dict[str, Any]:
    from agents.base import AgentTask
    from agents.orchestrator_agent import OrchestratorAgent
    from core.llm import get_default_llm_client

    psm, sm, target = _find_pending_proposal(org_name, proposal_id)
    if not target.get("file_path"):
        raise HTTPException(status_code=400, detail="この提案は file_path がないため承認できません")

    approval_notes = str(req.approval_notes).strip() if req and req.approval_notes is not None else ""
    if approval_notes:
        sm.update_proposal_fields(str(target.get("id", "")), approval_notes=approval_notes)
        target["approval_notes"] = approval_notes

    org = _find_org(org_name)
    repo_path = Path(org.target_repo_path) if org.target_repo_path else psm.platform_home

    # 検証済み変更(サイドカー)があれば添付し、LLM 再生成せず直接適用する。
    # Core 自己改善の検証済み変更は RepoCorp リポジトリ自身を対象にする。
    validated_changes = _load_validated_changes(sm, str(target.get("id", "")))
    if validated_changes:
        target["validated_changes"] = validated_changes
        if str(target.get("category") or "") == "core_self_improvement":
            repo_path = PROJECT_ROOT

    sm.update_proposal_status(str(target.get("id", "")), "in_progress")
    await _record_execution_event(
        "proposal_started",
        str(target.get("title") or "改善提案を実行中"),
        status="pending",
        details=str(target.get("description") or ""),
        org_name=org_name,
        entity_type="proposal",
        entity_id=str(target.get("id", "")),
        route=f"/proposals?org={org_name}",
        metadata={"file_path": target.get("file_path")},
    )

    task = AgentTask(
        task_type="improvement_execution",
        description=f"改善提案の適用: {target.get('title')}",
        input={
            "repo_path": str(repo_path),
            "suggestion": target,
            "github_token": os.getenv("GITHUB_TOKEN"),
        },
    )
    orchestrator = OrchestratorAgent.create(llm_client=get_default_llm_client(settings=_load_gui_settings()))
    result = await orchestrator.run(task)
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
            route=f"/proposals?org={org_name}",
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
    }
    await _record_execution_event(
        "proposal_approved",
        str(target.get("title") or "改善提案を承認"),
        status="success",
        actor="user",
        details=result.output.get("change_summary", "") or str(target.get("description") or ""),
        org_name=org_name,
        entity_type="proposal",
        entity_id=str(target.get("id", "")),
        route=f"/proposals?org={org_name}",
        metadata={
            "file_path": target.get("file_path"),
            "branch": result.output.get("branch"),
            "pr_url": result.output.get("pr_url"),
        },
    )
    await _updates_hub.broadcast({
        "type": "task_complete",
        "status": "success",
        "title": str(target.get("title") or "改善提案を承認"),
        "details": result.output.get("change_summary", "") or str(target.get("description") or ""),
        "org_name": org_name,
        "entity_type": "proposal",
        "entity_id": str(target.get("id", "")),
        "route": f"/proposals?org={org_name}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return payload


async def _reject_proposal_internal(org_name: str, proposal_id: str) -> Dict[str, Any]:
    _, sm, target = _find_pending_proposal(org_name, proposal_id)
    sm.update_proposal_status(str(target.get("id", "")), "rejected")
    payload = {
        "status": "rejected",
        "proposal_id": str(target.get("id", "")),
        "title": target.get("title"),
    }
    await _record_execution_event(
        "proposal_rejected",
        str(target.get("title") or "改善提案を却下"),
        status="success",
        actor="user",
        details=str(target.get("description") or ""),
        org_name=org_name,
        entity_type="proposal",
        entity_id=str(target.get("id", "")),
        route=f"/proposals?org={org_name}",
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

    updated = [item for item in results if item.get("ok")]
    failed = [item for item in results if not item.get("ok")]
    return {
        "action": body.action,
        "updated": len(updated),
        "failed": len(failed),
        "results": results,
    }


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
            yield _format_sse({
                "type": "start",
                "org": req.org_name,
                "org_name": req.org_name,
                "content": f"{req.org_name} の分析を開始します",
            })
            await asyncio.sleep(0)
            yield _format_sse({"type": "progress", "message": "Loading organization...", "content": "Loading organization..."})
            await asyncio.sleep(0)
            yield _format_sse({"type": "progress", "message": "Running code review...", "content": "Running code review..."})
            await asyncio.sleep(0)
            result = await _perform_analyze(req)
            yield _format_sse({"type": "progress", "message": "Saving generated proposals...", "content": "Saving generated proposals..."})
            await asyncio.sleep(0)
            for proposal in result["generated_proposals"]:
                yield _format_sse({
                    "type": "proposal",
                    "org_name": result["org_name"],
                    "title": proposal.get("title"),
                    "file_path": proposal.get("file_path"),
                    "content": proposal.get("title") or "改善提案を生成しました",
                    "data": proposal,
                })
                await asyncio.sleep(0)
            yield _format_sse({
                "type": "done",
                "org_name": result["org_name"],
                "files_reviewed": result["files_reviewed"],
                "proposals_generated": result["proposals_generated"],
                "count": result["proposals_generated"],
                "content": f"{result['files_reviewed']} 件のファイルを確認し、{result['proposals_generated']} 件の提案を生成しました",
            })
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
        try:
            yield _format_sse({
                "type": "start",
                "goal": req.goal_text,
                "org_name": getattr(req, "org_name", None),
            })
            await asyncio.sleep(0)
            yield _format_sse({"type": "progress", "message": "Planning goal execution...", "content": "Planning goal execution..."})
            await asyncio.sleep(0)
            result = await _perform_goal_run(req)
            yield _format_sse({"type": "progress", "message": "Saving goal history...", "content": "Saving goal history..."})
            await asyncio.sleep(0)
            result_text = str(result.get("result") or result.get("summary") or "")
            yield _format_sse({
                "type": "result",
                "goal": result.get("goal") or req.goal_text,
                "org_name": result.get("org_name") or result.get("organization"),
                "result": result_text,
                "summary": result.get("summary") or result_text,
                "content": result_text,
                "data": result,
            })
            await asyncio.sleep(0)
            yield _format_sse({
                "type": "done",
                "goal": result.get("goal") or req.goal_text,
                "org_name": result.get("org_name") or result.get("organization"),
                "result": result_text,
                "content": "ゴール実行が完了しました",
            })
            await asyncio.sleep(0)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Goal stream failed", exc_info=exc)
            yield _format_sse({"type": "error", "message": _stream_error_message(exc)})
            await asyncio.sleep(0)

    return _stream_response(event_generator())


@app.post("/api/core/improve", tags=["core"])
async def api_core_improve(req: CoreImproveRequest) -> Dict[str, Any]:
    """WebGUI から RepoCorp 自身(Core)の改善を依頼する。

    内蔵のプロバイダー非依存エージェントが LLM で編集→テスト検証(反復)し、
    検証済みの変更を人間承認待ちの ImprovementProposal として登録する
    （作業ツリーへは自動適用しない）。承認は既存の提案承認フローで行う。
    """
    return await _perform_core_improve(req)


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
                    "path": str(rel),
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
async def list_chat_sessions() -> Dict[str, list[dict[str, Any]]]:
    return {"sessions": _list_sessions()}


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

    await websocket.accept()
    session = ChatSession(has_llm=_has_llm())
    await websocket.send_json({"type": "status", "has_llm": session.has_llm})

    try:
        while True:
            payload = ChatPayload.model_validate(await websocket.receive_json())
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
                await websocket.send_json({"type": "message", "role": "assistant", "content": response})
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")


@app.websocket("/ws/updates")
async def ws_updates(websocket: WebSocket) -> None:
    if not await _updates_hub.connect(websocket):
        return  # 接続上限（A9）
    await websocket.send_json({
        "type": "status",
        "status": "connected",
        "title": "リアルタイム更新に接続しました",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await _updates_hub.disconnect(websocket)
        logger.info("Updates WebSocket client disconnected")



def _require_localhost(request: Request) -> None:
    """ターミナル系エンドポイントは localhost 限定。"""
    client_host = request.client.host if request.client else None
    if not is_loopback_host(client_host):
        raise HTTPException(status_code=403, detail="ターミナルは localhost からのみ利用できます。")


@app.get("/api/terminal/sessions", tags=["terminal"])
async def api_list_terminal_sessions(request: Request) -> Dict[str, Any]:
    """埋め込みターミナルのワークスペース一覧（cmux 縦タブ用）。"""
    _require_localhost(request)
    return {"sessions": _terminal_manager.list()}


@app.post("/api/terminal/sessions", tags=["terminal"])
async def api_create_terminal_session(request: Request, body: TerminalCreateRequest) -> Dict[str, Any]:
    """ターミナルのワークスペースを作成する。

    cli_tool を指定すると CLI 実行モードとして外部コーディングCLIを起動する。
    command 未指定なら既定シェルを起動する。cwd 既定は RepoCorp リポジトリ。
    """
    _require_localhost(request)
    try:
        session = _terminal_manager.create(
            name=body.name,
            cwd=body.cwd,
            command=body.command,
            cli_tool=body.cli_tool,
            settings=_load_gui_settings(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"ターミナル起動に失敗しました: {exc}") from exc
    return session.meta()


@app.patch("/api/terminal/sessions/{session_id}", tags=["terminal"])
async def api_rename_terminal_session(
    request: Request, session_id: str, body: TerminalRenameRequest
) -> Dict[str, Any]:
    """ターミナルのワークスペース名を変更する（C11）。"""
    _require_localhost(request)
    if not _terminal_manager.rename(session_id, body.name):
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    session = _terminal_manager.get(session_id)
    return session.meta() if session else {"status": "renamed", "session_id": session_id}


@app.delete("/api/terminal/sessions/{session_id}", tags=["terminal"])
async def api_kill_terminal_session(request: Request, session_id: str) -> Dict[str, Any]:
    """ターミナルのワークスペースを終了する。"""
    _require_localhost(request)
    killed = _terminal_manager.kill(session_id)
    if not killed:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    return {"status": "killed", "session_id": session_id}


@app.websocket("/ws/terminal/{session_id}")
async def ws_terminal(websocket: WebSocket, session_id: str) -> None:
    """PTY とブラウザ(xterm.js)を双方向接続する。localhost 限定 + Origin 検証。"""
    client_host = websocket.client.host if websocket.client else None
    origin = websocket.headers.get("origin")
    if not is_loopback_host(client_host) or not is_allowed_origin(origin):
        await websocket.close(code=4403)
        return

    session = _terminal_manager.get(session_id)
    if session is None:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "session not found"})
        await websocket.close()
        return

    await websocket.accept()
    loop = asyncio.get_running_loop()
    session.start_reader(loop)
    queue = session.subscribe()

    if session.scrollback:
        await websocket.send_bytes(bytes(session.scrollback))
    if session.status == "exited":
        await websocket.send_json({"type": "exit", "exit_code": session.exit_code})

    async def _pump_output() -> None:
        while True:
            kind, payload = await queue.get()
            if kind == "data":
                await websocket.send_bytes(payload)
            elif kind == "exit":
                await websocket.send_json({"type": "exit", "exit_code": payload})

    output_task = asyncio.create_task(_pump_output())
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            text = message.get("text")
            if text is not None:
                handled = False
                if text.startswith("{"):
                    try:
                        control = json.loads(text)
                        if control.get("type") == "resize":
                            session.resize(int(control.get("rows", 24)), int(control.get("cols", 80)))
                            handled = True
                        elif control.get("type") == "input":
                            session.write(str(control.get("data", "")))
                            handled = True
                    except (json.JSONDecodeError, ValueError, TypeError):
                        handled = False
                if not handled:
                    session.write(text)
            elif message.get("bytes") is not None:
                session.write(message["bytes"].decode("utf-8", "ignore"))
    except WebSocketDisconnect:
        pass
    finally:
        output_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await output_task
        session.unsubscribe(queue)


def run_server(host: str | None = None, port: int = 7860) -> None:
    import uvicorn

    # 構造化ログ/レベルを環境変数に応じて設定（J2。REPOCORP_LOG_FORMAT=json 等）。
    configure_logging()

    # 既定は localhost のみ（A1）。環境変数 REPOCORP_HOST で上書き可。
    resolved_host = host or os.environ.get("REPOCORP_HOST") or "127.0.0.1"

    print("\nRepoCorp AI Web GUI を起動しています...")
    print(f"   URL: http://localhost:{port}")
    print(f"   プラットフォーム: {PlatformStateManager().platform_home}")
    if resolved_host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            f"   [警告] {resolved_host} で全インターフェースに公開します。"
            "埋め込みターミナル(実シェル)も到達可能になるため、信頼できるネットワークでのみ使用してください。"
        )
    uvicorn.run(app, host=resolved_host, port=port)


# --- SPA routes (must be last so API routes take precedence) ---

@app.get("/")
async def root():
    return _spa_index_response()


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """非APIのクライアントサイドルートに React SPA を返す。

    未知の /api/* ・ /ws/* はSPAで握りつぶさず 404(JSON) を返す
    （API の 404 挙動を正しく保つ）。
    """
    if full_path == "api" or full_path.startswith(("api/", "ws/")):
        raise HTTPException(status_code=404, detail="Not Found")
    return _spa_index_response()
