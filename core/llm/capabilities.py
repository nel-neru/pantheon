"""
ProviderCapabilities — プロバイダーごとの能力差を宣言的に集約する。

「どのAIでも全機能」を実現するには、UI/オーケストレーターが各プロバイダーで
何ができるか（tool 呼び出し・JSONモード・ストリーミング・推論強度・文脈長など）を
知る必要がある。ここを唯一の真実とし、API/Settings から公開する。

値は現状の provider 実装が実際に行っている挙動に合わせた「保守的な既定」。
将来 provider 側で機能を有効化したらここを更新する。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

__all__ = ["ProviderCapabilities", "get_capabilities", "all_capabilities", "CAPABILITIES"]


@dataclass(frozen=True)
class ProviderCapabilities:
    """単一プロバイダーの能力記述。"""

    provider: str
    supports_tools: bool = True
    supports_json_mode: bool = False
    supports_streaming: bool = True
    supports_streaming_tools: bool = False
    supports_reasoning_effort: bool = False
    supports_system_prompt: bool = True
    max_context_tokens: int = 0  # 0 = 不明 / 未設定
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# provider_name -> ProviderCapabilities
CAPABILITIES: Dict[str, ProviderCapabilities] = {
    "anthropic": ProviderCapabilities(
        provider="anthropic",
        supports_tools=True,
        supports_json_mode=False,  # ネイティブ response_format なし。堅牢抽出で代替（tool強制は後続）
        supports_streaming=True,
        supports_streaming_tools=False,  # 現状 stream() は tools を扱わない
        supports_reasoning_effort=False,  # extended thinking 未配線
        supports_system_prompt=True,
        max_context_tokens=200000,
        notes="Claude 3.5/4 系。system は専用フィールド。",
    ),
    "openai": ProviderCapabilities(
        provider="openai",
        supports_tools=True,
        supports_json_mode=True,  # response_format={"type":"json_object"} を配線
        supports_streaming=True,
        supports_streaming_tools=False,
        supports_reasoning_effort=False,  # o系 reasoning_effort 未配線
        supports_system_prompt=True,
        max_context_tokens=128000,
        notes="OpenAI Chat Completions 互換。",
    ),
    "groq": ProviderCapabilities(
        provider="groq",
        supports_tools=True,
        supports_json_mode=True,  # OpenAI 互換 response_format（モデル依存だが既定は対応）
        supports_streaming=True,
        supports_streaming_tools=False,
        supports_reasoning_effort=False,
        supports_system_prompt=True,
        max_context_tokens=32768,
        notes="OpenAI 互換エンドポイント。文脈長はモデル依存。",
    ),
    "github_models": ProviderCapabilities(
        provider="github_models",
        supports_tools=True,
        supports_json_mode=True,  # OpenAI 互換 response_format（既定 gpt-4o は対応）
        supports_streaming=True,
        supports_streaming_tools=False,
        supports_reasoning_effort=False,
        supports_system_prompt=True,
        max_context_tokens=128000,
        notes="GitHub Models (Azure 推論) OpenAI 互換。レート制限が厳しめ。",
    ),
    "gemini": ProviderCapabilities(
        provider="gemini",
        supports_tools=True,
        supports_json_mode=True,  # generation_config.response_mime_type="application/json" を配線
        supports_streaming=True,
        supports_streaming_tools=False,
        supports_reasoning_effort=False,
        supports_system_prompt=True,
        max_context_tokens=1000000,
        notes="Gemini 1.5/2.0 系。長文脈。function_declarations 形式の tools。",
    ),
}

_DEFAULT = ProviderCapabilities(provider="unknown", notes="未登録プロバイダー（既定能力）。")


def get_capabilities(provider_name: str) -> ProviderCapabilities:
    """provider 名から能力記述を返す。未登録なら provider 名のみ差し替えた既定値。"""
    cap = CAPABILITIES.get(provider_name)
    if cap is not None:
        return cap
    return ProviderCapabilities(
        provider=provider_name or "unknown",
        notes=_DEFAULT.notes,
    )


def all_capabilities() -> Dict[str, Dict[str, Any]]:
    """全プロバイダーの能力を dict 形式で返す（API/Settings 公開用）。"""
    return {name: cap.to_dict() for name, cap in CAPABILITIES.items()}
