"""
OpenAI-compatible Provider Implementation (OpenAI, Groq)
"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse


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

    @staticmethod
    def _normalize_tools(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        if not tools:
            return None

        normalized = []
        for tool in tools:
            if tool.get("type") == "function" and "function" in tool:
                normalized.append(tool)
                continue

            normalized.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get(
                            "input_schema",
                            {"type": "object", "properties": {}, "required": []},
                        ),
                    },
                }
            )
        return normalized

    @staticmethod
    def _normalize_tool_choice(tool_choice: Optional[str | Dict[str, Any]]) -> Optional[str | Dict[str, Any]]:
        if tool_choice is None:
            return None
        if isinstance(tool_choice, str) and tool_choice in {"auto", "none", "required"}:
            return tool_choice
        if isinstance(tool_choice, str):
            return {"type": "function", "function": {"name": tool_choice}}
        return tool_choice

    @staticmethod
    def _parse_tool_calls(choice_message: Any) -> Optional[List[Dict[str, Any]]]:
        if not getattr(choice_message, "tool_calls", None):
            return None

        parsed_calls = []
        for tool_call in choice_message.tool_calls:
            raw_arguments = tool_call.function.arguments or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = raw_arguments
            parsed_calls.append(
                {
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "input": arguments,
                }
            )
        return parsed_calls

    async def generate(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str | Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()
        model_name = model or self.get_model_name()

        openai_messages = [{"role": m.role, "content": m.content} for m in messages]

        response = await client.chat.completions.create(
            model=model_name,
            messages=openai_messages,
            temperature=temperature,
            max_tokens=max_tokens or self.config.max_tokens,
            tools=self._normalize_tools(tools),
            tool_choice=self._normalize_tool_choice(tool_choice),
            **kwargs,
        )

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage=response.usage.model_dump() if response.usage else None,
            finish_reason=choice.finish_reason,
            tool_calls=self._parse_tool_calls(choice.message),
        )

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
