"""
RepoCorp AI - LLM Provider Package

使用例:
    from core.llm import get_llm_provider

    provider = get_llm_provider("anthropic")
    response = await provider.generate(messages=[...])
"""

from .anthropic_provider import AnthropicProvider
from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse
from .gemini_provider import GeminiProvider
from .github_models_provider import GitHubModelsProvider
from .openai_provider import OpenAIProvider

__all__ = [
    "LLMProvider",
    "LLMMessage",
    "LLMResponse",
    "LLMConfig",
    "AnthropicProvider",
    "OpenAIProvider",
    "GitHubModelsProvider",
    "GeminiProvider",
]


def get_llm_provider(
    provider_name: str | None = None,
    config: LLMConfig | None = None,
) -> LLMProvider:
    """プロバイダー名からインスタンスを返すファクトリ関数"""
    config = config or LLMConfig.from_env()
    selected_provider = provider_name or config.default_provider

    if selected_provider == "anthropic":
        return AnthropicProvider(config)
    if selected_provider in {"openai", "groq"}:
        return OpenAIProvider(config, provider_name=selected_provider)
    if selected_provider == "github_models":
        return GitHubModelsProvider(config)
    if selected_provider == "gemini":
        return GeminiProvider(config)
    raise ValueError(f"Unknown LLM provider: {selected_provider}")
