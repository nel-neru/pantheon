"""Tests for GitHub Models provider."""

from unittest.mock import patch

import pytest

from core.llm import get_llm_provider
from core.llm.base import LLMConfig
from core.llm.github_models_provider import GitHubModelsProvider



def test_github_models_provider_requires_token():
    """GITHUB_TOKEN がない場合はエラーになること"""
    config = LLMConfig(default_provider="github_models", default_model="gpt-4o", api_keys={})

    with patch.dict("os.environ", {}, clear=True):
        provider = GitHubModelsProvider(config)
        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            provider._get_client()



def test_github_models_provider_init_with_token():
    """GITHUB_TOKEN がある場合に OpenAI 互換クライアントを初期化できること"""
    config = LLMConfig(default_provider="github_models", default_model="gpt-4o", api_keys={})

    with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test_token"}, clear=True):
        with patch("openai.AsyncOpenAI") as mock_client:
            provider = GitHubModelsProvider(config)
            client = provider._get_client()

    assert client is mock_client.return_value
    mock_client.assert_called_once_with(
        api_key="ghp_test_token",
        base_url=GitHubModelsProvider.BASE_URL,
    )



def test_get_llm_provider_uses_github_models_default_provider():
    """default_provider が github_models のときファクトリが正しい実装を返すこと"""
    config = LLMConfig(
        default_provider="github_models",
        default_model="gpt-4o",
        api_keys={"github_models": "ghp_from_config"},
    )

    provider = get_llm_provider(config=config)

    assert isinstance(provider, GitHubModelsProvider)
