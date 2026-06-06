"""
Phase 4 — State 主従の明確化: `pantheon query --org-name` は正準 JSON ストア
（RepoStateManager / <repo>/.pantheon/improvements）を読む。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from commands.org import cmd_query
from core.models.organization import ImprovementProposal
from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager
from main import _parse_query_filters


def _setup(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    psm = PlatformStateManager(platform_home=tmp_path / "home")
    org = create_default_organization("QueryOrg", "query test")
    org.target_repo_path = str(repo)
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    sm.save_improvement_proposal(
        ImprovementProposal(
            review_id=uuid4(),
            title="High security fix",
            description="d",
            priority="high",
            category="security",
            file_path="a.py",
        )
    )
    sm.save_improvement_proposal(
        ImprovementProposal(
            review_id=uuid4(),
            title="Low style tweak",
            description="d",
            priority="low",
            category="style",
            file_path="b.py",
        )
    )
    return psm


def test_cmd_query_reads_json_store_by_org(tmp_path, capsys):
    psm = _setup(tmp_path)
    args = SimpleNamespace(org_name="QueryOrg", db_path=None, filter="", limit=50)
    asyncio.run(
        cmd_query(
            args,
            get_platform_home=lambda: tmp_path / "home",
            parse_query_filters=_parse_query_filters,
            get_psm=lambda: psm,
        )
    )
    out = capsys.readouterr().out
    assert "High security fix" in out
    assert "Low style tweak" in out


def test_cmd_query_json_applies_field_filter(tmp_path, capsys):
    psm = _setup(tmp_path)
    args = SimpleNamespace(org_name="QueryOrg", db_path=None, filter="priority=high", limit=50)
    asyncio.run(
        cmd_query(
            args,
            get_platform_home=lambda: tmp_path / "home",
            parse_query_filters=_parse_query_filters,
            get_psm=lambda: psm,
        )
    )
    out = capsys.readouterr().out
    assert "High security fix" in out
    assert "Low style tweak" not in out


def test_cmd_query_unknown_org_exits(tmp_path):
    psm = _setup(tmp_path)
    args = SimpleNamespace(org_name="NoSuchOrg", db_path=None, filter="", limit=50)
    with pytest.raises(SystemExit):
        asyncio.run(
            cmd_query(
                args,
                get_platform_home=lambda: tmp_path / "home",
                parse_query_filters=_parse_query_filters,
                get_psm=lambda: psm,
            )
        )
