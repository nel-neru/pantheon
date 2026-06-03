"""
LLM出力からの堅牢なJSON抽出ユーティリティ。

LLMプロバイダーによってJSON出力の癖が異なる（コードフェンス付与、前置き説明文、
複数オブジェクトの混在など）。プロバイダー非依存でJSONを取り出すための共通関数を
ここに集約する。各エージェントが個別に `json.loads()` するのではなく、
これらを通すことでプロバイダー差を吸収する。
"""

from __future__ import annotations

import json
from typing import Any, Optional

__all__ = ["strip_code_fences", "extract_json_object", "extract_json"]


def strip_code_fences(text: str) -> str:
    """Markdown のコードフェンス（```json ... ```）を取り除いて中身だけ返す。

    フェンスが無い場合は元のテキストをそのまま返す。
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    # 先頭の ``` または ```json 行を除去
    newline = stripped.find("\n")
    if newline == -1:
        return stripped
    body = stripped[newline + 1 :]

    # 末尾の ``` を除去
    fence_end = body.rfind("```")
    if fence_end != -1:
        body = body[:fence_end]
    return body.strip()


def _scan_for_value(content: str, opener: str) -> Optional[Any]:
    """`opener`（'{' または '['）から始まる最初の有効なJSON値を raw_decode で探す。"""
    decoder = json.JSONDecoder()
    start = content.find(opener)
    while start != -1:
        try:
            payload, _ = decoder.raw_decode(content[start:])
        except json.JSONDecodeError:
            start = content.find(opener, start + 1)
            continue
        return payload
    return None


def extract_json_object(content: str) -> Optional[dict[str, Any]]:
    """テキストから最初に現れる有効なJSON「オブジェクト」を返す。無ければ None。

    1. コードフェンスを剥がして全体を json.loads で試す
    2. 失敗したら最初の '{' から raw_decode で走査する
    """
    if not content:
        return None

    cleaned = strip_code_fences(content)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    value = _scan_for_value(cleaned, "{")
    return value if isinstance(value, dict) else None


def extract_json(content: str) -> Optional[Any]:
    """テキストからオブジェクト/配列いずれかの最初の有効なJSON値を返す。無ければ None。"""
    if not content:
        return None

    cleaned = strip_code_fences(content)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    obj_start = cleaned.find("{")
    arr_start = cleaned.find("[")
    if obj_start == -1 and arr_start == -1:
        return None
    if arr_start == -1 or (obj_start != -1 and obj_start < arr_start):
        return _scan_for_value(cleaned, "{")
    return _scan_for_value(cleaned, "[")
