"""
Anthropic Claude Provider Implementation
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator, Dict, List, Optional

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.from_env()
        self._client = None  # 遅延初期化

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError("anthropic package is required. pip install anthropic")
            api_key = self.config.api_keys.get("anthropic") or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY is not set")
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        return self._client

    def get_model_name(self, task_type: str = "default") -> str:
        # 将来的にタスク種別でモデルを切り替えるロジックをここに
        if task_type == "fast":
            return "claude-3-5-haiku-20241022"
        if task_type == "reasoning":
            return "claude-3-5-sonnet-20241022"
        return self.config.default_model

    async def generate(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()
        model_name = model or self.get_model_name()

        # Anthropic形式に変換
        system_prompt = None
        anthropic_messages = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                anthropic_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

        response = await client.messages.create(
            model=model_name,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=anthropic_messages,
            tools=tools,
            tool_choice={"type": tool_choice} if tool_choice else None,
            **kwargs,
        )

        content = ""
        tool_calls = None
        if response.content:
            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    if tool_calls is None:
                        tool_calls = []
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

        return LLMResponse(
            content=content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            } if response.usage else None,
            finish_reason=response.stop_reason,
            tool_calls=tool_calls,
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

        system_prompt = None
        anthropic_messages = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                anthropic_messages.append({"role": msg.role, "content": msg.content})

        async with client.messages.stream(
            model=model_name,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=anthropic_messages,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                    yield event.delta.text
