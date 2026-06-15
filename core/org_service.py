"""OrgService — Organization 生成の唯一の入口（CLI / GUI / エージェント共通）。

組織の作成経路を一本化するための薄いサービス層。``core/org_factory`` の各 builder を
呼び分け、``isolation_level`` などを第一級引数として受け取り、必要なら ``save_organization``
まで一括で行う。CLI・Web API・自律パイプラインが**全てここを通る**ことで、
「GUI から作ると standard、CLI だと external」のような経路差（管理破綻の温床）を無くす。

恒久原則: 新規事業＝外部 Organization（``isolation_level="external"`` ＋業務は兄弟 repo）。
詳細は ``docs/architecture/organization_boundaries.md``。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from core.models.organization import Organization, OrganizationStatus
from core.org_factory import create_default_organization, create_organization_from_template

if TYPE_CHECKING:
    from core.platform.state import PlatformStateManager

VALID_ISOLATION_LEVELS = ("core", "standard", "external")
VALID_MANAGEMENT_MODES = ("repo", "workspace")


def normalize_isolation_level(value: Optional[str]) -> str:
    """未知/None は ``standard`` に正規化する（モデルの validator と一致）。"""
    return value if value in VALID_ISOLATION_LEVELS else "standard"


def create_org(
    name: str,
    purpose: str = "",
    *,
    isolation_level: str = "standard",
    allowed_path_scope: Optional[List[str]] = None,
    target_repo_path: str | Path | None = None,
    management_mode: Optional[str] = None,
    workspace_path: str | Path | None = None,
    industry_genre: Optional[str] = None,
    persona_id: Optional[str] = None,
    design_style: Optional[str] = None,
    template_path: str | Path | None = None,
    status: OrganizationStatus = OrganizationStatus.INCUBATING,
    is_system: bool = False,
    persist: bool = True,
    psm: "Optional[PlatformStateManager]" = None,
) -> Organization:
    """Organization を 1 つ生成して（既定で）永続化する単一経路。

    - ``template_path`` 指定時はテンプレから、未指定なら最小構成で作成する。
    - ``isolation_level`` は全経路でここを通すことで第一級に扱われる（GUI も CLI も同一）。
    - ``persist=False`` で保存せずオブジェクトのみ返す（呼び出し元が保存制御したい場合）。
    - ``psm`` 未指定時は ``PlatformStateManager()`` を生成して保存する。
    """
    iso = normalize_isolation_level(isolation_level)

    if template_path is not None:
        org = create_organization_from_template(
            name,
            purpose,
            Path(template_path),
            status=status,
            is_system=is_system,
            repo_path=target_repo_path,
            isolation_level=iso,
            allowed_path_scope=allowed_path_scope,
            industry_genre=industry_genre,
            persona_id=persona_id,
            design_style=design_style,
        )
    else:
        org = create_default_organization(
            name,
            purpose,
            status=status,
            is_system=is_system,
            repo_path=target_repo_path,
            isolation_level=iso,
            allowed_path_scope=allowed_path_scope,
        )
        # 最小構成 builder は genre/persona/design を受けないため後付けで反映する。
        if industry_genre:
            org.industry_genre = str(industry_genre)
        if persona_id:
            org.persona_id = str(persona_id)
        if design_style:
            org.design_style = str(design_style)

    if management_mode in VALID_MANAGEMENT_MODES:
        org.management_mode = management_mode
    if workspace_path:
        org.workspace_path = str(workspace_path)

    if persist:
        if psm is None:
            from core.platform.state import PlatformStateManager

            psm = PlatformStateManager()
        psm.save_organization(org)

    return org
