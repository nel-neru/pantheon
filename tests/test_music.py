"""BGM 自動選定（core/media/music）の検証。完全ローカル・決定論（鍵不要）。"""

from __future__ import annotations

from pathlib import Path

from core.media.music import music_library_dir, select_music


def _track(lib: Path, mood: str, name: str):
    d = lib / mood
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(b"ID3fake-audio")


def test_no_library_returns_none(tmp_path):
    assert select_music("tender", platform_home=tmp_path) is None


def test_selects_by_mood_keyword(tmp_path):
    lib = music_library_dir(tmp_path)
    _track(lib, "tender", "a.mp3")
    _track(lib, "tense", "b.mp3")
    picked = select_music("minimal, tender, one quiet turn", platform_home=tmp_path)
    assert picked is not None and Path(picked).parent.name == "tender"


def test_rotation_by_episode(tmp_path):
    lib = music_library_dir(tmp_path)
    _track(lib, "tender", "a.mp3")
    _track(lib, "tender", "b.mp3")
    first = select_music("tender", platform_home=tmp_path, episode_no=0)
    second = select_music("tender", platform_home=tmp_path, episode_no=1)
    assert {Path(first).name, Path(second).name} == {"a.mp3", "b.mp3"}  # 話ごとに循環
    # 決定論: 同じ episode_no は同じ曲
    assert select_music("tender", platform_home=tmp_path, episode_no=2) == first


def test_fallback_when_mood_folder_absent(tmp_path):
    lib = music_library_dir(tmp_path)
    _track(lib, "whimsical", "w.mp3")  # tense は無い
    picked = select_music("dark tense suspense", platform_home=tmp_path)
    assert picked is not None and Path(picked).name == "w.mp3"  # 他フォルダへフォールバック


def test_ignores_non_audio(tmp_path):
    lib = music_library_dir(tmp_path)
    (lib / "tender").mkdir(parents=True)
    (lib / "tender" / "notes.txt").write_text("x", encoding="utf-8")
    assert select_music("tender", platform_home=tmp_path) is None  # 音源拡張子のみ対象
