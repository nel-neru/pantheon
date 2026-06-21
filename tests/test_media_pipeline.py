"""メディア生産（画像生成・動画組立）の検証。

- 認証情報: 環境変数/ファイルから解決、無ければ MediaProviderNotConfigured（偽画像を作らない）。
- 画像生成: モック transport で request 構築と base64 デコード→保存を検証（実ネットワーク不要）。
- 動画組立: コマンド構築（純粋）＋ 実 FFmpeg スモーク（あれば実行・無ければ skip）。
- CLI story render: install → brief → 画像配置 → 実 FFmpeg で mp4 生成（end-to-end）。
"""

from __future__ import annotations

import asyncio
import base64
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.media.credentials import MediaProviderNotConfigured, load_api_key, require_api_key
from core.media.image_gen import generate_images
from core.media.video_assembly import _RESOLUTION, assemble_video, build_ffmpeg_command

_FFMPEG = shutil.which("ffmpeg")

# 既知の 1x1 PNG（base64）。画像生成のモックレスポンスに使う。
_PNG_1x1_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


# --------------------------------------------------------------------------- #
# 認証情報                                                                      #
# --------------------------------------------------------------------------- #


def test_load_api_key_from_env_and_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    assert load_api_key("gemini", platform_home=tmp_path) == "env-key"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert load_api_key("gemini", platform_home=tmp_path) is None  # 未設定
    cred = tmp_path / "media_credentials"
    cred.mkdir()
    (cred / "gemini.key").write_text("file-key\n", encoding="utf-8")
    assert load_api_key("gemini", platform_home=tmp_path) == "file-key"


def test_require_api_key_raises_when_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(MediaProviderNotConfigured):
        require_api_key("gemini", platform_home=tmp_path)


# --------------------------------------------------------------------------- #
# 画像生成（モック transport）                                                  #
# --------------------------------------------------------------------------- #


class _FakeTransport:
    def __init__(self, *, image_b64=None, raise_on_post=False):
        self.image_b64 = image_b64
        self.raise_on_post = raise_on_post
        self.calls = []

    def post_json(self, url, headers, payload):
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        if self.raise_on_post:
            raise RuntimeError("boom-api")
        return {"candidates": [{"content": {"parts": [{"inlineData": {"data": self.image_b64}}]}}]}

    def get_bytes(self, url, headers=None):  # fal 用（このテストでは未使用）
        return b""


def _prompts():
    return [
        {
            "shot_id": "S01",
            "positive": "a quiet town",
            "style_suffix": "risograph",
            "negative_prompt": "3d",
            "aspect": "16:9",
        },
        {
            "shot_id": "S02",
            "positive": "the twist",
            "style_suffix": "risograph",
            "negative_prompt": "text",
            "aspect": "16:9",
        },
    ]


def test_generate_images_writes_real_bytes_via_mock(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    tr = _FakeTransport(image_b64=_PNG_1x1_B64)
    results = generate_images(
        _prompts(), out_dir=tmp_path / "imgs", provider="gemini", transport=tr
    )
    assert [r.ok for r in results] == [True, True]
    for r in results:
        assert Path(r.path).exists() and Path(r.path).read_bytes() == base64.b64decode(_PNG_1x1_B64)
    # プロンプトに style_suffix と negative が乗っている（カノン固定がAPIへ届く）
    sent = tr.calls[0]["payload"]["contents"][0]["parts"][0]["text"]
    assert "risograph" in sent and "Avoid: 3d" in sent


def test_generate_images_honest_failure_no_fake_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    out = tmp_path / "imgs"
    results = generate_images(
        _prompts(), out_dir=out, provider="gemini", transport=_FakeTransport(raise_on_post=True)
    )
    assert all(not r.ok and "boom-api" in r.error for r in results)
    # 失敗時は偽の画像ファイルを書かない
    assert not list(out.glob("*.png"))


def test_generate_images_requires_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(MediaProviderNotConfigured):
        generate_images(_prompts(), out_dir=tmp_path, provider="gemini", platform_home=tmp_path)


# --------------------------------------------------------------------------- #
# 動画組立（純粋なコマンド構築）                                                #
# --------------------------------------------------------------------------- #


def _timeline():
    return {
        "fps": 24,
        "aspect": "16:9",
        "shots": [
            {"shot_id": "S01", "duration_s": 1},
            {"shot_id": "S02", "duration_s": 1},
        ],
    }


def test_build_ffmpeg_command_resolution_and_inputs(tmp_path):
    imgs = {"S01": str(tmp_path / "a.png"), "S02": str(tmp_path / "b.png")}
    cmd, missing = build_ffmpeg_command(_timeline(), imgs, out_path=tmp_path / "o.mp4")
    assert missing == []
    joined = " ".join(cmd)
    assert "1920:1080" in joined  # 16:9 解像度
    assert cmd.count("-loop") == 2  # 2 カット
    assert "concat=n=2" in joined


def test_build_ffmpeg_command_reports_missing_images(tmp_path):
    cmd, missing = build_ffmpeg_command(
        _timeline(), {"S01": str(tmp_path / "a.png")}, out_path=tmp_path / "o.mp4"
    )
    assert missing == ["S02"]


def test_assemble_video_missing_images_is_honest(tmp_path):
    res = assemble_video(_timeline(), {}, out_path=tmp_path / "o.mp4", ffmpeg_bin="ffmpeg")
    assert not res.ok and "画像" in res.error  # 偽の動画は作らない


# --------------------------------------------------------------------------- #
# 動画組立（実 FFmpeg スモーク）                                                #
# --------------------------------------------------------------------------- #


def _make_png(path: Path, color: str, size: str = "320x180"):
    subprocess.run(
        [
            _FFMPEG,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={size}",
            "-frames:v",
            "1",
            str(path),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.mark.skipif(_FFMPEG is None, reason="ffmpeg が PATH に無い")
def test_assemble_video_real_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setitem(_RESOLUTION, "16:9", (96, 54))  # テストは極小解像度で高速化
    _make_png(tmp_path / "S01.png", "red")
    _make_png(tmp_path / "S02.png", "blue")
    imgs = {"S01": str(tmp_path / "S01.png"), "S02": str(tmp_path / "S02.png")}
    out = tmp_path / "out.mp4"
    res = assemble_video(_timeline(), imgs, out_path=out)
    assert res.ok, res.error
    assert out.exists() and out.stat().st_size > 0


@pytest.mark.skipif(_FFMPEG is None, reason="ffmpeg が PATH に無い")
def test_cli_story_render_end_to_end(tmp_path, monkeypatch, capsys):
    """install → brief → 画像配置 → render（--no-images）で実 mp4 を生成する。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.setitem(_RESOLUTION, "16:9", (96, 54))  # テストは極小解像度で高速化
    from commands.story import cmd_story_brief, cmd_story_render
    from core.orchestration.company_plugins import install_company_plugin
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path)
    result = install_company_plugin("illustration_story_youtube", psm=psm)
    org_name = result["org_name"]
    asyncio.run(
        cmd_story_brief(
            SimpleNamespace(org=org_name, ep=1, format="long_form"), get_psm=lambda: psm
        )
    )

    org = psm.load_organization_by_name(org_name)
    work = Path(org.workspace_path) / "episodes" / "ep-01"
    images = work / "images"
    images.mkdir(parents=True, exist_ok=True)
    # ブリーフの timeline の各 shot に実画像を配置（手動生成相当）
    import yaml

    brief = yaml.safe_load(
        (Path(org.workspace_path) / "episodes" / "ep-01.yaml").read_text(encoding="utf-8")
    )
    for shot in brief["timeline_spec"]["shots"]:
        _make_png(images / f"{shot['shot_id']}.png", "green")

    asyncio.run(
        cmd_story_render(
            SimpleNamespace(org=org_name, ep=1, provider="gemini", no_images=True, audio=None),
            get_psm=lambda: psm,
        )
    )
    out = capsys.readouterr().out
    assert "動画を生成しました" in out
    assert (work / "ep-01.mp4").exists() and (work / "ep-01.mp4").stat().st_size > 0
