"""作業ボード（タスクキュー）の drain を1か所に集約した共有ヘルパ。

PENDING タスクを :func:`core.runtime.work_launcher.dispatch_task` 経由で wmux の
work セッション（headless 時はサブプロセス）へ着火する処理は、これまで

  * ``web/server.py``（GUI 接続中の自動 drain・``/ws/updates`` へ配信）
  * ``commands/tasks.py``（``pantheon tasks drain`` の一発実行）
  * ``core/runtime/task_drain_scheduler.py``（headless daemon の定期 drain）

の3か所で個別に ``MultiOrgExecutor.process_pending`` を呼んでいた。dispatch の
振り分けは既に :func:`work_launcher.dispatch_task` に一本化されているが、その上の
「executor を組んで pending を捌く」層も重複していたため、ここに正準化する。

各呼び出し側は本ヘルパが返す per-task 結果（``session_id`` / ``driver`` /
``error``）を受け取り、提示は各々が行う（web=broadcast / CLI=print / daemon=log）。

注意: ``process_pending`` は dispatcher が返った時点（= wmux セッションを *起動* した
時点）でタスクを DONE にする。これは作業の *完了* ではなく *着火* を意味する。
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional


async def drain_pending_tasks(
    *,
    org_filter: Optional[str] = None,
    max_tasks: int = 10,
    queue: Any = None,
) -> list[dict[str, Any]]:
    """PENDING タスクを並列で着火し、per-task 結果のリストを返す。

    Args:
        org_filter: 指定すると、その Organization のタスクだけを着火する。
        max_tasks: 一度に着火する最大タスク数。
        queue: テスト用に :class:`TaskQueue` を注入する（省略時は既定キュー）。

    Returns:
        ``process_pending`` の結果リスト。着火成功は ``{"session_id", "driver",
        "dispatched": True}``、失敗は ``{"error": ...}``。着火対象が無ければ空リスト。
    """
    from core.orchestration.multi_org_executor import MultiOrgExecutor
    from core.orchestration.task_queue import TaskQueue
    from core.runtime import work_launcher

    queue = queue if queue is not None else TaskQueue()
    executor = MultiOrgExecutor(queue=queue)

    async def _dispatch(task: dict[str, Any]) -> dict[str, Any]:
        record = await asyncio.to_thread(work_launcher.dispatch_task, task)
        return {"session_id": record.id, "driver": record.driver, "dispatched": True}

    return await executor.process_pending(_dispatch, org_filter=org_filter, max_tasks=max_tasks)
