"""YouTube アップロード（core/media/youtube_upload）と `pantheon story publish` の検証。

OAuth/resumable upload のロジックをモック transport で検証（実ネットワーク不要）。認証情報が
無ければ送出、API 失敗は偽の成功/URLを返さない、既定 privacy は private、CLI 既定はドライラン。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from core.media.credentials import MediaProviderNotConfigured
from core.media.youtube_upload import load_youtube_credentials, upload_video


def _write_creds(tmp_path, **over):
    data = {"client_id": "cid", "client_secret": "sec", "refresh_token": "rt"}
    data.update(over)
    (tmp_path / "youtube_credentials.json").write_text(json.dumps(data), encoding="utf-8")


def _video(tmp_path):
    p = tmp_path / "ep-01.mp4"
    p.write_bytes(b"\x00\x00fake-mp4-bytes")
    return p


class _FakeYT:
    def __init__(self, *, fail=False, no_id=False):
        self.fail = fail
        self.no_id = no_id
        self.body = None

    def fetch_token(self, form):
        assert form["grant_type"] == "refresh_token"
        return {"access_token": "at-123"}

    def start_session(self, headers, body):
        assert headers["Authorization"] == "Bearer at-123"
        self.body = body
        return "https://upload.example/session/abc"

    def upload(self, session_url, headers, blob):
        if self.fail:
            raise RuntimeError("boom-upload")
        assert blob  # 実バイトを送っている
        return {} if self.no_id else {"id": "VID42"}


def test_load_credentials(tmp_path):
    assert load_youtube_credentials(tmp_path) is None  # 無し
    (tmp_path / "youtube_credentials.json").write_text(
        json.dumps({"client_id": "x"}), encoding="utf-8"
    )
    assert load_youtube_credentials(tmp_path) is None  # 不完全
    _write_creds(tmp_path)
    creds = load_youtube_credentials(tmp_path)
    assert creds and creds["refresh_token"] == "rt"


def test_upload_requires_credentials(tmp_path):
    with pytest.raises(MediaProviderNotConfigured):
        upload_video(_video(tmp_path), title="t", platform_home=tmp_path)


def test_upload_happy_path_with_mock(tmp_path):
    _write_creds(tmp_path)
    tr = _FakeYT()
    res = upload_video(
        _video(tmp_path),
        title="RED THREAD #1",
        description="d",
        tags=["a", "b"],
        privacy="unlisted",
        platform_home=tmp_path,
        transport=tr,
    )
    assert res.ok and res.video_id == "VID42"
    assert res.url == "https://youtu.be/VID42"
    # snippet/status が正しく組み立てられている（誤公開しない privacy 指定が効く）
    assert tr.body["snippet"]["title"] == "RED THREAD #1"
    assert tr.body["status"]["privacyStatus"] == "unlisted"


def test_upload_api_failure_no_fake_success(tmp_path):
    _write_creds(tmp_path)
    res = upload_video(
        _video(tmp_path), title="t", platform_home=tmp_path, transport=_FakeYT(fail=True)
    )
    assert not res.ok and "boom-upload" in res.error and res.url == ""


def test_upload_missing_video_id_is_honest(tmp_path):
    _write_creds(tmp_path)
    res = upload_video(
        _video(tmp_path), title="t", platform_home=tmp_path, transport=_FakeYT(no_id=True)
    )
    assert not res.ok and not res.url


def test_upload_rejects_bad_privacy_and_missing_file(tmp_path):
    _write_creds(tmp_path)
    assert not upload_video(_video(tmp_path), title="t", privacy="world", platform_home=tmp_path).ok
    assert not upload_video(tmp_path / "nope.mp4", title="t", platform_home=tmp_path).ok


def test_cli_publish_defaults_to_dry_run(tmp_path, monkeypatch, capsys):
    """CLI 既定はドライラン（外部公開は --yes 明示時のみ）＝誤公開しない。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from commands.story import cmd_story_publish
    from core.orchestration.company_plugins import install_company_plugin
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path)
    org_name = install_company_plugin("illustration_story_youtube", psm=psm)["org_name"]
    org = psm.load_organization_by_name(org_name)
    from pathlib import Path

    work = Path(org.workspace_path) / "episodes" / "ep-01"
    work.mkdir(parents=True, exist_ok=True)
    (work / "ep-01.mp4").write_bytes(b"mp4")

    asyncio.run(
        cmd_story_publish(
            SimpleNamespace(org=org_name, ep=1, privacy="private", yes=False), get_psm=lambda: psm
        )
    )
    out = capsys.readouterr().out
    assert "ドライラン" in out and "private" in out
    assert "認証情報" in out  # 鍵の有無を正直に表示
