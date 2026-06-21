"""動画組立 — エピソードブリーフの timeline_spec ＋ 生成画像から mp4 を作る（FFmpeg・ローカル完結）。

外部 API も鍵も不要（FFmpeg はローカルバイナリ）。各カットの静止画に Ken Burns（緩やかなズーム）を
かけ、timeline_spec の尺で連結し、任意で音声を載せる。これが「動画生成も自動化」のローカル本命。

正直性: FFmpeg が無ければ ``VideoResult(ok=False, ...)``、必要な画像が欠けていればそれを明示して
失敗する（偽の動画は作らない）。``runner`` は注入可能（テストはコマンド構築を検証／実 FFmpeg は
スモークテストで実行）。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# aspect → 出力解像度（YouTube 標準）。
_RESOLUTION = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}


@dataclass
class VideoResult:
    ok: bool
    path: Optional[str] = None
    error: str = ""
    command: List[str] = field(default_factory=list)


def _resolution(aspect: str) -> Tuple[int, int]:
    return _RESOLUTION.get(str(aspect), (1920, 1080))


def _default_runner(cmd: List[str]) -> Tuple[int, str]:
    import subprocess

    from core.runtime.process_utils import no_window_kwargs

    proc = subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",  # Windows の cp932 で stderr が壊れないよう明示（既知ハザード）
        errors="replace",
        **no_window_kwargs(),
    )
    return proc.returncode, (proc.stderr or "")


def build_ffmpeg_command(
    timeline_spec: Dict[str, Any],
    image_paths: Dict[str, str],
    *,
    out_path: Any,
    audio_path: Optional[str] = None,
    ffmpeg_bin: str = "ffmpeg",
) -> Tuple[List[str], List[str]]:
    """FFmpeg コマンドと「欠けている shot_id」一覧を返す（純粋・テスト可能）。

    各 shot を ``-loop 1 -t <dur>`` で入力し、scale/crop で解像度を埋め、zoompan で緩やかな
    Ken Burns をかけて concat する。音声があれば最後に load して ``-shortest`` で尺を合わせる。
    """
    fps = int(timeline_spec.get("fps") or 30)
    aspect = str(timeline_spec.get("aspect") or "16:9")
    width, height = _resolution(aspect)
    shots = list(timeline_spec.get("shots") or [])

    inputs: List[str] = []
    filters: List[str] = []
    missing: List[str] = []
    n = 0
    for shot in shots:
        shot_id = str(shot.get("shot_id") or "")
        img = image_paths.get(shot_id)
        if not img:
            missing.append(shot_id)
            continue
        dur = float(shot.get("duration_s") or 4)
        frames = max(1, int(round(dur * fps)))
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur}", "-i", str(img)]
        # 緩やかなズームイン Ken Burns（zoom-out は環境差で乱れやすいので全カット安定なズームインに統一）。
        filters.append(
            f"[{n}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"zoompan=z='min(zoom+0.0012,1.18)':d={frames}:s={width}x{height}:fps={fps},"
            f"setsar=1[v{n}]"
        )
        n += 1

    if n == 0:
        return [], missing  # 有効カットなし

    concat_in = "".join(f"[v{i}]" for i in range(n))
    filter_complex = ";".join(filters) + f";{concat_in}concat=n={n}:v=1:a=0[outv]"

    cmd = [ffmpeg_bin, "-y", *inputs]
    if audio_path:
        cmd += ["-i", str(audio_path)]
    cmd += ["-filter_complex", filter_complex, "-map", "[outv]"]
    if audio_path:
        cmd += ["-map", f"{n}:a", "-shortest"]
    cmd += ["-r", str(fps), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)]
    return cmd, missing


def assemble_video(
    timeline_spec: Dict[str, Any],
    image_paths: Dict[str, str],
    *,
    out_path: Any,
    audio_path: Optional[str] = None,
    runner: Optional[Callable[[List[str]], Tuple[int, str]]] = None,
    ffmpeg_bin: Optional[str] = None,
) -> VideoResult:
    """timeline_spec + 画像から mp4 を組み立てる。FFmpeg 不在/画像欠落/失敗は正直に返す。"""
    binary = ffmpeg_bin or shutil.which("ffmpeg")
    if not binary:
        return VideoResult(
            ok=False,
            error="FFmpeg が見つかりません。https://ffmpeg.org からインストールし PATH を通してください",
        )

    cmd, missing = build_ffmpeg_command(
        timeline_spec, image_paths, out_path=out_path, audio_path=audio_path, ffmpeg_bin=binary
    )
    if not cmd:
        return VideoResult(
            ok=False,
            error=f"有効な画像が1枚もありません（欠けている shot: {', '.join(missing) or '全て'}）",
        )
    if missing:
        return VideoResult(
            ok=False,
            command=cmd,
            error=f"画像が欠けている shot があります: {', '.join(missing)}（先に画像生成を完了してください）",
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    run = runner or _default_runner
    code, stderr = run(cmd)
    if code != 0:
        tail = "\n".join(stderr.strip().splitlines()[-8:])
        return VideoResult(ok=False, command=cmd, error=f"FFmpeg 失敗 (exit {code}):\n{tail}")
    return VideoResult(ok=True, path=str(out), command=cmd)
