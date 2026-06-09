"""org scan（親フォルダの git リポジトリ検出 → ワークスペース登録）のテスト。"""

from __future__ import annotations

import argparse
import asyncio

from commands.org import _find_git_repos, cmd_org_scan
from core.platform.state import PlatformStateManager


def _make_repo(parent, name):
    repo = parent / name
    (repo / ".git").mkdir(parents=True)
    return repo


def test_find_git_repos_detects_children(tmp_path):
    _make_repo(tmp_path, "alpha")
    _make_repo(tmp_path, "beta")
    (tmp_path / "not-a-repo").mkdir()
    names = {r.name for r in _find_git_repos(tmp_path)}
    assert names == {"alpha", "beta"}


def test_scan_registers_new_repos_with_yes(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTHEON_HOME", str(tmp_path / "home"))
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()
    _make_repo(workspaces, "sns-org")
    _make_repo(workspaces, "note-org")

    psm = PlatformStateManager(platform_home=tmp_path / "home")
    args = argparse.Namespace(parent=str(workspaces), yes=True)
    asyncio.run(cmd_org_scan(args, get_psm=lambda: psm))

    names = {o.name for o in psm.load_organizations()}
    assert {"sns-org", "note-org"}.issubset(names)
    # repo が必ず紐づく（1 ws = 1 org）
    sns = psm.load_organization_by_name("sns-org")
    assert sns.target_repo_path and sns.is_workspace_bound


def test_scan_skips_already_registered(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTHEON_HOME", str(tmp_path / "home"))
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()
    repo = _make_repo(workspaces, "sns-org")

    psm = PlatformStateManager(platform_home=tmp_path / "home")
    # 1回目: 登録
    asyncio.run(
        cmd_org_scan(argparse.Namespace(parent=str(workspaces), yes=True), get_psm=lambda: psm)
    )
    count_after_first = len(psm.load_organizations())
    # 2回目: 既登録なので増えない
    asyncio.run(
        cmd_org_scan(argparse.Namespace(parent=str(workspaces), yes=True), get_psm=lambda: psm)
    )
    assert len(psm.load_organizations()) == count_after_first
    assert psm.load_organization_by_repo(repo) is not None


def test_scan_without_yes_does_not_register(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTHEON_HOME", str(tmp_path / "home"))
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()
    _make_repo(workspaces, "sns-org")

    psm = PlatformStateManager(platform_home=tmp_path / "home")
    before = len(psm.load_organizations())
    asyncio.run(
        cmd_org_scan(argparse.Namespace(parent=str(workspaces), yes=False), get_psm=lambda: psm)
    )
    # --yes 無しでは候補表示のみ。登録は増えない。
    assert len(psm.load_organizations()) == before
