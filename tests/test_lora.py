"""Flux スタイルLoRA 学習（core/media/lora_training）と canon→プロンプトへの LoRA 注入の検証。

学習画像の収集/zip はローカル（検証可）。fal 投入/状態はモック transport で検証（鍵/ネット不要）。
学習済み lora_url が canon にあると episode/thumbnail/character の画像プロンプトと fal payload に
loras が乗ることを固定する（独自スタイルを重みで固定＝偽の重みは作らない）。
"""

from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.illustration_story.asset_prompts import character_prompts, lora_payload, thumbnail_prompt
from core.illustration_story.episode_brief import build_episode_brief
from core.media.credentials import MediaProviderNotConfigured
from core.media.lora_training import (
    build_training_zip,
    check_lora_status,
    collect_training_images,
    submit_lora_training,
)


def _png(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n")


def test_collect_and_zip_training_images(tmp_path):
    _png(tmp_path / "canon" / "characters" / "keeper.png")
    _png(tmp_path / "episodes" / "ep-01" / "images" / "S01.png")
    _png(tmp_path / "episodes" / "ep-01" / "images" / "S02.png")
    imgs = collect_training_images(tmp_path)
    assert len(imgs) == 3
    zp = build_training_zip(imgs, tmp_path / "lora" / "t.zip")
    assert zp.exists()
    with zipfile.ZipFile(zp) as zf:
        assert set(zf.namelist()) == {"keeper.png", "S01.png", "S02.png"}


def test_submit_requires_key_and_url(tmp_path, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    with pytest.raises(MediaProviderNotConfigured):
        submit_lora_training("https://x/zip", platform_home=tmp_path)
    monkeypatch.setenv("FAL_KEY", "k")
    with pytest.raises(ValueError):
        submit_lora_training("", platform_home=tmp_path)  # URL 必須


class _FakeFal:
    def __init__(self, status="IN_PROGRESS", lora=None):
        self.status = status
        self.lora = lora
        self.posted = None

    def post_json(self, url, headers, payload):
        self.posted = {"url": url, "headers": headers, "payload": payload}
        return {
            "request_id": "req-1",
            "status_url": "https://q/req-1/status",
            "response_url": "https://q/req-1",
        }

    def get_json(self, url, headers):
        if url.endswith("/status"):
            return {"status": self.status}
        return {"diffusers_lora_file": {"url": self.lora}} if self.lora else {}


def test_submit_and_status_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "k")
    fal = _FakeFal(status="IN_PROGRESS")
    job = submit_lora_training(
        "https://x/zip", trigger_word="redthread", platform_home=tmp_path, transport=fal
    )
    assert job.request_id == "req-1"
    assert fal.posted["payload"]["images_data_url"] == "https://x/zip"
    # 進行中→ lora_url は None（捏造しない）
    assert check_lora_status(job, platform_home=tmp_path, transport=fal)["lora_url"] is None
    # 完了→ lora_url を取り出す
    done = _FakeFal(status="COMPLETED", lora="https://cdn/lora.safetensors")
    res = check_lora_status(job, platform_home=tmp_path, transport=done)
    assert res["status"] == "COMPLETED" and res["lora_url"] == "https://cdn/lora.safetensors"


def test_lora_payload_and_injection():
    canon = {"style_bible": {"style_suffix": "riso", "lora_url": "https://cdn/l.safetensors"}}
    assert lora_payload(canon) == [{"path": "https://cdn/l.safetensors", "scale": 1.0}]
    assert lora_payload({"style_bible": {}}) is None
    # thumbnail / character / episode のプロンプトに loras が乗る
    th = thumbnail_prompt({"metadata": {"thumbnail_brief": {}}}, canon)
    assert th["loras"][0]["path"].endswith("l.safetensors")
    canon["character_registry"] = {"characters": [{"id": "k", "base_seed": 1}]}
    assert character_prompts(canon)[0]["loras"]
    brief = build_episode_brief(canon, episode_no=1, logline="x", cast_ids=["k"])
    assert all(p.get("loras") for p in brief["image_prompts"])


def test_fal_provider_passes_loras(tmp_path, monkeypatch):
    """fal 画像生成は prompt の loras を payload に載せる（学習済みスタイルを適用）。"""
    monkeypatch.setenv("FAL_KEY", "k")
    from core.media.image_gen import generate_images

    class _T:
        def __init__(self):
            self.payload = None

        def post_json(self, url, headers, payload):
            self.payload = payload
            return {"images": [{"url": "https://img/1.png"}]}

        def get_bytes(self, url, headers=None):
            return b"\x89PNG"

    tr = _T()
    prompts = [
        {
            "shot_id": "S01",
            "positive": "p",
            "style_suffix": "riso",
            "aspect": "16:9",
            "loras": [{"path": "u", "scale": 1.0}],
        }
    ]
    res = generate_images(prompts, out_dir=tmp_path, provider="fal", transport=tr)
    assert res[0].ok
    assert tr.payload["loras"] == [{"path": "u", "scale": 1.0}]


def test_cli_lora_prepare_and_status(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from commands.story import cmd_story_lora
    from core.orchestration.company_plugins import install_company_plugin
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path)
    org_name = install_company_plugin("illustration_story_youtube", psm=psm)["org_name"]
    org = psm.load_organization_by_name(org_name)
    _png(Path(org.workspace_path) / "canon" / "characters" / "keeper.png")

    # prepare: zip を作る
    asyncio.run(
        cmd_story_lora(SimpleNamespace(org=org_name, lora_action="prepare"), get_psm=lambda: psm)
    )
    assert "zip 化" in capsys.readouterr().out
    assert (Path(org.workspace_path) / "lora" / "training_images.zip").exists()

    # status: 完了ジョブをモックして canon に lora_url 登録
    import json

    (Path(org.workspace_path) / "lora" / "job.json").write_text(
        json.dumps(
            {"request_id": "r", "status_url": "s", "response_url": "v", "trigger": "redthread"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "core.media.lora_training.check_lora_status",
        lambda job, **kw: {"status": "COMPLETED", "lora_url": "https://cdn/l.safetensors"},
    )
    asyncio.run(
        cmd_story_lora(SimpleNamespace(org=org_name, lora_action="status"), get_psm=lambda: psm)
    )
    out = capsys.readouterr().out
    assert "style_bible に登録" in out
    import yaml

    sb = yaml.safe_load(
        (Path(org.workspace_path) / "canon" / "style_bible.yaml").read_text(encoding="utf-8")
    )
    assert sb["lora_url"] == "https://cdn/l.safetensors"
