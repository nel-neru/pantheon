"""YouTube OAuth アクセストークン取得（refresh_token → access_token）の共有ヘルパ。

upload / analytics が共通で使う。認証情報（``youtube_credentials.json``）が無ければ
``MediaProviderNotConfigured``。``transport`` 注入でテスト可能（実ネットワーク不要）。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from core.media.credentials import MediaProviderNotConfigured
from core.media.youtube_upload import load_youtube_credentials, youtube_credentials_path

_TOKEN_URL = "https://oauth2.googleapis.com/token"


class _UrllibTokenTransport:
    def fetch_token(self, form: Dict[str, str]) -> Dict[str, Any]:
        data = urllib.parse.urlencode(form).encode("utf-8")
        req = urllib.request.Request(
            _TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))


def get_access_token(platform_home: Optional[Path] = None, *, transport: Any = None) -> str:
    """refresh_token を access_token に交換して返す。認証情報が無ければ送出。"""
    creds = load_youtube_credentials(platform_home)
    if creds is None:
        raise MediaProviderNotConfigured(
            "YouTube の OAuth 認証情報がありません。"
            f"{youtube_credentials_path(platform_home)} に "
            '{"client_id","client_secret","refresh_token"} を保存してください。'
        )
    tr = transport or _UrllibTokenTransport()
    token = tr.fetch_token(
        {
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        }
    )
    access = str(token.get("access_token") or "")
    if not access:
        raise MediaProviderNotConfigured(f"アクセストークン取得に失敗しました: {token}")
    return access
