from __future__ import annotations

import argparse
from typing import Any


async def cmd_doctor(args: argparse.Namespace) -> None:
    from core.state.system_doctor import SystemDoctor

    doctor = SystemDoctor()
    issues = doctor.diagnose()

    if not issues:
        print("[OK] 問題は見つかりませんでした。")
        return

    print("Pantheon Doctor")
    for issue in issues:
        fixable = "auto-fixable" if issue.auto_fixable else "manual"
        print(f"- [{issue.severity}] {issue.issue_id} ({fixable})")
        print(f"  {issue.description}")

    if getattr(args, "fix", False):
        fixed = doctor.fix_issues(issues)
        print(f"\n[OK] 自動修復: {fixed} 件")
    elif any(issue.auto_fixable for issue in issues):
        print("\nヒント: pantheon doctor --fix で自動修復できます。")


def register(subparsers: Any) -> None:
    doctor_parser = subparsers.add_parser("doctor", help="プラットフォーム健康診断を実行")
    doctor_parser.add_argument("--fix", action="store_true", help="自動修復可能な問題を修復する")
    doctor_parser.set_defaults(handler_name="cmd_doctor")
