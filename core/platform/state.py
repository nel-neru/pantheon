"""
PlatformStateManager

Core（本社）のグローバルストア（~/.pantheon/）を管理する。
複数の Organization（子会社）を横断的に登録・管理するプラットフォーム層。

ストアの場所は PANTHEON_HOME 環境変数で変更可能（デフォルト: ~/.pantheon/）。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.models.organization import Organization

logger = logging.getLogger(__name__)

# 同じ破損ファイルが居座ると常時ポーリングの daemon/web で warning が洪水になるため、
# path+mtime 単位で初回のみ WARNING、同一内容の再遭遇は DEBUG に落とす。
_warned_org_files: Dict[str, float] = {}


def warn_skipped_org_file(f: Path, exc: Exception) -> None:
    try:
        mtime = f.stat().st_mtime
    except OSError:
        mtime = -1.0
    key = str(f)
    level = logging.DEBUG if _warned_org_files.get(key) == mtime else logging.WARNING
    _warned_org_files[key] = mtime
    logger.log(
        level,
        "Organization ファイルの読み込みをスキップ: %s (%s: %s)",
        f,
        type(exc).__name__,
        exc,
    )


def _migrate_legacy_home(new_home: Path) -> None:
    """One-time migration from the old ``~/.repocorp`` store to ``~/.pantheon``.

    Copies the legacy directory the first time Pantheon runs after the rename, so
    existing organizations / settings / history carry over without data loss. The
    legacy directory is left intact (non-destructive).
    """
    if new_home.exists():
        return
    legacy = Path.home() / ".repocorp"
    if legacy.is_dir():
        import shutil

        try:
            shutil.copytree(legacy, new_home)
        except OSError:
            pass


def get_platform_home() -> Path:
    """
    プラットフォームストアのルートディレクトリを返す。
    PANTHEON_HOME 環境変数が設定されていればそちらを使う。
    旧 ~/.repocorp が存在する場合は初回のみ ~/.pantheon へ自動移行する。
    """
    env = os.environ.get("PANTHEON_HOME")
    if env:
        return Path(env).expanduser().resolve()
    home = Path.home() / ".pantheon"
    _migrate_legacy_home(home)
    return home


class PlatformStateManager:
    """
    Core（本社）のグローバルプラットフォームストアを管理する。

    ディレクトリ構成:
      ~/.pantheon/
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
        self.platform_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_platform_config(self) -> Dict[str, Any]:
        if not self.platform_file.exists():
            return {}
        return json.loads(self.platform_file.read_text(encoding="utf-8"))

    def save_platform_config(self, config: Dict[str, Any]) -> None:
        config["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.platform_file.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def set_meta_improvement_org_id(self, org_id: str) -> None:
        config = self.load_platform_config()
        config["meta_improvement_org_id"] = org_id
        self.save_platform_config(config)

    def get_workspaces_root(self) -> Optional[str]:
        """新規ワークスペース（git repo）を作成する既定の親フォルダ（未設定なら None）。

        ゴールから新規ワークスペースを作る際の置き場所。未設定時の既定は呼び出し側で
        ``platform_home/workspaces`` 等にフォールバックする。実運用では
        ``set_workspaces_root("C:\\Users\\neoma\\NEL")`` のように設定する。
        """
        return self.load_platform_config().get("workspaces_root")

    def set_workspaces_root(self, path: str | Path) -> None:
        config = self.load_platform_config()
        config["workspaces_root"] = str(path)
        self.save_platform_config(config)

    # ---- Organization 管理 ----

    def save_organization(self, org: Organization) -> None:
        """Organization をグローバルストアに保存する"""
        path = self.orgs_dir / f"{org.id}.json"
        path.write_text(org.model_dump_json(indent=2), encoding="utf-8")

    def load_organizations(self) -> List[Organization]:
        """全 Organization を読み込む。

        壊れた/検証に失敗した JSON は耐性のためスキップするが（旧データや手書きファイルで
        全体を壊さない）、黙って消えると「組織が音もなく消失した」ように見えるため
        warning で観測可能にする。ファイルは削除しない（修復すれば次回読み込まれる）。
        """
        result = []
        for f in sorted(self.orgs_dir.glob("*.json")):
            try:
                result.append(Organization.model_validate_json(f.read_text(encoding="utf-8")))
            except Exception as exc:  # noqa: BLE001 — 1ファイルの破損で全体を壊さない
                warn_skipped_org_file(f, exc)
                continue
        return result

    def load_organization_by_name(self, name: str) -> Optional[Organization]:
        for org in self.load_organizations():
            if org.name == name:
                return org
        return None

    def load_organization_by_repo(self, repo_path: str | Path) -> Optional[Organization]:
        """指定ワークスペース（repo パス）に紐づく Organization を返す（重複登録判定用）。"""
        target = str(Path(repo_path)).rstrip("\\/").lower()
        for org in self.load_organizations():
            if (
                org.target_repo_path
                and str(Path(org.target_repo_path)).rstrip("\\/").lower() == target
            ):
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
        Org のデータ位置（``data_location``）内の .pantheon/ を管理する RepoStateManager を返す。

        repo モードは target_repo_path、workspace モード（Workspace モデル §5）は workspace_path を
        使う。いずれも未設定なら platform_home にフォールバックする。
        """
        from core.state.manager import RepoStateManager

        location = org.data_location
        repo_path = Path(location) if location else self.platform_home
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
