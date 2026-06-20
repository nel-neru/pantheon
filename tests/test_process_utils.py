"""core.runtime.process_utils — cross-platform pid liveness / termination.

回帰防止（Cycle 44）: Windows の ``os.kill(pid, 0)`` は終了済み（reaped）pid を
「稼働中」と誤報告する（false positive）。これが daemon の生存判定を狂わせ、
クラッシュしたデーモンを watchdog が復活させない不具合につながっていた。
``pid_alive`` は実 exit code を見て正しく False を返す。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from core.runtime.daemon_registry import is_process_running
from core.runtime.process_utils import no_window_kwargs, pid_alive, terminate_pid


def _spawn_sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])


def test_pid_alive_rejects_nonpositive():
    assert pid_alive(0) is False
    assert pid_alive(-1) is False


def test_pid_alive_true_for_live_child_false_after_reap():
    proc = _spawn_sleeper()
    try:
        assert pid_alive(proc.pid) is True
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    # teeth: 終了直後の pid。旧実装 os.kill(pid, 0) は Windows でここを True と誤判定した。
    assert pid_alive(proc.pid) is False


def test_is_process_running_uses_windows_safe_liveness():
    """daemon の生存判定が reaped pid を稼働中と誤報告しない（原バグの直接ガード）。"""
    proc = _spawn_sleeper()
    try:
        assert is_process_running(proc.pid) is True
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    assert is_process_running(proc.pid) is False


def test_terminate_pid_kills_live_child():
    proc = _spawn_sleeper()
    assert terminate_pid(proc.pid) is True
    proc.wait(timeout=10)
    assert pid_alive(proc.pid) is False


def test_terminate_pid_rejects_nonpositive():
    assert terminate_pid(0) is False
    assert terminate_pid(-5) is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only: Windows has no zombie processes")
def test_pid_alive_false_for_unreaped_zombie_child():
    """回帰防止: POSIX で kill 済みだが未 ``wait()`` の子は *ゾンビ* として残り、
    ``os.kill(pid, 0)`` は成功し続ける。だが ゾンビは終了済みであり稼働中ではない。
    旧実装はこれを True と誤報告し、クロスプロセス stop の e2e テストが Linux CI で
    タイムアウト失敗していた（Windows にゾンビは無く素通りしていた OS 差異バグ）。
    ここでは あえて刈り取らずに ``pid_alive`` が False を返すことを直接ピンする。"""
    proc = _spawn_sleeper()
    try:
        assert pid_alive(proc.pid) is True  # 稼働中
        proc.terminate()  # SIGTERM — 親(=このプロセス)が reap するまでゾンビ化
        # teeth: 刈り取らないまま、ゾンビを「死亡」と判定できること。
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and pid_alive(proc.pid):
            time.sleep(0.05)
        assert pid_alive(proc.pid) is False
    finally:
        proc.wait(timeout=10)  # ここで初めて reap（テスト後始末）
