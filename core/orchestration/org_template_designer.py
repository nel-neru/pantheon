"""OrganizationTemplateDesigner — LLM-designed, schema-validated org templates.

Given an industry genre (ai / side_business / video_edit / game_dev / …), this
asks the local ``claude`` CLI to design a Division/Team/required-skill structure,
validates it against the same schema ``org_factory`` consumes, and saves it to
``config/departments/generated/<genre>.yaml``. When ``claude`` is unavailable it
falls back to a deterministic generic template so org creation never blocks.

This is the engine behind "ジャンル別エキスパート組織の量産": one genre →
one validated departments template → a ready Organization.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.models.organization import AgentSkill, DivisionType

logger = logging.getLogger(__name__)

GENERATED_DIRNAME = "generated"
MAX_DIVISIONS = 5
MAX_TEAMS_PER_DIVISION = 3

_VALID_SKILLS = {s.value for s in AgentSkill}
_VALID_DIVISION_TYPES = {d.value for d in DivisionType}

_DESIGN_SYSTEM = (
    "あなたは組織設計の専門家です。指定された業界ジャンルの個人開発者向け自律 AI 組織の"
    "部門(Division)・チーム(Team)構成を設計します。出力は厳密に JSON のみ（説明文なし）。"
    "形式:\n"
    '{"departments": [{"name": "部門名", "type": "<division_type>", "mission": "...", '
    '"teams": [{"name": "チーム名", "mission": "...", "required_skills": ["skill1","skill2"]}]}]}\n'
    f"type は次のいずれか: {sorted(_VALID_DIVISION_TYPES)}\n"
    f"required_skills は次から 2〜3 個選ぶ: {sorted(_VALID_SKILLS)}\n"
    "部門は最大 5、各部門のチームは最大 3。実在しないスキル/タイプは使わない。"
)


def generated_dir() -> Path:
    # ユーザー固有の生成物なので platform home（~/.pantheon）配下に書く。
    # resource_path は読み取り専用の同梱領域（frozen 時 _MEIPASS）を指すため使わない。
    from core.platform.state import get_platform_home

    return Path(get_platform_home()) / "config" / "departments" / GENERATED_DIRNAME


def _coerce_skills(raw: Any) -> List[str]:
    """有効スキルだけを 2〜3 個に正規化する（不足は汎用スキルで補う）。"""
    skills = [s for s in (raw or []) if isinstance(s, str) and s in _VALID_SKILLS]
    # 重複排除（順序保持）
    seen: set[str] = set()
    skills = [s for s in skills if not (s in seen or seen.add(s))]
    fillers = ["deep_research", "knowledge_curation", "strategic_planning"]
    for f in fillers:
        if len(skills) >= 2:
            break
        if f not in skills:
            skills.append(f)
    return skills[:3]


def validate_departments(data: Any) -> List[Dict[str, Any]]:
    """LLM 出力を org_factory が読める departments スキーマに正規化・検証する。

    不正な type は org_evolution に寄せ、無効スキルは除去、空構造は弾く。
    SpecialistAgent.skills の 2〜3 個制約に合わせて required_skills を正規化する。
    """
    if isinstance(data, dict):
        departments = data.get("departments", [])
    elif isinstance(data, list):
        departments = data
    else:
        return []
    if not isinstance(departments, list):
        return []

    out: List[Dict[str, Any]] = []
    for dept in departments[:MAX_DIVISIONS]:
        if not isinstance(dept, dict) or not dept.get("name"):
            continue
        dtype = dept.get("type")
        if dtype not in _VALID_DIVISION_TYPES:
            dtype = DivisionType.ORG_EVOLUTION.value
        teams_out: List[Dict[str, Any]] = []
        for team in (dept.get("teams") or [])[:MAX_TEAMS_PER_DIVISION]:
            if not isinstance(team, dict) or not team.get("name"):
                continue
            teams_out.append(
                {
                    "name": str(team["name"]),
                    "mission": str(team.get("mission", "")),
                    "required_skills": _coerce_skills(team.get("required_skills")),
                }
            )
        if not teams_out:
            continue
        out.append(
            {
                "name": str(dept["name"]),
                "type": dtype,
                "mission": str(dept.get("mission", "")),
                "teams": teams_out,
            }
        )
    return out


def _deterministic_template(genre: str) -> List[Dict[str, Any]]:
    """claude 不在時の汎用テンプレ（content_operations 相当の安全な雛形）。"""
    return [
        {
            "name": f"{genre} 制作部",
            "type": DivisionType.CONTENT_PRODUCTION.value,
            "mission": f"{genre} ドメインの価値あるアウトプットを継続的に企画・制作する",
            "teams": [
                {
                    "name": "Strategy Team",
                    "mission": "市場・ニッチ選定と計画",
                    "required_skills": ["strategic_planning", "deep_research"],
                },
                {
                    "name": "Production Team",
                    "mission": "制作と品質管理",
                    "required_skills": ["content_strategy", "knowledge_curation"],
                },
            ],
        },
        {
            "name": f"{genre} グロース部",
            "type": DivisionType.AUDIENCE_DEVELOPMENT.value,
            "mission": "チャネル横断で需要を獲得・拡大する",
            "teams": [
                {
                    "name": "Growth Team",
                    "mission": "集客と分析",
                    "required_skills": ["audience_growth", "performance_analysis"],
                }
            ],
        },
    ]


def _extract_json(text: str) -> Optional[Any]:
    """LLM 出力から JSON オブジェクトを抽出する（コードフェンス等を除去）。

    fence の除去は `\\s*`+lazy の重複（ReDoS）を避けるため改行アンカーにする。
    まず最初の '{' から JSONDecoder.raw_decode で正しく閉じた範囲だけを取り、
    末尾に余計なプロンプトが続いても安全にパースする。
    """
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\n(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    if start == -1:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(candidate[start:])
        return obj
    except ValueError:
        return None


async def design_departments(genre: str) -> List[Dict[str, Any]]:
    """ジャンルから departments を設計する（claude 優先、検証済み・フォールバック付き）。"""
    genre = (genre or "general").strip() or "general"
    from core.runtime.claude_code import claude_available

    if claude_available():
        try:
            from core.llm import LLMMessage, get_llm_provider

            provider = get_llm_provider()
            response = await provider.generate(
                messages=[
                    LLMMessage(role="system", content=_DESIGN_SYSTEM),
                    LLMMessage(
                        role="user",
                        content=f"業界ジャンル: {genre}。個人開発者向けの自律 AI 組織を設計してください。",
                    ),
                ],
                temperature=0.4,
                max_tokens=1500,
                task_type="meta_improvement",
            )
            parsed = _extract_json(getattr(response, "content", "") or "")
            validated = validate_departments(parsed)
            if validated:
                return validated
            logger.info("org design for '%s' did not validate — using fallback", genre)
        except Exception as exc:  # noqa: BLE001
            logger.info("org design via claude failed for '%s' (%s) — using fallback", genre, exc)
    return _deterministic_template(genre)


def _write_template_yaml(path: Path, genre: str, departments: List[Dict[str, Any]]) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": {"industry_genre": genre}, "departments": departments}
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def save_generated_template(genre: str, departments: List[Dict[str, Any]]) -> Path:
    """検証済み departments を ``<platform_home>/config/departments/generated/<genre>.yaml`` に保存する。"""
    safe = re.sub(r"[^a-z0-9_]+", "_", genre.lower()).strip("_") or "general"
    path = generated_dir() / f"{safe}.yaml"
    _write_template_yaml(path, genre, departments)
    return path


async def design_and_save(genre: str) -> tuple[Path, List[Dict[str, Any]]]:
    """設計→検証→保存をまとめて行い、(保存先, departments) を返す。

    通常の保存に失敗（権限・容量等）しても、検証済みの departments は一時ファイルに
    退避して必ず読み取り可能なパスを返す（org create を I/O エラーで止めない）。
    """
    departments = await design_departments(genre)
    try:
        path = save_generated_template(genre, departments)
    except OSError as exc:
        import tempfile

        logger.warning("failed to save generated template (%s) — using temp file", exc)
        fd, tmp = tempfile.mkstemp(prefix="org_template_", suffix=".yaml")
        import os as _os

        _os.close(fd)
        path = Path(tmp)
        _write_template_yaml(path, genre, departments)
    return path, departments
