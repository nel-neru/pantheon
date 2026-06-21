"""メディア生産（画像生成・動画組立）— エピソードブリーフから実ファイルを作る外部連携層。

Pantheon の「思考」は claude CLI（ホスト型 LLM キー無し）だが、画像ピクセル/動画レンダは
本質的に外部サービス/ツールを要する。本サブシステムはそれを **opt-in・認証情報ゲート付き**で
提供する: 鍵があれば本物のAPIを呼び、無ければ正直にエラー（偽の画像・偽の成功は出さない）。
動画組立は FFmpeg（ローカル・鍵不要）で完結する。
"""

from __future__ import annotations

from core.media.credentials import MediaProviderNotConfigured, load_api_key, media_credentials_dir

__all__ = ["MediaProviderNotConfigured", "load_api_key", "media_credentials_dir"]
