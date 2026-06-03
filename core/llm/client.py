"""
LLMClient — 同期ブリッジ＆既定クライアント解決

RepoCorp の中核は async な `LLMProvider`（core/llm/base.py）。一方で多くの
エージェント（tool_design_agent, self_code_writer, goal_parser, ...）は歴史的経緯から
同期の `llm_client.invoke(prompt)` / `llm_client.complete(messages)` を前提にしている。

LLMClient はその両インターフェースを満たしつつ内部を `LLMProvider.generate()` に
一本化する薄いアダプタ。これにより「どのプロバイダーでも同じ呼び出しで動く」を実現する。

get_default_llm_client() は GUI設定（~/.repocorp/gui_settings.json）→ 環境変数の順で
provider と APIキーを解決し、キーがあれば LLMClient を、無ければ None を返す。
None の場合、各エージェントは従来どおりテンプレート/フォールバック動作になる
（＝APIキー未設定のテスト環境では挙動が変わらない）。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse

__all__ = [
    "LLMClient",
    "get_default_llm_client",
    "get_configured_llm_provider",
    "reset_provider_cache",
    "resolve_default_provider",
    "resolve_provider_api_key",
    "resolve_default_model",
    "PROVIDER_KEY_MAPPING",
]

# provider -> (gui_settings のトップレベルキー, 環境変数名)
# main.py / web/server.py にも同等の対応表があるが、core/llm を唯一の正典とする。
PROVIDER_KEY_MAPPING: Dict[str, tuple[str, str]] = {
    "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "groq": ("groq_api_key", "GROQ_API_KEY"),
    "github_models": ("github_models_api_key", "GITHUB_TOKEN"),
    "gemini": ("gemini_api_key", "GOOGLE_API_KEY"),
}

_SETTINGS_FILE = Path.home() / ".repocorp" / "gui_settings.json"

PromptLike = Union[str, List[Union[LLMMessage, Dict[str, Any]]]]


def _run_sync(coro: Any) -> Any:
    """async コルーチンを同期コンテキストから安全に実行する。

    実行中のイベントループが無ければ asyncio.run、ある場合（FastAPI の async 文脈など）
    は専用スレッドで新しいループを回して `asyncio.run() cannot be called from a running
    event loop` を回避する。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro)).result()


def _coerce_messages(prompt: PromptLike) -> List[LLMMessage]:
    """文字列 / メッセージ辞書のリスト / LLMMessage のリストを LLMMessage 列へ正規化。"""
    if isinstance(prompt, str):
        return [LLMMessage(role="user", content=prompt)]

    messages: List[LLMMessage] = []
    for item in prompt:
        if isinstance(item, LLMMessage):
            messages.append(item)
        elif isinstance(item, dict):
            messages.append(
                LLMMessage(
                    role=str(item.get("role", "user")),
                    content=str(item.get("content", "") or ""),
                    name=item.get("name"),
                    tool_calls=item.get("tool_calls"),
                )
            )
        else:
            messages.append(LLMMessage(role="user", content=str(item)))
    return messages


class LLMClient:
    """同期/非同期の双方から使える LLMProvider アダプタ。

    既存の `.invoke()` / `.complete()` 呼び出し規約を満たしつつ、内部は
    プロバイダー非依存の `LLMProvider.generate()` に委譲する。
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> None:
        self._provider = provider
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    @property
    def provider_name(self) -> str:
        return getattr(self._provider, "provider_name", "")

    # --- 同期インターフェース（既存エージェント互換） --- #

    def invoke(self, prompt: PromptLike, **kwargs: Any) -> LLMResponse:
        """`llm_client.invoke(prompt)` 互換。LLMResponse（.content を持つ）を返す。"""
        return _run_sync(self.ainvoke(prompt, **kwargs))

    def complete(self, messages: PromptLike, **kwargs: Any) -> str:
        """`llm_client.complete(messages)` 互換。content 文字列を返す。"""
        return self.invoke(messages, **kwargs).content

    def generate_json(self, prompt: PromptLike, *, schema: Any = None, **kwargs: Any) -> Dict[str, Any]:
        """JSONオブジェクトを期待する同期生成。

        provider のネイティブJSONモード（対応時）＋堅牢抽出のフォールバックで
        プロバイダー差を吸収する（async の `agenerate_json` / `LLMProvider.generate_json`
        と同一経路）。`schema` は将来のネイティブ構造化出力用に予約（現状は未使用）。
        """
        return _run_sync(self.agenerate_json(prompt, **kwargs))

    # --- 非同期インターフェース --- #

    async def ainvoke(self, prompt: PromptLike, **kwargs: Any) -> LLMResponse:
        kwargs.setdefault("temperature", self._temperature)
        kwargs.setdefault("max_tokens", self._max_tokens)
        return await self._provider.generate(_coerce_messages(prompt), **kwargs)

    async def agenerate_json(self, prompt: PromptLike, **kwargs: Any) -> Dict[str, Any]:
        kwargs.setdefault("temperature", self._temperature)
        kwargs.setdefault("max_tokens", self._max_tokens)
        return await self._provider.generate_json(_coerce_messages(prompt), **kwargs)


# --------------------------------------------------------------------------- #
# 既定プロバイダー / APIキー解決                                                #
# --------------------------------------------------------------------------- #


def _load_gui_settings() -> Dict[str, Any]:
    try:
        if _SETTINGS_FILE.exists():
            data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def resolve_default_provider(settings: Optional[Dict[str, Any]] = None) -> str:
    """既定プロバイダー名を解決する（環境変数 > GUI設定 > anthropic）。"""
    s = settings if settings is not None else _load_gui_settings()
    provider = os.getenv("REPOCORP_DEFAULT_LLM_PROVIDER") or s.get("llm_provider") or "anthropic"
    return provider if provider in PROVIDER_KEY_MAPPING else "anthropic"


def resolve_provider_api_key(provider: str, settings: Optional[Dict[str, Any]] = None) -> str:
    """指定プロバイダーのAPIキーを解決する（api_keys辞書 > トップレベル設定 > 環境変数）。"""
    s = settings if settings is not None else _load_gui_settings()
    setting_key, env_var = PROVIDER_KEY_MAPPING.get(provider, ("", ""))
    if not setting_key:
        return ""
    api_keys = s.get("api_keys") if isinstance(s.get("api_keys"), dict) else {}
    return str(api_keys.get(provider) or s.get(setting_key) or os.getenv(env_var, "") or "")


def resolve_default_model(settings: Optional[Dict[str, Any]] = None) -> str:
    """既定モデル名を解決する（環境変数 > GUI設定 > 空文字）。空ならプロバイダー既定を使う。"""
    s = settings if settings is not None else _load_gui_settings()
    return os.getenv("REPOCORP_DEFAULT_MODEL") or s.get("llm_model") or ""


# provider インスタンスのキャッシュ（B11）。キーに api_key/model を含むため、
# 設定変更（キー/モデル差し替え）時は自然に別エントリとなり stale を避けられる。
_provider_cache: Dict[tuple[str, str, str], LLMProvider] = {}


def reset_provider_cache() -> None:
    """provider キャッシュを破棄する（テスト/設定全更新時に使用）。"""
    _provider_cache.clear()


def get_configured_llm_provider(
    provider_name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> Optional[LLMProvider]:
    """GUI設定/環境変数から APIキーを解決して LLMProvider を構築する。

    `LLMConfig.from_env()` は環境変数しか見ないため、GUI で保存したキーが
    効かない。この関数は gui_settings.json も参照してキーを config に流し込むので、
    provider ベースのエージェント（CodeReviewAgent など）が GUI 保存キーでも動く。
    キーが解決できない場合は None を返す。同一 (provider, key, model) はキャッシュする（B11）。
    """
    s = settings if settings is not None else _load_gui_settings()
    provider = provider_name or resolve_default_provider(s)
    api_key = resolve_provider_api_key(provider, s)
    if not api_key:
        return None

    model = resolve_default_model(s)
    cache_key = (provider, api_key, model)
    cached = _provider_cache.get(cache_key)
    if cached is not None:
        return cached

    config = LLMConfig(
        default_provider=provider,
        default_model=model or LLMConfig().default_model,
        api_keys={provider: api_key},
    )
    try:
        from core.llm import get_llm_provider

        provider_obj = get_llm_provider(provider, config=config)
    except Exception:
        return None
    _provider_cache[cache_key] = provider_obj
    return provider_obj


def get_default_llm_client(settings: Optional[Dict[str, Any]] = None) -> Optional[LLMClient]:
    """GUI設定/環境変数から既定 LLMClient を構築する。

    APIキーが解決できない場合は None を返す。呼び出し側（main._get_orchestrator や
    web/server の実行エントリ）は None をそのままエージェントへ渡し、従来の
    テンプレート/フォールバック動作を維持する（＝キー未設定環境では挙動不変）。
    """
    s = settings if settings is not None else _load_gui_settings()
    provider_obj = get_configured_llm_provider(settings=s)
    return LLMClient(provider_obj) if provider_obj is not None else None
