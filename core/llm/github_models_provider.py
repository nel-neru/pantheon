"""
GitHub Models Provider Implementation (OpenAI-compatible)
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator, Dict, List, Optional

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse
from .json_mode import OPENAI_JSON_RESPONSE_FORMAT, ensure_json_keyword
from .retry import call_with_retry
from .tool_schema import parse_openai_tool_calls, to_openai_tool_choice, to_openai_tools
from .usage import record_usage


class GitHubModelsProvider(LLMProvider):
    BASE_URL = "https://models.inference.ai.azure.com"

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.from_env()
        self._client = None

    @property
    def provider_name(self) -> str:
        return "github_models"

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError("openai package is required. pip install openai")
            api_key = self.config.api_keys.get("github_models") or os.getenv("GITHUB_TOKEN")
            if not api_key:
                raise ValueError("GITHUB_TOKEN is not set")
            self._client = AsyncOpenAI(api_key=api_key, base_url=self.BASE_URL)
        return self._client

    def get_model_name(self, task_type: str = "default") -> str:
        if task_type == "fast":
            return "gpt-4o-mini"
        if task_type == "reasoning":
            return "gpt-4o"
        return self.config.default_model or "gpt-4o"

    async def generate(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()
        model_name = model or self.get_model_name()

        openai_messages = [
            {"role": message.role, "content": message.content} for message in messages
        ]

        create_kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "tools": to_openai_tools(tools),
            "tool_choice": to_openai_tool_choice(tool_choice),
            **kwargs,
        }
        if json_mode:
            create_kwargs["messages"] = ensure_json_keyword(openai_messages)
            create_kwargs["response_format"] = dict(OPENAI_JSON_RESPONSE_FORMAT)

        response = await call_with_retry(
            lambda: client.chat.completions.create(**create_kwargs),
            provider="github_models",
        )

        choice = response.choices[0]
        result = LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage=response.usage.model_dump() if response.usage else None,
            finish_reason=choice.finish_reason,
            tool_calls=parse_openai_tool_calls(choice.message),
        )
        record_usage("github_models", result.model, result.usage)
        return result

    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        model_name = model or self.get_model_name()

        openai_messages = [{"role": message.role, "content": message.content} for message in messages]

        stream = await client.chat.completions.create(
            model=model_name,
            messages=openai_messages,
            temperature=temperature,
            max_tokens=max_tokens or self.config.max_tokens,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
