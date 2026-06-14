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
from core.publishing.auto_gate import auto_send_enabled
from core.publishing.base import (
    PUBLISH_MODE_ASSISTED,
    PUBLISH_MODE_AUTO,
    PublishContent,
    PublishResult,
    PublishTarget,
)
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
        "handed_off": result.handed_off,
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

    # PUB-AUTO 安全境界: auto ジョブでも「無人実送信フラグ ON」かつ「アダプタが実 auto 送信対応」
    # でない限り、assisted（下書き準備→handed_off＝人手が最終送信）へ降格する。これにより
    # デーモンは寝ている間に投稿を“送信の直前”まで自動準備しつつ、取り消せない外部送信は人手ゲートを保つ。
    if target.mode == PUBLISH_MODE_AUTO:
        try:
            adapter_supports_auto = bool(
                getattr(get_adapter(job.platform), "supports_auto_send", False)
            )
        except Exception:  # noqa: BLE001 — 未知プラットフォームは後段の通常処理でエラーになる
            adapter_supports_auto = False
        if not (auto_send_enabled(home) and adapter_supports_auto):
            target = PublishTarget(
                platform=job.platform,
                account=job.account,
                scheduled_at=job.scheduled_at,
                mode=PUBLISH_MODE_ASSISTED,
            )

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

    if result.ok and result.handed_off:
        # assisted のハンドオフ: 下書き流し込みまで成功し最終公開は人間待ち。
        # published とは区別し、未公開のものを成果（posts）には数えない。
        store.mark_status(job.job_id, status="handed_off", result_url=result.url)
        # 人間専用タスク（最終公開の確認）をキューへ積む（Human Member タスク管理）。
        from core.humans.human_tasks import enqueue_human_task

        enqueue_human_task(
            f"{job.platform} の公開を確認: {job.title or job.platform}",
            platform_home=home,
            kind="publish_confirm",
            org_name=job.org_name,
            ref=job.job_id,
            dedupe_key=f"publish_confirm:{job.job_id}",
            description="assisted で下書きを流し込みました。ブラウザで内容を確認して公開し、"
            "インボックスで『公開を確認』してください。",
        )
    elif result.ok:
        store.mark_status(job.job_id, status="published", result_url=result.url)
        _record_outcome(job, result, home)
    else:
        store.mark_status(job.job_id, status="failed", error=result.error)
    _log_publish(home, _result_dict(job, result))
    return _result_dict(job, result)


def confirm_handed_off(
    job_id: str,
    *,
    store: PublishJobStore,
    platform_home: Optional[Path] = None,
    result_url: str = "",
) -> Dict[str, Any]:
    """handed_off（人間が最終公開する待ち）のジョブを「公開済み」として確定する。

    人間がブラウザで実際に公開した後に呼ぶ確認ステップ。ここで初めて published に
    遷移し、成果（posts）を記録する — 未公開のものを収益指標に数えない、という
    handed_off 意味論の出口側。handed_off 以外の status では何もしない（ok=False）。
    """
    home = Path(platform_home) if platform_home else store.platform_home
    job = store.get_job(job_id)
    if job is None:
        return {"ok": False, "job_id": job_id, "error": "投稿ジョブが見つかりません"}
    if job.status != "handed_off":
        return {
            "ok": False,
            "job_id": job_id,
            "error": f"handed_off のジョブだけ確認できます（現在: {job.status}）",
            "status": job.status,
        }
    store.mark_status(job_id, status="published", result_url=result_url)
    result = PublishResult(
        ok=True, platform=job.platform, url=result_url, mode=job.mode, detail="公開を人間が確認"
    )
    # 成果はジョブ固有 source で冪等に記録する（並行/再送の confirm でも二重計上しない。
    # status ゲートに加えた防御の深層化）。
    from core.metrics.outcomes import OutcomeStore

    try:
        OutcomeStore(platform_home=home).record(
            job.org_name,
            "posts",
            1,
            unit="count",
            source=f"publish-confirm:{job.job_id}",
            note=result_url,
            dedupe_on_source=True,
        )
    except (OSError, ValueError, TypeError):
        pass  # 成果記録失敗で確認フローを壊さない（_record_outcome と同方針）
    _log_publish(home, {**_result_dict(job, result), "confirmed_by_human": True})
    return {"ok": True, "job_id": job_id, "status": "published", "url": result_url}


async def process_due_publish_jobs(
    store: PublishJobStore,
    *,
    platform_home: Optional[Path] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """予約時刻に達した auto モードの queued ジョブをまとめて実行する。

    assisted モードは「最終送信は人間」が契約のため、どの自動実行経路からも
    絶対に発火させない（承認＝唯一の出荷ゲート。content_scheduler 側の
    _process_due_publish_jobs と同じ不変条件）。

    PUB-AUTO: auto ジョブはここで実行されるが、無人実送信フラグ（``auto_gate.auto_send_enabled``）
    が OFF（既定）またはアダプタが実 auto 送信未対応の間は run_publish_job 内で assisted へ降格し、
    「下書き準備→handed_off（人手が最終送信）」になる。したがって外部への取り消せない送信は既定で発火しない。
    """
    results: List[Dict[str, Any]] = []
    executed = 0
    for job in store.due_jobs():
        if executed >= max(0, limit):
            break
        if job.mode != PUBLISH_MODE_AUTO:
            continue
        results.append(
            await run_publish_job(job, store=store, platform_home=platform_home, dry_run=False)
        )
        executed += 1
    return results
