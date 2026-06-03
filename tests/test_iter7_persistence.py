"""Iter7: 原子的書き込み(D4) と utcnow 非使用監査(D6)。"""

from __future__ import annotations

import json
import pathlib
from uuid import uuid4

from core.io_utils import atomic_write_text

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_atomic_write_text_overwrite_no_residue(tmp_path):
    target = tmp_path / "sub" / "data.json"
    atomic_write_text(target, json.dumps({"x": 1}))
    assert json.loads(target.read_text(encoding="utf-8")) == {"x": 1}
    atomic_write_text(target, json.dumps({"x": 2}))
    assert json.loads(target.read_text(encoding="utf-8")) == {"x": 2}
    assert list(target.parent.glob("*.tmp.*")) == []  # 一時ファイルが残らない


def test_repo_state_manager_writes_are_atomic(tmp_path):
    from core.models.organization import ImprovementProposal
    from core.state.manager import RepoStateManager

    sm = RepoStateManager(tmp_path, "Org")
    sm.save_improvement_proposal(
        ImprovementProposal(review_id=uuid4(), title="t", description="d", file_path="x.py", status="proposed")
    )
    sm.record_decision("d1", "title", "content", made_by="test")
    # .repocorp 配下に一時ファイルの残骸が無い
    assert list((tmp_path / ".repocorp").rglob("*.tmp.*")) == []
    # 保存した提案が読み戻せる
    assert sm.get_pending_improvement_proposals(limit=10)


def test_platform_state_writes_are_atomic(tmp_path):
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path)
    psm.initialize(meta_improvement_org_id="x")
    psm.save_platform_config({"k": "v"})
    assert list(tmp_path.rglob("*.tmp.*")) == []
    assert psm.load_platform_config().get("k") == "v"


def test_no_naive_utcnow_in_source():
    """D6: 本番コードに `datetime.utcnow()`（naive）が無いことを保証する。"""
    targets = ["core", "agents", "web", "commands", "main.py"]
    offenders: list[str] = []
    for name in targets:
        base = REPO_ROOT / name
        files = [base] if base.is_file() else base.rglob("*.py")
        for path in files:
            if "legacy" in path.parts or "__pycache__" in path.parts:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                # コメント/docstring 内の言及（バックティック付き）は除外
                if "utcnow(" in line and "`" not in line and not line.lstrip().startswith("#"):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    assert offenders == [], f"naive utcnow found: {offenders}"
