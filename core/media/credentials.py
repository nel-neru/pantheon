"""メディアプロバイダの認証情報解決（環境変数 → ~/.pantheon/media_credentials/<provider>.key）。

Pantheon が秘密を「受け取って動く」のではなく、利用者が置いた鍵を読むだけ（publishing の
session 方針と同じ）。鍵が無ければ ``MediaProviderNotConfigured`` を投げ、呼び出し側は
偽の成果物を作らず正直に失敗する。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class MediaProviderNotConfigured(RuntimeError):
    """外部メディアプロバイダの認証情報が未設定（鍵が無い）ことを示す。"""


def media_credentials_dir(platform_home: Optional[Path] = None) -> Path:
    """``~/.pantheon/media_credentials``（または注入 home 配下）を返す。"""
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()
    return Path(platform_home) / "media_credentials"


# プロバイダ → 既定の環境変数名（環境変数があればファイルより優先）。
_ENV_VARS = {
    "gemini": "GEMINI_API_KEY",
    "fal": "FAL_KEY",
}


def load_api_key(
    provider: str,
    *,
    platform_home: Optional[Path] = None,
    env_var: Optional[str] = None,
) -> Optional[str]:
    """``provider`` の API キーを解決する。無ければ ``None``。

    探索順: ①明示 ``env_var`` か既定の環境変数 ②``media_credentials/<provider>.key`` の中身。
    どちらも無ければ ``None``（呼び出し側が ``MediaProviderNotConfigured`` を投げる）。
    """
    name = str(provider).strip().lower()
    var = env_var or _ENV_VARS.get(name)
    if var:
        val = os.environ.get(var)
        if val and val.strip():
            return val.strip()
    key_file = media_credentials_dir(platform_home) / f"{name}.key"
    if key_file.exists():
        try:
            content = key_file.read_text(encoding="utf-8").strip()
            return content or None
        except OSError:
            return None
    return None


def require_api_key(
    provider: str,
    *,
    platform_home: Optional[Path] = None,
    env_var: Optional[str] = None,
) -> str:
    """鍵を返す。無ければ設定方法を添えて ``MediaProviderNotConfigured`` を投げる。"""
    key = load_api_key(provider, platform_home=platform_home, env_var=env_var)
    if key:
        return key
    name = str(provider).strip().lower()
    var = env_var or _ENV_VARS.get(name, f"{name.upper()}_API_KEY")
    raise MediaProviderNotConfigured(
        f"{name} の API キーが未設定です。環境変数 {var} を設定するか、"
        f"{media_credentials_dir(platform_home) / f'{name}.key'} に鍵を保存してください"
        "（鍵が無い間は画像生成を行いません＝偽の画像は作りません）。"
    )
