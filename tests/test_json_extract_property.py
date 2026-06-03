"""json_extract のプロパティ風テスト（F9）。

固定シードの乱数で多様なネスト構造を生成し、JSON 化してノイズ（前置き文/後置き文/
コードフェンス）で包んでも `extract_json_object` / `extract_json` が元の値を復元することを確認する。
hypothesis 非依存（決定論的）。
"""

from __future__ import annotations

import json
import random

from core.llm.json_extract import extract_json, extract_json_object


def _rand_json_value(rng: random.Random, depth: int = 0):
    if depth >= 3:
        return rng.choice([rng.randint(-1000, 1000), rng.random(), _rand_str(rng), True, False, None])
    kind = rng.choice(["int", "float", "str", "bool", "null", "list", "dict"])
    if kind == "int":
        return rng.randint(-10000, 10000)
    if kind == "float":
        return round(rng.random() * 1000, 4)
    if kind == "str":
        return _rand_str(rng)
    if kind == "bool":
        return rng.choice([True, False])
    if kind == "null":
        return None
    if kind == "list":
        return [_rand_json_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return {_rand_str(rng): _rand_json_value(rng, depth + 1) for _ in range(rng.randint(1, 4))}


def _rand_str(rng: random.Random) -> str:
    alphabet = "abcXYZ 日本語_-{}[]\"',:0129"
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8)))


def _rand_dict(rng: random.Random) -> dict:
    return {f"k{i}": _rand_json_value(rng, 1) for i in range(rng.randint(1, 5))}


def test_extract_json_object_roundtrips_with_noise():
    rng = random.Random(1234)
    for _ in range(200):
        obj = _rand_dict(rng)
        encoded = json.dumps(obj, ensure_ascii=False)
        wrapper = rng.choice([
            "{body}",
            "Sure! Here is the result:\n{body}\nLet me know if you need more.",
            "```json\n{body}\n```",
            "```\n{body}\n```",
            "前置きの説明。\n{body}",
        ])
        text = wrapper.format(body=encoded)
        assert extract_json_object(text) == obj


def test_extract_json_handles_arrays_with_noise():
    rng = random.Random(99)
    for _ in range(100):
        arr = [_rand_json_value(rng, 1) for _ in range(rng.randint(0, 5))]
        encoded = json.dumps(arr, ensure_ascii=False)
        text = rng.choice(["{body}", "prefix {body} suffix", "```json\n{body}\n```"]).format(body=encoded)
        assert extract_json(text) == arr


def test_extract_json_object_returns_none_for_non_json():
    for text in ["", "   ", "no json here", "12345 plain", "</html>"]:
        assert extract_json_object(text) is None


def test_extract_json_object_takes_first_valid_object():
    assert extract_json_object('noise {"a": 1} more {"b": 2}') == {"a": 1}
