"""Tests for Gemini provider."""

from unittest.mock import patch

import pytest

from core.llm import get_llm_provider
from core.llm.base import LLMConfig
from core.llm.gemini_provider import GeminiProvider


def test_gemini_provider_requires_api_key():
    """GOOGLE_API_KEY がない場合はエラーになること"""
    config = LLMConfig(default_provider="gemini", default_model="gemini-2.0-flash", api_keys={})

    with patch.dict("os.environ", {}, clear=True):
        provider = GeminiProvider(config)
        with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
            provider._get_genai()


def test_gemini_provider_init_with_api_key():
    """GOOGLE_API_KEY がある場合に Gemini SDK を初期化できること"""
    config = LLMConfig(default_provider="gemini", default_model="gemini-2.0-flash", api_keys={})

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "AIza-test-key"}, clear=True):
        with patch("google.generativeai.configure") as mock_configure:
            provider = GeminiProvider(config)
            genai = provider._get_genai()

    assert genai.__name__ == "google.generativeai"
    mock_configure.assert_called_once_with(api_key="AIza-test-key")


def test_get_llm_provider_supports_gemini():
    provider = get_llm_provider(
        "gemini",
        config=LLMConfig(default_model="gemini-2.0-flash", api_keys={"gemini": "AIza-test-key"}),
    )

    assert isinstance(provider, GeminiProvider)
    assert provider.provider_name == "gemini"
