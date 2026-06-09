"""PublishJob の実行。

承認済みジョブを適切なアダプタで投稿し、結果でジョブ status を更新、成功時は
``OutcomeEvent``（投稿実績）を記録し ``~/.pantheon/publish_log.jsonl`` に監査ログを残す。
実投稿は dry-run=False かつ接続済みセッションが前提（Phase 0 ではブラウザ未接続だと
正直に failed になる）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.publishing.adapters import get_adapter
from core.publishing.base import PublishContent, PublishResult, PublishTarget
from core.publishing.publish_jobs import PublishJob, PublishJobStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_content(job: PublishJob) -> PublishContent:
    return PublishContent(title=job.title, body=job.body)


def _build_target(job: PublishJob) -> PublishTarget:
    return PublishTarget(
        platform=job.platform,
        account=job.account,
        scheduled_at=job.scheduled_at,
        mode=job.mode,
    )


def _result_dict(job: PublishJob, result: PublishResult) -> Dict[str, Any]:
    return {
        "ok": result.ok,
        "job_id": job.job_id,
        "platform": result.platform,
        "url": result.url,
        "error": result.error,
        "dry_run": result.dry_run,
        "mode": result.mode,
        "detail": result.detail,
    }


def _log_publish(platform_home: Path, payload: Dict[str, Any]) -> None:
    """投稿監査を JSONL（1 行 1 イベント）で追記する。"""
    payload = {"ts": _now_iso(), **payload}
    path = Path(platform_home) / "publish_log.jsonl"
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 監査ログ失敗で投稿フローを壊さない


def _record_outcome(job: PublishJob, result: PublishResult, platform_home: Path) -> None:
    """投稿成功を成果イベントとして記録（収益ダッシュボードの相関キーになる）。"""
    from core.metrics.outcomes import OutcomeStore

    try:
        OutcomeStore(platform_home=platform_home).record(
            job.org_name,
            "posts",
            1,
            unit="count",
            source=f"publish:{job.platform}",
            note=result.url,
        )
    except (OSError, ValueError, TypeError):
        pass  # 成果記録失敗で投稿フローを壊さない


async def run_publish_job(
    job: PublishJob,
    *,
    store: PublishJobStore,
    platform_home: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """1 件の投稿ジョブを実行する。

    - ``dry_run=True``: プレビューのみ。ジョブ status は変更しない。
    - ``dry_run=False``: status を publishing→published/failed に更新し、成功時は成果記録＋監査ログ。
    """
    home = Path(platform_home) if platform_home else store.platform_home
    content = _build_content(job)
    target = _build_target(job)

    if dry_run:
        try:
            result = await get_adapter(job.platform).publish(content, target, dry_run=True)
        except (ValueError, NotImplementedError) as exc:
            result = PublishResult(
                ok=False, platform=job.platform, error=f"{type(exc).__name__}: {exc}", mode=job.mode
            )
        return _result_dict(job, result)

    store.mark_status(job.job_id, status="publishing", bump_attempts=True)
    try:
        result = await get_adapter(job.platform).publish(content, target, dry_run=False)
    except Exception as exc:  # noqa: BLE001 — アダプタの想定外失敗も failed に落とす
        result = PublishResult(
            ok=False, platform=job.platform, error=f"{type(exc).__name__}: {exc}", mode=job.mode
        )

    if result.ok:
        store.mark_status(job.job_id, status="published", result_url=result.url)
        _record_outcome(job, result, home)
    else:
        store.mark_status(job.job_id, status="failed", error=result.error)
    _log_publish(home, _result_dict(job, result))
    return _result_dict(job, result)


async def process_due_publish_jobs(
    store: PublishJobStore,
    *,
    platform_home: Optional[Path] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """予約時刻に達した queued ジョブをまとめて実行する（daemon から呼ぶ）。"""
    results: List[Dict[str, Any]] = []
    for job in store.due_jobs()[: max(0, limit)]:
        results.append(
            await run_publish_job(job, store=store, platform_home=platform_home, dry_run=False)
        )
    return results
