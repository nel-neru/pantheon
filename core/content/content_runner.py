"""content_runner — ContentJob を1回実行し、ワークスペース repo へ投稿（content_asset 提案）を生成する。

外部公開はしない。生成物は ``category=content_asset`` の ImprovementProposal として受け手 org の
``<repo>/.pantheon/improvements`` に保存され、PolicyEngine により **human_required**（人間承認待ち）になる。
claude CLI が使えれば LLM で本文生成、無ければ決定論テンプレ（人間が編集する下書き骨子）にフォールバックする。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from core.content.content_jobs import ContentJob

_KIND_LABEL = {
    "content_brief": "SNS 投稿",
    "audience_signal": "需要シグナルメモ",
    "monetization_lead": "収益化リード（PR 表記必須）",
    "generic": "コンテンツ下書き",
}

_KIND_SYSTEM = {
    "content_brief": (
        "あなたは SNS グロース担当の編集者です。指定テーマで、続きが読みたくなる日本語の"
        "X(Twitter) 投稿ドラフトを Markdown で作成してください。誇張・虚偽の数値は書かない。"
    ),
    "audience_signal": (
        "あなたは需要リサーチャーです。指定テーマについて、検証すべき読者の課題仮説と、"
        "それを確かめる軽い投稿アイデアを日本語 Markdown で簡潔にまとめてください。"
    ),
    "monetization_lead": (
        "あなたは収益化担当です。指定テーマで note 等の有料導線ドラフトを日本語 Markdown で作成し、"
        "必ず末尾に『#PR』等のステマ防止のための関係性明示（PR 表記）を入れてください。"
    ),
    "generic": "指定テーマについて、編集前提の下書きを日本語 Markdown で作成してください。",
}


def _deterministic_draft(job: ContentJob, label: str, stamp: str) -> str:
    theme = job.theme or "(テーマ未設定)"
    pr_note = "\n\n#PR" if job.kind == "monetization_lead" else ""
    return (
        f"# {label} 下書き\n\n"
        f"- テーマ: {theme}\n"
        f"- 生成: {stamp}（claude CLI 不在のためテンプレート骨子）\n\n"
        "## 本文（編集してください）\n\n"
        f"{theme} について、読者の課題と解決の糸口を一段落で書き出す。\n\n"
        "- ポイント1\n- ポイント2\n- ポイント3\n\n"
        "（このドラフトはレビュー後に承認・適用してください）"
        f"{pr_note}\n"
    )


async def _generate_body(job: ContentJob, label: str, stamp: str):
    """(markdown 本文, llm_used, rate_info) を返す。

    rate_info は :class:`RateLimitInfo`（``limited=True`` ならレート制限検知）または None。
    claude 不在/通常失敗時は決定論テンプレ。
    """
    from core.runtime.claude_code import claude_available
    from core.runtime.rate_limit import detect_rate_limit, detect_rate_limit_strict

    if not claude_available():
        return _deterministic_draft(job, label, stamp), False, None
    try:
        from core.llm import LLMMessage, get_llm_provider

        provider = get_llm_provider()
        system = _KIND_SYSTEM.get(job.kind, _KIND_SYSTEM["generic"])
        user = f"テーマ: {job.theme or '(未設定)'}\n対象組織: {job.org_name}\nMarkdown で出力。"
        response = await provider.generate(
            messages=[
                LLMMessage(role="system", content=system),
                LLMMessage(role="user", content=user),
            ],
            temperature=0.6,
            max_tokens=2000,
        )
        body = (getattr(response, "content", "") or "").strip()
        # claude CLI はレート制限を「正常終了(returncode 0)の結果テキスト」として返すことがある。
        # 例外時だけでなく成功本文も検査するが、正常なドラフトが "rate limit"/"429" に
        # 言及しただけで誤検知しないよう、アンカー付き定型句（strict）に限定する。
        info = detect_rate_limit_strict(body)
        if info.limited:
            return "", False, info
        if body:
            return body, True, None
        return _deterministic_draft(job, label, stamp), False, None
    except Exception as exc:  # noqa: BLE001
        # レート制限なら検知して上位へ伝える（テンプレで誤魔化さない＝ループを止める判断材料）。
        info = detect_rate_limit(str(exc))
        if info.limited:
            return "", False, info
        return _deterministic_draft(job, label, stamp), False, None


async def run_content_job(job: ContentJob, psm: Any) -> Dict[str, Any]:
    """ContentJob を1回実行し、生成した content_asset 提案を受け手 org の repo に保存する。

    戻り値: {"ok": bool, "status": str, "detail": str, "proposal_id": str|None, "file_path": str|None}
    外部公開はせず、提案は human_required（承認待ち）として保存される。
    """
    from core.orchestration.asset_application import build_content_asset_proposal

    org = psm.load_organization_by_name(job.org_name)
    if org is None:
        return {
            "ok": False,
            "status": "org_not_found",
            "detail": f"組織 '{job.org_name}' が見つかりません",
        }
    if not getattr(org, "target_repo_path", None):
        return {
            "ok": False,
            "status": "no_workspace",
            "detail": f"組織 '{job.org_name}' に repo（ワークスペース）が未設定です",
        }

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    file_stamp = now.strftime("%Y%m%d-%H%M%S")
    label = _KIND_LABEL.get(job.kind, _KIND_LABEL["generic"])

    body, llm_used, rate_info = await _generate_body(job, label, stamp)
    if rate_info is not None and rate_info.limited:
        # レート制限検知時は提案を作らず、上位（スケジューラ）にループ停止を促す。
        return {
            "ok": False,
            "status": "rate_limited",
            "detail": rate_info.message or "Claude のレート制限を検知しました",
            "retry_at": rate_info.reset_at.isoformat() if rate_info.reset_at else None,
            "scope": rate_info.scope,
        }
    file_path = f"content/{job.kind}-{job.job_id[:8]}-{file_stamp}.md"
    title = f"[{label}] {job.theme or job.org_name}（{file_stamp}）"
    description = (
        f"ContentJob {job.job_id[:8]} が生成した投稿ドラフト。"
        f"{'LLM 生成' if llm_used else 'テンプレ下書き'}。レビューのうえ承認・適用してください。"
    )

    proposal = build_content_asset_proposal(
        title=title,
        description=description,
        file_path=file_path,
        content=body,
        mode="create",
        target_repo=str(org.target_repo_path),
        priority="medium",
    )
    sm = psm.get_org_state_manager(org)
    sm.save_improvement_proposal(proposal)

    return {
        "ok": True,
        "status": "generated",
        "detail": f"{'LLM' if llm_used else 'template'} draft -> {file_path}（承認待ち）",
        "proposal_id": str(proposal.id),
        "file_path": file_path,
        "llm_used": llm_used,
    }
