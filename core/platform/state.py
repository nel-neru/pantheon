"""
PlatformStateManager

Core（本社）のグローバルストア（~/.repocorp/）を管理する。
複数の Organization（子会社）を横断的に登録・管理するプラットフォーム層。

ストアの場所は REPOCORP_HOME 環境変数で変更可能（デフォルト: ~/.repocorp/）。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.io_utils import atomic_write_text
from core.models.organization import Organization


def get_platform_home() -> Path:
    """
    プラットフォームストアのルートディレクトリを返す。
    REPOCORP_HOME 環境変数が設定されていればそちらを使う。
    """
    env = os.environ.get("REPOCORP_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".repocorp"


class PlatformStateManager:
    """
    Core（本社）のグローバルプラットフォームストアを管理する。

    ディレクトリ構成:
      ~/.repocorp/
      ├── platform.json          - プラットフォーム設定・メタ情報
      ├── organizations/         - Organization（子会社）の定義
      │   └── <uuid>.json
      └── knowledge/             - 全 Org 共有ナレッジ
          └── <uuid>.json
    """

    PLATFORM_VERSION = "1.0.0"

    def __init__(self, platform_home: Optional[Path] = None):
        self.platform_home = platform_home or get_platform_home()
        self.orgs_dir = self.platform_home / "organizations"
        self.knowledge_dir = self.platform_home / "knowledge"
        self.platform_file = self.platform_home / "platform.json"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for d in [self.platform_home, self.orgs_dir, self.knowledge_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ---- プラットフォーム設定 ----

    def is_initialized(self) -> bool:
        return self.platform_file.exists()

    def initialize(self, meta_improvement_org_id: str = "") -> None:
        """プラットフォームを初期化する（初回のみ）"""
        if self.is_initialized():
            return
        data: Dict[str, Any] = {
            "version": self.PLATFORM_VERSION,
            "initialized_at": datetime.now(timezone.utc).isoformat(),
            "meta_improvement_org_id": meta_improvement_org_id,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        atomic_write_text(self.platform_file, json.dumps(data, ensure_ascii=False, indent=2))

    def load_platform_config(self) -> Dict[str, Any]:
        if not self.platform_file.exists():
            return {}
        return json.loads(self.platform_file.read_text(encoding="utf-8"))

    def save_platform_config(self, config: Dict[str, Any]) -> None:
        config["last_updated"] = datetime.now(timezone.utc).isoformat()
        atomic_write_text(self.platform_file, json.dumps(config, ensure_ascii=False, indent=2))

    def set_meta_improvement_org_id(self, org_id: str) -> None:
        config = self.load_platform_config()
        config["meta_improvement_org_id"] = org_id
        self.save_platform_config(config)

    # ---- Organization 管理 ----

    def save_organization(self, org: Organization) -> None:
        """Organization をグローバルストアに保存する"""
        path = self.orgs_dir / f"{org.id}.json"
        atomic_write_text(path, org.model_dump_json(indent=2))

    def load_organizations(self) -> List[Organization]:
        """全 Organization を読み込む"""
        result = []
        for f in sorted(self.orgs_dir.glob("*.json")):
            try:
                result.append(Organization.model_validate_json(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return result

    def load_organization_by_name(self, name: str) -> Optional[Organization]:
        for org in self.load_organizations():
            if org.name == name:
                return org
        return None

    def load_organization_by_id(self, org_id: str) -> Optional[Organization]:
        path = self.orgs_dir / f"{org_id}.json"
        if not path.exists():
            return None
        try:
            return Organization.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def remove_organization(self, org_id: str) -> bool:
        path = self.orgs_dir / f"{org_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    # ---- 各 Org のリポジトリ内 StateManager を取得 ----

    def get_org_state_manager(self, org: Organization):
        """
        Org の target_repo_path 内の .repocorp/ を管理する
        RepoStateManager を返す。target_repo_path が未設定の場合は platform_home を使う。
        """
        from core.state.manager import RepoStateManager

        repo_path = Path(org.target_repo_path) if org.target_repo_path else self.platform_home
        return RepoStateManager(repo_path, org.name)

    # ---- 共有ナレッジ ----

    def save_shared_insight(
        self,
        title: str,
        content: str,
        source_org: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        from core.knowledge.manager import KnowledgeManager
        km = KnowledgeManager(self.platform_home)
        return km.save_insight(title, content, tags=tags or [], source_org=source_org)

    def get_shared_insights(
        self, tags: Optional[List[str]] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        from core.knowledge.manager import KnowledgeManager
        km = KnowledgeManager(self.platform_home)
        return km.get_insights(limit=limit, tags=tags)
