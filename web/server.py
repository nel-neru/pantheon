"""
RepoCorp AI - Web Server (Platform Level)

PlatformStateManager を使ってプラットフォーム全体を管理する FastAPI サーバー。
"""

from __future__ import annotations

import base64
import asyncio
import colorsys
import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.models.organization import ImprovementProposal, is_active_improvement_proposal_status
from core.platform.state import PlatformStateManager, get_platform_home

logger = logging.getLogger(__name__)
app = FastAPI(title="RepoCorp AI Platform", version="2.0.0")

STATIC_DIR = Path(__file__).parent / "static"
DIST_DIR = Path(__file__).parent / "dist"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
SYSTEM_ORG_NAMES = {"Meta-Improvement Organization", "RepoCorp Core", "meta-improvement"}
SETTINGS_FILE = Path.home() / ".repocorp" / "gui_settings.json"
CHAT_SESSIONS_DIR = Path.home() / ".repocorp" / "chat_sessions"
CHAT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
_PROVIDER_KEY_MAPPING = {
    "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "groq": ("groq_api_key", "GROQ_API_KEY"),
    "github_models": ("github_models_api_key", "GITHUB_TOKEN"),
    "gemini": ("gemini_api_key", "GOOGLE_API_KEY"),
}
FALLBACK_MODELS = {
    "anthropic": [
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1",
        "o1-mini",
        "o3-mini",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ],
    "github_models": [
        "gpt-4o",
        "gpt-4o-mini",
        "claude-3-5-sonnet",
        "meta-llama-3-70b-instruct",
        "mistral-large",
        "phi-3-medium-instruct-128k",
        "ai21-jamba-instruct",
    ],
    "gemini": [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-pro-exp",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ],
}
_model_cache: dict[str, tuple[list[str], float]] = {}
_CACHE_TTL = 300

# Serve React build (dist/) when available, fallback to legacy static/
_serve_dir = DIST_DIR if DIST_DIR.is_dir() else STATIC_DIR
app.mount("/assets", StaticFiles(directory=_serve_dir / "assets" if (DIST_DIR / "assets").is_dir() else STATIC_DIR), name="assets")


def _load_gui_settings() -> Dict[str, Any]:
    """GUI 設定ファイルを読み込む（存在しなければデフォルト値を返す）"""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "llm_provider": os.getenv("REPOCORP_DEFAULT_LLM_PROVIDER", "anthropic"),
        "llm_model": os.getenv("REPOCORP_DEFAULT_MODEL", "claude-3-5-sonnet-20241022"),
        "anthropic_api_key": "",
        "openai_api_key": "",
        "groq_api_key": "",
        "github_models_api_key": "",
        "gemini_api_key": "",
        "daemon_interval": 3600,
        "daemon_max_files": 10,
    }


def _save_gui_settings(data: Dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")



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


class OrgCreateRequest(BaseModel):
    name: str
    purpose: str = ""
    target_repo_path: str = ""


class OrgIconRequest(BaseModel):
    icon_data: str


class AnalyzeRequest(BaseModel):
    org_name: str
    max_files: int = Field(default=15, ge=1, le=50)


class ProposalApproveRequest(BaseModel):
    pass


class GoalRunRequest(BaseModel):
    goal_text: str


class DaemonStartRequest(BaseModel):
    interval: int = Field(default=3600, ge=1)
    max_files: int = Field(default=10, ge=1)


class TaskQueueRequest(BaseModel):
    task_type: str
    org_name: str
    description: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=1, le=10)


class ChatPayload(BaseModel):
    message: str


class ChatRequest(BaseModel):
    message: str
    session_context: list[dict[str, Any]] = Field(default_factory=list)


class ChatSessionCreate(BaseModel):
    name: str = ""


class ChatSessionUpdate(BaseModel):
    name: str


class ChatMessageCreate(BaseModel):
    content: str
    role: str = "user"


class KnowledgeFileUpdate(BaseModel):
    content: str


class KnowledgeFileCreate(BaseModel):
    name: str
    content: str = ""



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



def _load_goal_history() -> list[dict[str, Any]]:
    path = _goal_history_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []



def _save_goal_history(record: dict[str, Any], keep: int = 12) -> None:
    history = [record, *_load_goal_history()][:keep]
    _goal_history_path().write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )



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
    return {
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



def _stream_error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)



async def _perform_analyze(req: AnalyzeRequest) -> dict[str, Any]:
    from agents.base import AgentTask
    from agents.code_review_agent import CodeReviewAgent
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
    agent = CodeReviewAgent(specialist)
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
        generated_proposals.append(_serialize_generated_proposal(proposal))

    return {
        "org_name": org.name,
        "files_reviewed": result.output.get("files_reviewed", 0),
        "proposals_generated": len(generated_proposals),
        "generated_proposals": generated_proposals,
    }



async def _perform_goal_run(req: GoalRunRequest) -> dict[str, Any]:
    from core.goals.abstract_goal_pipeline import AbstractGoalPipeline

    pipeline = AbstractGoalPipeline()
    result = await pipeline.run(req.goal_text)
    record = _goal_record(req, result)
    _save_goal_history(record)
    return record



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
    }


@app.get("/api/platform/status")
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


@app.get("/api/daemon/status")
async def api_daemon_status() -> Dict[str, Any]:
    return _daemon_status_payload()


@app.post("/api/daemon/start")
async def api_daemon_start(req: DaemonStartRequest | None = None) -> Dict[str, Any]:
    req = req or DaemonStartRequest()
    pid_file, log_file = _daemon_paths()
    pid = _read_daemon_pid(pid_file)
    if pid is not None and _is_process_running(pid):
        return {
            "status": "already_running",
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
    return {
        "status": "started",
        "running": True,
        "pid": proc.pid,
        "log_path": str(log_file),
        "interval": req.interval,
        "max_files": req.max_files,
    }


@app.post("/api/daemon/stop")
async def api_daemon_stop() -> Dict[str, Any]:
    pid_file, log_file = _daemon_paths()
    pid = _read_daemon_pid(pid_file)
    if pid is None:
        pid_file.unlink(missing_ok=True)
        return {
            "status": "not_running",
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
        "running": False,
        "pid": pid,
        "log_path": str(log_file),
    }


@app.post("/api/init")
async def api_init_platform() -> Dict[str, Any]:
    from core.bootstrap import bootstrap_platform

    already_initialized = _psm().is_initialized()
    psm = bootstrap_platform()
    meta_id = psm.load_platform_config().get("meta_improvement_org_id")
    meta_name = None
    if meta_id:
        meta = psm.load_organization_by_id(meta_id)
        meta_name = meta.name if meta else None
    return {
        "status": "already_initialized" if already_initialized else "initialized",
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
    return queue.add_task(
        task_type=body.task_type,
        org_name=body.org_name,
        description=body.description,
        payload=body.payload,
        priority=body.priority,
    )


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
    if not queue.cancel_task(task_id):
        raise HTTPException(status_code=400, detail="タスクをキャンセルできません（実行中または存在しない）")
    return {"status": "cancelled", "task_id": task_id}


class SettingsUpdateRequest(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    github_models_api_key: str | None = None
    gemini_api_key: str | None = None
    daemon_interval: int | None = None
    daemon_max_files: int | None = None


@app.get("/api/settings")
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
        "daemon_interval": s.get("daemon_interval", 3600),
        "daemon_max_files": s.get("daemon_max_files", 10),
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
    if req.daemon_interval is not None:
        s["daemon_interval"] = req.daemon_interval
    if req.daemon_max_files is not None:
        s["daemon_max_files"] = req.daemon_max_files

    _save_gui_settings(s)
    return {"status": "saved", "has_llm": _has_llm(s)}


@app.get("/api/providers/{provider}/models")
async def get_provider_models(provider: str) -> Dict[str, Any]:
    """プロバイダーから利用可能なモデル一覧を取得する。"""
    cached = _get_cached_models(provider)
    if cached is not None:
        return {"provider": provider, "models": cached, "source": "cache"}

    if provider not in FALLBACK_MODELS:
        return {"provider": provider, "models": [], "source": "unknown"}

    settings = _load_gui_settings()
    models: list[str] | None = None
    source = "fallback"

    try:
        if provider == "anthropic":
            api_key = _get_provider_api_key(settings, provider)
            if api_key:
                import anthropic

                client = anthropic.Anthropic(api_key=api_key)
                response = client.models.list(limit=100)
                models = sorted(model.id for model in response.data if getattr(model, "id", ""))
                source = "api"

        elif provider == "openai":
            api_key = _get_provider_api_key(settings, provider)
            if api_key:
                from openai import OpenAI

                client = OpenAI(api_key=api_key)
                response = client.models.list()
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
                response = client.models.list()
                models = sorted(model.id for model in response.data if getattr(model, "id", ""))
                source = "api"

        elif provider == "github_models":
            github_token = _get_provider_api_key(settings, provider)
            if github_token:
                import httpx

                response = httpx.get(
                    "https://models.inference.ai.azure.com/models",
                    headers={"Authorization": f"Bearer {github_token}"},
                    timeout=10,
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

                fetched = GeminiProvider.list_models(api_key)
                if fetched:
                    models = fetched
                    source = "api"

    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch models for %s: %s", provider, exc)

    if not models:
        models = list(FALLBACK_MODELS.get(provider, []))
        source = "fallback"

    _set_cached_models(provider, models)
    return {"provider": provider, "models": models, "source": source}


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
    return {"status": "deleted", "name": org_name}


class OrgUpdateRequest(BaseModel):
    purpose: str | None = None
    target_repo_path: str | None = None


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
    return [proposal for proposal in proposals if is_active_improvement_proposal_status(proposal.get("status"))]


@app.post("/api/proposals/{org_name}/{proposal_id}/approve")
async def api_approve_proposal(
    org_name: str,
    proposal_id: str,
    req: ProposalApproveRequest | None = None,
) -> Dict[str, Any]:
    from agents.base import AgentTask
    from agents.orchestrator_agent import OrchestratorAgent

    psm, sm, target = _find_pending_proposal(org_name, proposal_id)
    if not target.get("file_path"):
        raise HTTPException(status_code=400, detail="この提案は file_path がないため承認できません")

    org = _find_org(org_name)
    repo_path = Path(org.target_repo_path) if org.target_repo_path else psm.platform_home
    sm.update_proposal_status(str(target.get("id", "")), "in_progress")

    task = AgentTask(
        task_type="improvement_execution",
        description=f"改善提案の適用: {target.get('title')}",
        input={
            "repo_path": str(repo_path),
            "suggestion": target,
            "github_token": os.getenv("GITHUB_TOKEN"),
        },
    )
    result = await OrchestratorAgent.create().run(task)
    if not result.success:
        sm.update_proposal_status(str(target.get("id", "")), "failed")
        raise HTTPException(status_code=500, detail=result.error or "改善提案の適用に失敗しました")

    next_status = "done"
    sm.update_proposal_status(str(target.get("id", "")), next_status)
    return {
        "status": next_status,
        "proposal_id": str(target.get("id", "")),
        "title": target.get("title"),
        "change_summary": result.output.get("change_summary", ""),
        "branch": result.output.get("branch"),
        "pr_url": result.output.get("pr_url"),
        "output": result.output,
    }


@app.post("/api/proposals/{org_name}/{proposal_id}/reject")
async def api_reject_proposal(org_name: str, proposal_id: str) -> Dict[str, Any]:
    _, sm, target = _find_pending_proposal(org_name, proposal_id)
    sm.update_proposal_status(str(target.get("id", "")), "rejected")
    return {
        "status": "rejected",
        "proposal_id": str(target.get("id", "")),
        "title": target.get("title"),
    }


@app.post("/api/analyze")
async def api_analyze(req: AnalyzeRequest) -> Dict[str, Any]:
    """Organization の担当リポジトリを分析して改善提案を生成"""
    return await _perform_analyze(req)


@app.post("/api/analyze/stream")
async def api_analyze_stream(req: AnalyzeRequest) -> StreamingResponse:
    async def event_generator():
        try:
            yield _format_sse({"type": "start", "org": req.org_name})
            await asyncio.sleep(0)
            yield _format_sse({"type": "progress", "message": "Loading organization..."})
            await asyncio.sleep(0)
            yield _format_sse({"type": "progress", "message": "Running code review..."})
            await asyncio.sleep(0)
            result = await _perform_analyze(req)
            yield _format_sse({"type": "progress", "message": "Saving generated proposals..."})
            await asyncio.sleep(0)
            for proposal in result["generated_proposals"]:
                yield _format_sse({"type": "proposal", "data": proposal})
                await asyncio.sleep(0)
            yield _format_sse({"type": "done", "count": result["proposals_generated"]})
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


@app.get("/api/skills")
async def api_skills() -> List[Dict[str, Any]]:
    from core.loaders.skill_loader import SkillLoader

    return [_serialize_skill(defn) for defn in SkillLoader().all()]


@app.post("/api/goals/run")
async def api_run_goal(req: GoalRunRequest) -> Dict[str, Any]:
    return await _perform_goal_run(req)


@app.post("/api/goals/stream")
async def api_goals_stream(req: GoalRunRequest) -> StreamingResponse:
    async def event_generator():
        try:
            yield _format_sse({"type": "start", "goal": req.goal_text})
            await asyncio.sleep(0)
            yield _format_sse({"type": "progress", "message": "Planning goal execution..."})
            await asyncio.sleep(0)
            result = await _perform_goal_run(req)
            yield _format_sse({"type": "progress", "message": "Saving goal history..."})
            await asyncio.sleep(0)
            yield _format_sse({"type": "result", "data": result})
            await asyncio.sleep(0)
            yield _format_sse({"type": "done"})
            await asyncio.sleep(0)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Goal stream failed", exc_info=exc)
            yield _format_sse({"type": "error", "message": _stream_error_message(exc)})
            await asyncio.sleep(0)

    return _stream_response(event_generator())


@app.get("/api/goals/history")
async def api_goal_history() -> List[Dict[str, Any]]:
    return _load_goal_history()


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



def run_server(host: str = "0.0.0.0", port: int = 7860) -> None:
    import uvicorn

    print("\nRepoCorp AI Web GUI を起動しています...")
    print(f"   URL: http://localhost:{port}")
    print(f"   プラットフォーム: {PlatformStateManager().platform_home}")
    uvicorn.run(app, host=host, port=port)


# --- SPA routes (must be last so API routes take precedence) ---

@app.get("/")
async def root():
    index = _serve_dir / "index.html"
    return FileResponse(index if index.exists() else STATIC_DIR / "index.html")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """Serve React SPA for all non-API client-side routes."""
    index = _serve_dir / "index.html"
    return FileResponse(index if index.exists() else STATIC_DIR / "index.html")
