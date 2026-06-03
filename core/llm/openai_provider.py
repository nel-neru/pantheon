"""
OpenAI-compatible Provider Implementation (OpenAI, Groq)
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator, Dict, List, Optional

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse
from .json_mode import OPENAI_JSON_RESPONSE_FORMAT, ensure_json_keyword
from .retry import call_with_retry
from .tool_schema import parse_openai_tool_calls, to_openai_tool_choice, to_openai_tools
from .usage import record_usage


class OpenAIProvider(LLMProvider):
    BASE_URLS = {
        "openai": None,
        "groq": "https://api.groq.com/openai/v1",
    }
    API_KEY_ENV_VARS = {
        "openai": "OPENAI_API_KEY",
        "groq": "GROQ_API_KEY",
    }
    DEFAULT_MODELS = {
        "openai": "gpt-4o",
        "groq": "llama-3.1-70b-versatile",
    }

    def __init__(self, config: Optional[LLMConfig] = None, provider_name: str = "openai"):
        if provider_name not in self.BASE_URLS:
            raise ValueError(f"Unsupported OpenAI-compatible provider: {provider_name}")
        self.config = config or LLMConfig.from_env()
        self._provider_name = provider_name
        self._client = None

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError("openai package is required. pip install openai")

            env_var = self.API_KEY_ENV_VARS[self._provider_name]
            api_key = self.config.api_keys.get(self._provider_name) or os.getenv(env_var)
            if not api_key:
                raise ValueError(f"{env_var} is not set")

            kwargs: Dict[str, Any] = {"api_key": api_key}
            base_url = self.BASE_URLS[self._provider_name]
            if base_url:
                kwargs["base_url"] = base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def get_model_name(self, task_type: str = "default") -> str:
        if task_type == "fast":
            if self._provider_name == "groq":
                return "llama-3.1-8b-instant"
            return "gpt-4o-mini"
        if task_type == "reasoning":
            if self._provider_name == "groq":
                return "llama-3.1-70b-versatile"
            return "gpt-4o"
        return self.config.default_model or self.DEFAULT_MODELS[self._provider_name]

    async def generate(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str | Dict[str, Any]] = None,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()
        model_name = model or self.get_model_name()

        openai_messages = [{"role": m.role, "content": m.content} for m in messages]

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
            # response_format=json_object は messages に "json" を要求するため補う
            create_kwargs["messages"] = ensure_json_keyword(openai_messages)
            create_kwargs["response_format"] = dict(OPENAI_JSON_RESPONSE_FORMAT)

        response = await call_with_retry(
            lambda: client.chat.completions.create(**create_kwargs),
            provider=self._provider_name,
        )

        choice = response.choices[0]
        result = LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage=response.usage.model_dump() if response.usage else None,
            finish_reason=choice.finish_reason,
            tool_calls=parse_openai_tool_calls(choice.message),
        )
        record_usage(self._provider_name, result.model, result.usage)
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

        openai_messages = [{"role": m.role, "content": m.content} for m in messages]

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
