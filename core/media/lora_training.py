"""Flux スタイル LoRA 学習 — 署名スタイルを「参照プロンプト」から「学習済み重み」へ昇格する（fal.ai）。

正直な分担:
- **学習画像の収集・zip 化はローカル**（canon/characters と各話 images から良カットを集める＝検証可）。
- **zip の公開 URL 化は利用者の作業**（fal ストレージへの upload は API ドリフトが激しく検証できない
  ため、ここでは扱わない。利用者が zip をどこかに公開し URL を渡す＝人間専用入力）。
- **fal への学習投入・状態確認は鍵ゲート（FAL_KEY）**。fal の queue API に準拠して request_id を取り、
  完了時に LoRA 重み URL を取り出す。鍵が無ければ送出、失敗は正直に返す（偽の重みは作らない）。
- 完了した ``lora_url``/``trigger`` は style_bible に保存し、以後の画像生成（fal provider）が参照する。

注: fal の model slug / レスポンス形は各社ドキュメント準拠の既定値。実アカウントでの最終確認は
利用者の鍵が要る（model は引数で上書き可）。
"""

from __future__ import annotations

import json
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.media.credentials import require_api_key

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_DEFAULT_MODEL = "fal-ai/flux-lora-fast-training"
_QUEUE_BASE = "https://queue.fal.run"


@dataclass
class LoraJob:
    request_id: str
    status_url: str = ""
    response_url: str = ""


def collect_training_images(workspace: Any, *, limit: int = 60) -> List[Path]:
    """workspace のカノン設定画＋各話生成画像から学習用の画像を集める（最大 limit 枚）。"""
    ws = Path(workspace)
    found: List[Path] = []
    for sub in (ws / "canon" / "characters", *sorted((ws / "episodes").glob("ep-*/images"))):
        if sub.exists() and sub.is_dir():
            found.extend(sorted(p for p in sub.iterdir() if p.suffix.lower() in _IMG_EXTS))
    # 重複を避けつつ順序維持
    seen: set = set()
    unique = [p for p in found if not (str(p) in seen or seen.add(str(p)))]
    return unique[:limit]


def build_training_zip(images: List[Path], out_zip: Any) -> Path:
    """学習画像を 1 つの zip にまとめる（fal に渡す素材。ローカルで完結・検証可）。"""
    out = Path(out_zip)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for img in images:
            zf.write(img, arcname=img.name)
    return out


class _UrllibFalTransport:
    def post_json(
        self, url: str, headers: Dict[str, str], payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json", **headers}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))

    def get_json(self, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))


def submit_lora_training(
    images_url: str,
    *,
    trigger_word: str = "redthread",
    model: str = _DEFAULT_MODEL,
    platform_home: Optional[Path] = None,
    transport: Any = None,
) -> LoraJob:
    """学習ジョブを fal の queue へ投入し request_id 等を返す（鍵ゲート）。

    ``images_url`` は学習画像 zip の公開 URL（利用者が用意＝人間作業）。鍵が無ければ送出。
    """
    if not images_url:
        raise ValueError("学習画像 zip の公開 URL（images_url）が必要です（利用者が用意します）")
    key = require_api_key("fal", platform_home=platform_home)
    tr = transport or _UrllibFalTransport()
    body = {"images_data_url": images_url, "trigger_word": trigger_word}
    resp = tr.post_json(f"{_QUEUE_BASE}/{model}", {"Authorization": f"Key {key}"}, body)
    rid = str(resp.get("request_id") or "")
    if not rid:
        raise ValueError(f"fal が request_id を返しませんでした: {resp}")
    return LoraJob(
        request_id=rid,
        status_url=str(resp.get("status_url") or ""),
        response_url=str(resp.get("response_url") or ""),
    )


def check_lora_status(
    job: LoraJob,
    *,
    platform_home: Optional[Path] = None,
    transport: Any = None,
) -> Dict[str, Any]:
    """学習ジョブの状態を確認し、完了していれば LoRA 重み URL を取り出す（鍵ゲート）。

    Returns: ``{"status": str, "lora_url": Optional[str]}``。完了以外は lora_url=None。
    """
    key = require_api_key("fal", platform_home=platform_home)
    tr = transport or _UrllibFalTransport()
    auth = {"Authorization": f"Key {key}"}
    st = tr.get_json(job.status_url, auth) if job.status_url else {}
    status = str(st.get("status") or "UNKNOWN").upper()
    if status != "COMPLETED" or not job.response_url:
        return {"status": status, "lora_url": None}
    res = tr.get_json(job.response_url, auth)
    lora = (res.get("diffusers_lora_file") or {}).get("url") or res.get("lora_url")
    return {"status": status, "lora_url": str(lora) if lora else None}
