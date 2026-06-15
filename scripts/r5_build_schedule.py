"""R5 ヘルパ: 182日分の投稿スケジュールを plan_schedule で確定して JSON 出力する。

使い方: python scripts/r5_build_schedule.py <out.json> [start=YYYY-MM-DD] [count=182]
量産 Workflow にスケジュールを args として渡すための前段。実行後に削除してよい一時スクリプト。
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("r5_schedule.json")
    start_s = sys.argv[2] if len(sys.argv) > 2 else "2026-07-01"
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 182
    y, m, d = (int(x) for x in start_s.split("-"))

    from core.affiliate.generator import plan_schedule
    from core.affiliate.programs import AffiliateProgramStore

    # config からシードした一時ストアで商材を取得（実ユーザ状態を汚さない）。
    tmp_home = Path(tempfile.mkdtemp(prefix="r5sched-"))
    store = AffiliateProgramStore(platform_home=tmp_home)
    store.seed_from_config()
    programs = store.list_programs()

    plan = plan_schedule(programs, date(y, m, d), count)
    rows = []
    for e in plan:
        p = e["program"]
        rows.append(
            {
                "day_index": e["day_index"],
                "date": e["date"],
                "hook_type": e["hook_type"],
                "program_name": p.name if p else "",
                "program_id": p.program_id if p else "",
                "category": p.category if p else "general",
                "topics": list(p.topics) if p else [],
                "has_affiliate": bool(p.has_affiliate) if p else False,
            }
        )
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(rows)} entries -> {out}")


if __name__ == "__main__":
    main()
