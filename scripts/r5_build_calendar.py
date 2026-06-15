"""R5 ヘルパ: 量産Workflowの出力(creative) + スケジュールから 182本の投稿カレンダーを組み立て、
content/shortvideo_affiliate/ に calendar.json / calendar.csv / posts.md を書き出す。

欠損日（生成失敗/レート制限）は決定的 fallback_post で必ず補完するため、常に全 N 本が揃う。

使い方:
  python scripts/r5_build_calendar.py <schedule.json> <workflow_output.json> [outdir]

workflow_output.json は Workflow タスクの .output（result.creative を持つ）か、
{"creative": {...}} 形式のどちらでも可。実行後に削除してよい一時スクリプト。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_creative(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    # タスク .output は {"result": {"creative": {...}}}、直接形は {"creative": {...}}
    if isinstance(payload, dict):
        if "creative" in payload and isinstance(payload["creative"], dict):
            return payload["creative"]
        res = payload.get("result")
        if isinstance(res, dict) and isinstance(res.get("creative"), dict):
            return res["creative"]
    return {}


def main() -> None:
    schedule_path = Path(sys.argv[1])
    creative_path = Path(sys.argv[2])
    outdir = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("content/shortvideo_affiliate")
    outdir.mkdir(parents=True, exist_ok=True)

    from core.affiliate.generator import fallback_post, post_from_llm_json
    from core.affiliate.programs import AffiliateProgram
    from core.affiliate.short_video import (
        ShortVideoPost,
        render_calendar_csv,
        render_calendar_markdown,
    )

    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    creative = _load_creative(creative_path)  # keys are strings (JSON object)

    posts: list[ShortVideoPost] = []
    produced = 0
    for entry in schedule:
        di = int(entry["day_index"])
        program = AffiliateProgram(
            name=entry.get("program_name", ""),
            category=entry.get("category", "general"),
            has_affiliate=bool(entry.get("has_affiliate", False)),
            topics=list(entry.get("topics", [])),
            program_id=entry.get("program_id", ""),
        )
        hook_type = entry.get("hook_type", "pain")
        date_str = entry.get("date", "")
        cre = creative.get(str(di)) or creative.get(di)
        if isinstance(cre, dict) and cre.get("title"):
            post = post_from_llm_json(cre, program, hook_type, date_str, di)
            produced += 1
        else:
            post = fallback_post(program, hook_type, date_str, di)
        posts.append(post)

    posts.sort(key=lambda p: p.day_index)

    (outdir / "calendar.json").write_text(
        json.dumps([p.to_dict() for p in posts], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (outdir / "calendar.csv").write_text(render_calendar_csv(posts), encoding="utf-8")
    (outdir / "posts.md").write_text(render_calendar_markdown(posts), encoding="utf-8")

    fallback_n = len(posts) - produced
    print(f"calendar built: {len(posts)} posts ({produced} LLM, {fallback_n} fallback) -> {outdir}")


if __name__ == "__main__":
    main()
