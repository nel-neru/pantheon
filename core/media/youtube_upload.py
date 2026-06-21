"""YouTube 動画アップロード — Data API v3 の resumable upload（OAuth・認証ゲート・偽公開なし）。

テキスト publishing（note/X の Playwright assisted）とは別系統。動画ファイルを公式 API で
アップロードする。標準ライブラリ（urllib）のみ・外部 SDK 非依存。

正直性: OAuth 認証情報（``~/.pantheon/youtube_credentials.json`` = client_id/client_secret/
refresh_token）が無ければ ``MediaProviderNotConfigured``（アップロードしない）。API 失敗は
``UploadResult(ok=False, ...)``＝**偽の公開URLや成功を返さない**。``transport`` 注入でロジックを
実ネットワーク無しに検証できる。

注意（HITL/外部作用）: これは外部公開アクション。CLI は既定でドライプレビューにし、``--yes``
明示時のみ実アップロードする。チャンネル作成と OAuth リフレッシュトークン取得は利用者の作業
（Google Cloud で OAuth クライアントを作り refresh_token を得る＝人間でないとできない部分）。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.media.credentials import MediaProviderNotConfigured

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_UPLOAD_URL = (
    "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
)
# 22 = People & Blogs（無言ストーリーに無難。必要なら metadata.extra で上書き可）。
_DEFAULT_CATEGORY_ID = "22"
_VALID_PRIVACY = ("private", "unlisted", "public")


@dataclass
class UploadResult:
    ok: bool
    video_id: str = ""
    url: str = ""
    error: str = ""


def youtube_credentials_path(platform_home: Optional[Path] = None) -> Path:
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()
    return Path(platform_home) / "youtube_credentials.json"


def load_youtube_credentials(platform_home: Optional[Path] = None) -> Optional[Dict[str, str]]:
    """``youtube_credentials.json``（client_id/client_secret/refresh_token）を読む。無ければ None。"""
    path = youtube_credentials_path(platform_home)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not all(data.get(k) for k in ("client_id", "client_secret", "refresh_token")):
        return None
    return {k: str(data[k]) for k in ("client_id", "client_secret", "refresh_token")}


class _UrllibYouTubeTransport:
    """既定の HTTP transport（標準ライブラリのみ）。"""

    def fetch_token(self, form: Dict[str, str]) -> Dict[str, Any]:
        data = urllib.parse.urlencode(form).encode("utf-8")
        req = urllib.request.Request(
            _TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))

    def start_session(self, headers: Dict[str, str], body: Dict[str, Any]) -> str:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            _UPLOAD_URL, data=data, headers={"Content-Type": "application/json", **headers}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            location = resp.headers.get("Location") or resp.headers.get("location")
        if not location:
            raise ValueError("resumable セッション URL（Location）が返りませんでした")
        return location

    def upload(self, session_url: str, headers: Dict[str, str], blob: bytes) -> Dict[str, Any]:
        req = urllib.request.Request(session_url, data=blob, headers=headers, method="PUT")
        with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))


def upload_video(
    video_path: Any,
    *,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    privacy: str = "private",
    category_id: str = _DEFAULT_CATEGORY_ID,
    platform_home: Optional[Path] = None,
    transport: Any = None,
) -> UploadResult:
    """mp4 を YouTube へ resumable upload する。認証情報が無ければ送出、失敗は正直に返す。

    既定 privacy は ``private``（誤公開を避ける安全側）。``--yes`` 等の明示意思は CLI 側で扱う。
    """
    path = Path(video_path)
    if not path.exists():
        return UploadResult(ok=False, error=f"動画ファイルがありません: {path}")
    if privacy not in _VALID_PRIVACY:
        return UploadResult(ok=False, error=f"privacy は {_VALID_PRIVACY} のいずれか: {privacy}")

    creds = load_youtube_credentials(platform_home)
    if creds is None:
        raise MediaProviderNotConfigured(
            "YouTube の OAuth 認証情報がありません。Google Cloud で OAuth クライアントを作成し "
            f"{youtube_credentials_path(platform_home)} に "
            '{"client_id","client_secret","refresh_token"} を保存してください'
            "（認証情報が無い間はアップロードしません＝偽の公開はしません）。"
        )

    tr = transport or _UrllibYouTubeTransport()
    try:
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
            return UploadResult(ok=False, error=f"アクセストークン取得失敗: {token}")

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": list(tags or []),
                "categoryId": category_id,
            },
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
        }
        blob = path.read_bytes()
        session_url = tr.start_session(
            {"Authorization": f"Bearer {access}", "X-Upload-Content-Type": "video/*"}, body
        )
        result = tr.upload(
            session_url,
            {"Authorization": f"Bearer {access}", "Content-Type": "video/*"},
            blob,
        )
    except MediaProviderNotConfigured:
        raise
    except Exception as exc:  # noqa: BLE001 — 偽の成功を返さず正直に失敗
        return UploadResult(ok=False, error=f"{type(exc).__name__}: {exc}")

    video_id = str(result.get("id") or "")
    if not video_id:
        return UploadResult(ok=False, error=f"アップロード応答に動画IDがありません: {result}")
    return UploadResult(ok=True, video_id=video_id, url=f"https://youtu.be/{video_id}")
