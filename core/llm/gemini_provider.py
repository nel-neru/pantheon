"""
Google Gemini Provider Implementation
"""

from __future__ import annotations

import asyncio
import os
import warnings
from typing import Any, AsyncIterator, Dict, List, Optional

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse
from .json_mode import GEMINI_JSON_MIME_TYPE
from .retry import call_with_retry
from .usage import record_usage


class GeminiProvider(LLMProvider):
    DEFAULT_MODELS = {
        "default": "gemini-2.0-flash",
        "fast": "gemini-2.0-flash-lite",
        "reasoning": "gemini-1.5-pro",
    }

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.from_env()
        self._genai = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _get_genai(self):
        if self._genai is None:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", FutureWarning)
                    import google.generativeai as genai
            except ImportError as exc:
                raise ImportError("google-generativeai package is required. pip install google-generativeai") from exc

            api_key = self.config.api_keys.get("gemini") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY is not set")

            genai.configure(api_key=api_key)
            self._genai = genai
        return self._genai

    def get_model_name(self, task_type: str = "default") -> str:
        if task_type in self.DEFAULT_MODELS:
            default_model = self.DEFAULT_MODELS[task_type]
        else:
            default_model = self.DEFAULT_MODELS["default"]
        return self.config.default_model or default_model

    @staticmethod
    def _normalize_messages(messages: List[LLMMessage]) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []

        for message in messages:
            if message.role == "system":
                if message.content:
                    system_parts.append(message.content)
                continue

            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [message.content]})

        return ("\n\n".join(system_parts) or None, contents)

    @staticmethod
    def _normalize_tools(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        if not tools:
            return None

        declarations = []
        for tool in tools:
            function = tool.get("function", tool)
            declarations.append(
                {
                    "name": function["name"],
                    "description": function.get("description", ""),
                    "parameters": function.get(
                        "parameters",
                        function.get("input_schema", {"type": "object", "properties": {}, "required": []}),
                    ),
                }
            )

        return [{"function_declarations": declarations}]

    @staticmethod
    def _normalize_tool_choice(tool_choice: Optional[str | Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if tool_choice is None:
            return None
        if isinstance(tool_choice, dict):
            function_name = tool_choice.get("function", {}).get("name")
            if function_name:
                return {
                    "function_calling_config": {
                        "mode": "ANY",
                        "allowed_function_names": [function_name],
                    }
                }
            return None
        if tool_choice == "none":
            return {"function_calling_config": {"mode": "NONE"}}
        if tool_choice == "required":
            return {"function_calling_config": {"mode": "ANY"}}
        if tool_choice == "auto":
            return {"function_calling_config": {"mode": "AUTO"}}
        return {
            "function_calling_config": {
                "mode": "ANY",
                "allowed_function_names": [tool_choice],
            }
        }

    @staticmethod
    def _to_plain_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: GeminiProvider._to_plain_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [GeminiProvider._to_plain_value(item) for item in value]
        if hasattr(value, "items"):
            return {key: GeminiProvider._to_plain_value(item) for key, item in value.items()}
        return value

    @classmethod
    def _extract_content_and_tool_calls(cls, response: Any) -> tuple[str, Optional[List[Dict[str, Any]]]]:
        text_parts: list[str] = []
        tool_calls: list[Dict[str, Any]] = []

        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                text = getattr(part, "text", "")
                if text:
                    text_parts.append(text)
                function_call = getattr(part, "function_call", None)
                function_name = getattr(function_call, "name", "") if function_call else ""
                if function_name:
                    tool_calls.append(
                        {
                            "id": function_name,
                            "name": function_name,
                            "input": cls._to_plain_value(getattr(function_call, "args", {})),
                        }
                    )

        if not text_parts:
            text = getattr(response, "text", "")
            if text:
                text_parts.append(text)

        return "".join(text_parts), tool_calls or None

    @staticmethod
    def _extract_usage(response: Any) -> Optional[Dict[str, int]]:
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return None

        prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        completion_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
        total_tokens = int(getattr(usage, "total_token_count", prompt_tokens + completion_tokens) or 0)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

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
        genai = self._get_genai()
        model_name = model or self.get_model_name()
        system_instruction, content_messages = self._normalize_messages(messages)
        gemini_model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction,
            tools=self._normalize_tools(tools),
        )

        generation_config: Dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens or self.config.max_tokens,
        }
        if json_mode:
            generation_config["response_mime_type"] = GEMINI_JSON_MIME_TYPE
        request_kwargs: Dict[str, Any] = {"generation_config": generation_config}
        tool_config = self._normalize_tool_choice(tool_choice)
        if tool_config:
            request_kwargs["tool_config"] = tool_config
        request_kwargs.update(kwargs)

        response = await call_with_retry(
            lambda: asyncio.to_thread(
                gemini_model.generate_content,
                content_messages,
                **request_kwargs,
            ),
            provider="gemini",
        )
        content, tool_calls = self._extract_content_and_tool_calls(response)
        candidates = getattr(response, "candidates", []) or []
        finish_reason = str(getattr(candidates[0], "finish_reason", "")) if candidates else None

        result = LLMResponse(
            content=content,
            model=model_name,
            usage=self._extract_usage(response),
            finish_reason=finish_reason or None,
            tool_calls=tool_calls,
        )
        record_usage("gemini", result.model, result.usage)
        return result

    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        genai = self._get_genai()
        model_name = model or self.get_model_name()
        system_instruction, content_messages = self._normalize_messages(messages)
        gemini_model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction,
        )

        def _collect_chunks() -> list[str]:
            response = gemini_model.generate_content(
                content_messages,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens or self.config.max_tokens,
                },
                stream=True,
                **kwargs,
            )
            chunks: list[str] = []
            for chunk in response:
                text, _ = GeminiProvider._extract_content_and_tool_calls(chunk)
                if text:
                    chunks.append(text)
            return chunks

        for chunk in await asyncio.to_thread(_collect_chunks):
            yield chunk

    @classmethod
    def list_models(cls, api_key: str) -> list[str]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                import google.generativeai as genai
        except ImportError:
            return []

        try:
            genai.configure(api_key=api_key)
            models = []
            for model in genai.list_models():
                methods = getattr(model, "supported_generation_methods", []) or []
                if "generateContent" not in methods:
                    continue
                name = str(getattr(model, "name", "")).removeprefix("models/")
                if name.startswith("gemini"):
                    models.append(name)
            return sorted(set(models))
        except Exception:
            return []
