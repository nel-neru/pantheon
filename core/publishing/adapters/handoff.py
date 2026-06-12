"""assisted ハンドオフ中のブラウザ生存管理（note / X 共有）。

assisted の契約は「投稿画面まで自動・最終送信は人間」。成功時はブラウザを
開いたまま人間に引き渡すため、launcher への参照を保持して GC で閉じないようにする。
人間が閉じ終わった残骸（駆動プロセス）は次のハンドオフ時に解放する。
"""

from __future__ import annotations

from typing import Any, List

# 意図的にプロセス全体・プラットフォーム横断の単一リスト（per-platform 分離はしない）。
# prune は「死んだ launcher を閉じる」だけなので、どの platform の残骸が混ざっても安全。
_HANDOFF_KEEPALIVE: List[Any] = []


def keep_alive(launcher: Any) -> None:
    """ハンドオフしたブラウザの launcher を生存リストに登録する。"""
    _HANDOFF_KEEPALIVE.append(launcher)


async def prune_handoff_keepalive() -> None:
    """人間が閉じ終わったハンドオフの残骸（駆動プロセス）を後始末する。

    launcher が ``is_alive()`` を持たない場合（テストのフェイク等）は生存扱いで残す。
    """
    still_open: List[Any] = []
    for launcher in _HANDOFF_KEEPALIVE:
        checker = getattr(launcher, "is_alive", None)
        if checker is None or checker():
            still_open.append(launcher)
            continue
        try:
            await launcher.close()  # ブラウザは閉鎖済み — 駆動プロセスだけ解放
        except Exception:  # noqa: BLE001
            pass
    _HANDOFF_KEEPALIVE[:] = still_open
