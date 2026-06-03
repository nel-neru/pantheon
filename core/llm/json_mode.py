"""
ネイティブ JSON モードのヘルパ（プロバイダー非依存の構造化出力）。

各プロバイダーが「ネイティブな JSON 出力」を要求するための定数と補助を集約する。
- OpenAI 互換: `response_format={"type": "json_object"}`。ただし messages のどこかに
  "json" という語を含むことを API が要求する（含まないと 400 を返す）ため、
  含まれない場合は system メッセージで補う。
- Gemini: `generation_config.response_mime_type = "application/json"`。

どのモードを使うかは `core/llm/capabilities.py` の `supports_json_mode` で宣言し、
`LLMProvider.generate_json` が capabilities 連動で `json_mode=True` を渡す。
ネイティブモードが使えない/失敗した場合でも、最終的には `json_extract` の
堅牢抽出にフォールバックするため安全（純粋な上積み）。
"""

from __future__ import annotations

from typing import Any, Dict, List

__all__ = [
    "OPENAI_JSON_RESPONSE_FORMAT",
    "GEMINI_JSON_MIME_TYPE",
    "ensure_json_keyword",
]

# OpenAI 互換 (OpenAI / Groq / GitHub Models) の JSON モード指定。
OPENAI_JSON_RESPONSE_FORMAT: Dict[str, str] = {"type": "json_object"}

# Gemini の JSON モード指定（generation_config.response_mime_type）。
GEMINI_JSON_MIME_TYPE = "application/json"

# messages に "json" が無いとき補う指示（OpenAI の json_object モード要件を満たす）。
_JSON_NUDGE = "Respond with a single valid JSON object and nothing else."


def ensure_json_keyword(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """OpenAI の `json_object` モードは messages に "json" を含むことを要求する。

    どのメッセージ本文にも "json"（大文字小文字無視）が無ければ、末尾に system
    メッセージで指示を補う。既存メッセージは変更せず、必要時のみ新しいリストを返す。
    """
    for message in messages:
        if "json" in str(message.get("content", "")).lower():
            return messages
    return [*messages, {"role": "system", "content": _JSON_NUDGE}]
