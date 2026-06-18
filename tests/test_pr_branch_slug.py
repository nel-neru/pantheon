"""PR ブランチ slug 生成（branch_slug）の回帰テスト。

旧実装 `re.sub(r"[^a-z0-9]+", "-", title.lower())[:40]` は:
- 日本語タイトル（本プロジェクトの提案の主言語）を全て "-" に潰し、ブランチ名が
  `pantheon/improvement---<timestamp>` と退化・区別不能になっていた
- `title: None` で `.lower()` が AttributeError クラッシュしていた

本テストは修正後のセマンティクスを load-bearing にピン留めする。
"""

from __future__ import annotations

import asyncio
import re
import sys
from types import ModuleType, SimpleNamespace

from github_integration.pr_creator import (
    branch_slug,
    create_improvement_pr,
    suggestion_description,
    suggestion_title,
)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def test_ascii_title_produces_readable_slug():
    slug = branch_slug("Improve the cache layer!")
    assert slug == "improve-the-cache-layer"


def test_japanese_title_is_not_degenerate():
    """日本語のみのタイトルは '-' に潰れず、有効で非退化な slug になる。"""
    slug = branch_slug("キャッシュ層を改善する")
    assert _SLUG_RE.match(slug)  # git ref に使える形
    assert slug not in ("", "-", "--")  # 退化しない
    assert "--" not in slug


def test_distinct_japanese_titles_get_distinct_slugs():
    """別々の日本語タイトルは別々の slug になる（ブランチが衝突・混同しない）。"""
    a = branch_slug("キャッシュ層を改善する")
    b = branch_slug("ログ出力を整理する")
    assert a != b


def test_same_title_is_deterministic():
    assert branch_slug("同じタイトル") == branch_slug("同じタイトル")


def test_mixed_title_keeps_ascii_parts():
    """ASCII を含む場合は英数字部分を活かす（日本語部分だけ畳む）。"""
    assert branch_slug("Fix 日本語 bug") == "fix-bug"


def test_none_and_empty_title_do_not_crash():
    """None/空タイトルでもクラッシュせず有効な slug を返す（旧コードは None で AttributeError）。"""
    for value in (None, "", "   ", "！？"):
        slug = branch_slug(value)
        assert _SLUG_RE.match(slug), f"invalid slug for {value!r}: {slug!r}"


def test_long_title_is_truncated_without_trailing_dash():
    slug = branch_slug("word " * 50)  # 250 文字相当
    assert len(slug) <= 40
    assert not slug.endswith("-")


# ── 統合: 日本語タイトルでも有効なブランチ名が PR 経路に渡る ──


def _fake_github(repo):
    fake_module = ModuleType("github")

    class FakeGithubException(Exception):
        pass

    fake_module.GithubException = FakeGithubException

    class FakeGithub:
        def __init__(self, token):
            self.token = token

        def get_repo(self, slug):
            return repo

    fake_module.Github = FakeGithub
    return fake_module, FakeGithubException


def test_japanese_title_yields_valid_branch_in_pr_flow(monkeypatch, tmp_path):
    """日本語タイトルの提案でも、update_file に渡るブランチ名が有効・非退化になる。"""

    class FakeContent:
        sha = "abc123"

    class FakeRepo:
        default_branch = "main"

        def __init__(self):
            self.updated = []

        def get_branch(self, branch):
            return SimpleNamespace(commit=SimpleNamespace(sha="deadbeef"))

        def get_contents(self, path, ref=None):
            return FakeContent()

        def update_file(self, **kwargs):
            self.updated.append(kwargs)

        def create_file(self, **kwargs):  # pragma: no cover - 既存ファイル経路では未使用
            raise AssertionError("update_file should be used")

        def create_pull(self, **kwargs):
            return SimpleNamespace(html_url="https://example.com/pr/9")

    repo = FakeRepo()
    fake_module, _ = _fake_github(repo)
    monkeypatch.setitem(sys.modules, "github", fake_module)

    pr_url = asyncio.run(
        create_improvement_pr(
            repo_path=tmp_path,
            github_token="token",
            github_repo="owner/repo",
            file_path="src/app.py",
            modified_content="print('ok')",
            suggestion={"title": "キャッシュ層を改善する", "description": "説明"},
        )
    )
    assert pr_url == "https://example.com/pr/9"
    branch = repo.updated[0]["branch"]
    # ブランチ名全体が git ref に使える形で、slug が '---' に退化していない。
    assert re.fullmatch(r"pantheon/improvement-[a-z0-9][a-z0-9-]*-\d{14}", branch), branch
    assert "improvement---" not in branch


# ── title/description の表示用デフォルト（literal "None" 防止） ──


def test_suggestion_title_falls_back_when_none_or_empty_or_absent():
    """None/空/不在は default に落ちる（``.get(k, default)`` は None 値をガードしないため）。"""
    assert suggestion_title({"title": None}) == "Improvement"
    assert suggestion_title({"title": ""}) == "Improvement"
    assert suggestion_title({}) == "Improvement"
    assert suggestion_title({"title": None}, "Apply improvement") == "Apply improvement"


def test_suggestion_title_returns_value_when_present():
    assert suggestion_title({"title": "Improve cache"}) == "Improve cache"
    assert suggestion_title({"title": "キャッシュ改善"}) == "キャッシュ改善"


def test_suggestion_description_falls_back_when_none_or_absent():
    assert suggestion_description({"description": None}) == "(説明なし)"
    assert suggestion_description({}) == "(説明なし)"
    assert suggestion_description({"description": "詳細"}) == "詳細"


def test_pr_flow_emits_no_literal_none_when_title_and_description_missing(monkeypatch, tmp_path):
    """title/description が None の提案でも、commit メッセージ・PR タイトル・PR 本文に
    literal 'None' が混入しない（旧コードは ``refactor: None`` ``[Pantheon] None`` を生成）。"""

    class FakeContent:
        sha = "abc123"

    class FakeRepo:
        default_branch = "main"

        def __init__(self):
            self.updated = []
            self.pulls = []

        def get_branch(self, branch):
            return SimpleNamespace(commit=SimpleNamespace(sha="deadbeef"))

        def get_contents(self, path, ref=None):
            return FakeContent()

        def update_file(self, **kwargs):
            self.updated.append(kwargs)

        def create_file(self, **kwargs):  # pragma: no cover - 既存ファイル経路では未使用
            raise AssertionError("update_file should be used")

        def create_pull(self, **kwargs):
            self.pulls.append(kwargs)
            return SimpleNamespace(html_url="https://example.com/pr/9")

    repo = FakeRepo()
    fake_module, _ = _fake_github(repo)
    monkeypatch.setitem(sys.modules, "github", fake_module)

    asyncio.run(
        create_improvement_pr(
            repo_path=tmp_path,
            github_token="token",
            github_repo="owner/repo",
            file_path="src/app.py",
            modified_content="print('ok')",
            suggestion={"title": None, "description": None},
        )
    )

    commit_message = repo.updated[0]["message"]
    assert commit_message == "refactor: Apply improvement"
    assert "None" not in commit_message

    pull = repo.pulls[0]
    assert pull["title"] == "[Pantheon] Improvement"
    assert "None" not in pull["title"]
    # 本文の title/description 行も literal "None" を出さない。
    assert "**改善提案**: None" not in pull["body"]
    assert "**説明**: None" not in pull["body"]
