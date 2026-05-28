"""
InteractiveApprover — インタラクティブ承認UI (I-04)
CLIで提案を一覧表示しキーボードで承認/却下する
"""

from __future__ import annotations


class InteractiveApprover:
    """CLI proposals approval helper."""

    def __init__(self, state_manager=None):
        self.state_manager = state_manager

    def list_pending_proposals(self, proposals: list[dict]) -> str:
        if not proposals:
            return "未承認の提案はありません。"

        lines = ["未承認の提案:"]
        for index, proposal in enumerate(proposals, start=1):
            lines.append(
                f"{index}. {proposal.get('title', '(untitled)')} "
                f"[priority={proposal.get('priority', 'unknown')}, "
                f"category={proposal.get('category', 'general')}]"
            )
        return "\n".join(lines)

    def format_proposal_detail(self, proposal: dict) -> str:
        return "\n".join(
            [
                f"Title: {proposal.get('title', '(untitled)')}",
                f"Description: {proposal.get('description', '')}",
                f"File: {proposal.get('file_path', '')}",
                f"Priority: {proposal.get('priority', 'unknown')}",
            ]
        )

    def parse_action(self, user_input: str, proposal_id: str) -> tuple[str, str]:
        normalized = user_input.strip().lower()
        mapping = {
            "a": "approve",
            "approve": "approve",
            "d": "reject",
            "reject": "reject",
            "s": "skip",
            "skip": "skip",
        }
        action = mapping.get(normalized)
        if not action:
            return ("unknown", "")
        return (action, proposal_id)
