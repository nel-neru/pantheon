"""
Pantheon - System Bootstrap

初回起動時に Meta-Improvement Organization を自動作成する。
Meta-Improvement Organization は Pantheon システム自体の継続的改善を担う。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from core.models.organization import Organization, OrganizationStatus
from core.org_factory import create_organization_from_template

logger = logging.getLogger(__name__)

META_ORG_NAME = "Meta-Improvement Organization"
META_ORG_PURPOSE = "Pantheon システム全体の強化・改善・自己進化を担う中核 Organization"
META_TEMPLATE_PATH = Path(__file__).parent.parent / "config" / "departments" / "meta_improvement.yaml"


def ensure_meta_improvement_org(
    state_manager,  # PlatformStateManager | RepoStateManager 両対応
) -> Organization:
    """
    Meta-Improvement Organization が未作成なら自動作成して保存する。
    既に存在する場合はそのまま返す。
    """
    existing = state_manager.load_organization_by_name(META_ORG_NAME)
    if existing:
        if not existing.is_system:
            existing.is_system = True
            state_manager.save_organization(existing)
        logger.debug("Meta-Improvement Organization already exists: %s", existing.id)
        return existing

    logger.info("Creating Meta-Improvement Organization for the first time...")
    org = create_organization_from_template(
        name=META_ORG_NAME,
        purpose=META_ORG_PURPOSE,
        template_path=META_TEMPLATE_PATH,
        status=OrganizationStatus.ACTIVE,
        is_system=True,
    )
    state_manager.save_organization(org)
    print(f"[Bootstrap] Meta-Improvement Organization を初期化しました (ID: {org.id})")
    return org


def bootstrap_platform(core_repo_path: Optional[Path] = None) -> "PlatformStateManager":
    """
    グローバルプラットフォームを初期化し、PlatformStateManager を返す。
    Meta-Improvement Organization を自動作成し、Core リポジトリ自体を担当させる。

    Args:
        core_repo_path: Pantheon リポジトリのパス。
                        None の場合はこのファイルの親ディレクトリを自動検出。
    """
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager()
    meta = ensure_meta_improvement_org(psm)

    # Meta-Improvement Org に Core リポジトリを紐付ける（未設定の場合のみ）
    if not meta.target_repo_path:
        if core_repo_path is None:
            core_repo_path = Path(__file__).parent.parent.resolve()
        meta.target_repo_path = str(core_repo_path)
        psm.save_organization(meta)
        logger.info(
            "Meta-Improvement Org wired to Core repo: %s", core_repo_path
        )

    if not psm.is_initialized():
        psm.initialize(meta_improvement_org_id=str(meta.id))

    # デフォルトポリシーファイルを生成（未作成の場合のみ）
    policy_path = psm.platform_home / "policy.yaml"
    if not policy_path.exists():
        from core.policy.engine import PolicyEngine
        PolicyEngine().save_default_policy(policy_path)
        logger.info("Default policy.yaml created at %s", policy_path)

    return psm
