"""画像生成 — エピソードブリーフの image_prompts を外部AIで実画像にする（認証ゲート・偽画像なし）。

各カットのプロンプトに、ブリーフが既にカノンから注入済みの style_suffix・negative・character_refs
（固定 seed）が乗っているので、ここはそれを provider API へ渡して**実ファイル**を得るだけ。

正直性: 鍵が無ければ ``MediaProviderNotConfigured``（1件も生成しない）。API 呼び出しが失敗/想定外
レスポンスなら、そのカットは ``ImageResult(ok=False, error=...)`` を返す＝**偽の画像やプレース
ホルダは書かない**。HTTP は ``transport`` で注入可能（テストは実ネットワーク不要でロジック検証）。

注: provider の endpoint/model は各社ドキュメント準拠の既定値。実アカウントでの最終確認は
利用者の鍵が要る（＝人間でないとできない部分）。model は引数で上書きできる。
"""

from __future__ import annotations

import base64
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.media.credentials import require_api_key

# provider 既定 model（ドキュメント準拠・上書き可）。
_DEFAULT_MODEL = {
    "gemini": "gemini-2.5-flash-image-preview",  # 通称 Nano Banana（画像生成対応）
    "fal": "fal-ai/flux/dev",
}

# aspect → fal image_size 列挙の対応（gemini はプロンプト文に含める）。
_FAL_SIZE = {"16:9": "landscape_16_9", "9:16": "portrait_16_9", "1:1": "square_hd"}


@dataclass
class ImageResult:
    shot_id: str
    ok: bool
    path: Optional[str] = None
    error: str = ""


class _UrllibTransport:
    """既定の HTTP transport（標準ライブラリのみ・外部 SDK 非依存）。"""

    def post_json(
        self, url: str, headers: Dict[str, str], payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json", **headers}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 — 既知の https API
            return json.loads(resp.read().decode("utf-8"))

    def get_bytes(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            return resp.read()


def _full_prompt(prompt: Dict[str, Any]) -> str:
    positive = str(prompt.get("positive") or "").strip()
    style = str(prompt.get("style_suffix") or "").strip()
    negative = str(prompt.get("negative_prompt") or "").strip()
    text = f"{positive} {style}".strip()
    if negative:
        text = f"{text}. Avoid: {negative}"
    return text


def _gemini_image_bytes(
    transport: Any, *, api_key: str, model: str, prompt: Dict[str, Any]
) -> bytes:
    """Gemini 画像 API を呼び、最初の inline 画像の bytes を返す（想定外は ValueError）。"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    text = _full_prompt(prompt)
    aspect = str(prompt.get("aspect") or "16:9")
    payload = {
        "contents": [{"parts": [{"text": f"{text}. Aspect ratio {aspect}."}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    resp = transport.post_json(url, {}, payload)
    for cand in resp.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise ValueError(f"画像が返りませんでした（response keys={list(resp)}）")


def _fal_image_bytes(transport: Any, *, api_key: str, model: str, prompt: Dict[str, Any]) -> bytes:
    """fal.ai（Flux 等）を呼び、生成画像 URL を辿って bytes を返す（想定外は ValueError）。"""
    url = f"https://fal.run/{model}"
    aspect = str(prompt.get("aspect") or "16:9")
    payload = {
        "prompt": _full_prompt(prompt),
        "image_size": _FAL_SIZE.get(aspect, "landscape_16_9"),
    }
    # 学習済みスタイル LoRA があれば適用（カノン由来＝署名スタイルを重みで固定）。
    loras = prompt.get("loras")
    if loras:
        payload["loras"] = loras
    resp = transport.post_json(url, {"Authorization": f"Key {api_key}"}, payload)
    images = resp.get("images") or []
    if images and images[0].get("url"):
        return transport.get_bytes(str(images[0]["url"]))
    raise ValueError(f"画像 URL が返りませんでした（response keys={list(resp)}）")


_PROVIDERS: Dict[str, Callable[..., bytes]] = {
    "gemini": _gemini_image_bytes,
    "fal": _fal_image_bytes,
}


def generate_images(
    prompts: List[Dict[str, Any]],
    *,
    out_dir: Any,
    provider: str = "gemini",
    model: Optional[str] = None,
    platform_home: Optional[Path] = None,
    transport: Any = None,
    write_bytes: Optional[Callable[[Path, bytes], None]] = None,
) -> List[ImageResult]:
    """image_prompts を provider で生成し ``out_dir/<shot_id>.png`` に保存する。

    鍵が無ければ ``MediaProviderNotConfigured`` を送出（1件も生成しない）。各カットの API 失敗は
    そのカットだけ ``ok=False`` で記録し、偽の画像は書かない。``transport``/``write_bytes`` は注入可能。
    """
    name = str(provider).strip().lower()
    gen = _PROVIDERS.get(name)
    if gen is None:
        raise ValueError(f"未知の画像プロバイダ: {provider}（対応: {', '.join(_PROVIDERS)}）")
    api_key = require_api_key(name, platform_home=platform_home)  # 無ければここで正直に停止
    mdl = model or _DEFAULT_MODEL[name]
    tr = transport or _UrllibTransport()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    writer = write_bytes or (lambda p, b: p.write_bytes(b))

    results: List[ImageResult] = []
    for prompt in prompts:
        shot_id = str(prompt.get("shot_id") or f"shot{len(results) + 1:02d}")
        try:
            data = gen(tr, api_key=api_key, model=mdl, prompt=prompt)
            path = out / f"{shot_id}.png"
            writer(path, data)
            results.append(ImageResult(shot_id=shot_id, ok=True, path=str(path)))
        except Exception as exc:  # noqa: BLE001 — カット単位で正直に失敗を記録（偽画像は書かない）
            results.append(
                ImageResult(shot_id=shot_id, ok=False, error=f"{type(exc).__name__}: {exc}")
            )
    return results
