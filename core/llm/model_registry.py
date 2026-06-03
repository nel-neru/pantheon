"""
model_registry — モデル情報の唯一の正典

これまで web/server.py の FALLBACK_MODELS、各 provider の DEFAULT_MODELS や
get_model_name のタスク別ヒューリスティックに散在していたモデル名を集約する。
API/UI（プロバイダー別モデル一覧）と provider 実装の双方がここを参照することで、
「どのプロバイダーにどのモデルがあるか」を一箇所で管理する。

API 経由で実モデル一覧が取れない場合のフォールバックにも使う。
"""

from __future__ import annotations

from typing import Dict, List

__all__ = [
    "FALLBACK_MODELS",
    "DEFAULT_MODELS",
    "TASK_MODELS",
    "get_fallback_models",
    "get_default_model",
    "get_task_model",
    "known_providers",
]

# provider -> 代表的なモデル一覧（API取得不可時のフォールバック / UIの初期候補）
FALLBACK_MODELS: Dict[str, List[str]] = {
    "anthropic": [
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1",
        "o1-mini",
        "o3-mini",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ],
    "github_models": [
        "gpt-4o",
        "gpt-4o-mini",
        "claude-3-5-sonnet",
        "meta-llama-3-70b-instruct",
        "mistral-large",
        "phi-3-medium-instruct-128k",
        "ai21-jamba-instruct",
    ],
    "gemini": [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-pro-exp",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ],
}

# provider -> 既定モデル（明示指定が無い場合に使う）
DEFAULT_MODELS: Dict[str, str] = {
    "anthropic": "claude-3-5-sonnet-20241022",
    "openai": "gpt-4o",
    "groq": "llama-3.1-70b-versatile",
    "github_models": "gpt-4o",
    "gemini": "gemini-2.0-flash",
}

# provider -> {task_type: model} タスク種別ごとの推奨モデル
TASK_MODELS: Dict[str, Dict[str, str]] = {
    "anthropic": {
        "default": "claude-3-5-sonnet-20241022",
        "fast": "claude-3-5-haiku-20241022",
        "reasoning": "claude-3-5-sonnet-20241022",
    },
    "openai": {
        "default": "gpt-4o",
        "fast": "gpt-4o-mini",
        "reasoning": "gpt-4o",
    },
    "groq": {
        "default": "llama-3.1-70b-versatile",
        "fast": "llama-3.1-8b-instant",
        "reasoning": "llama-3.1-70b-versatile",
    },
    "github_models": {
        "default": "gpt-4o",
        "fast": "gpt-4o-mini",
        "reasoning": "gpt-4o",
    },
    "gemini": {
        "default": "gemini-2.0-flash",
        "fast": "gemini-2.0-flash-lite",
        "reasoning": "gemini-1.5-pro",
    },
}


def known_providers() -> List[str]:
    """登録済みプロバイダー名の一覧。"""
    return list(FALLBACK_MODELS.keys())


def get_fallback_models(provider: str) -> List[str]:
    """プロバイダーのフォールバックモデル一覧を返す（未登録なら空）。"""
    return list(FALLBACK_MODELS.get(provider, []))


def get_default_model(provider: str) -> str:
    """プロバイダーの既定モデルを返す（未登録なら空文字）。"""
    return DEFAULT_MODELS.get(provider, "")


def get_task_model(provider: str, task_type: str = "default") -> str:
    """タスク種別に応じた推奨モデルを返す。該当が無ければ既定モデルにフォールバック。"""
    provider_models = TASK_MODELS.get(provider, {})
    return provider_models.get(task_type) or provider_models.get("default") or get_default_model(provider)
