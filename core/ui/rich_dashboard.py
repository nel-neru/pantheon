"""
RichDashboard — リッチCLI TUIダッシュボード (I-03)

richライブラリを使ったTUI実装。
組織ツリー・メトリクス・最新提案をリッチ表示する。
"""

from __future__ import annotations

from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.tree import Tree

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    Console = None
    Table = None
    Tree = None
    RICH_AVAILABLE = False


class RichDashboard:
    def __init__(self, use_rich: bool = True):
        self.use_rich = bool(use_rich and RICH_AVAILABLE)

    def render_org_summary(self, org_data: dict) -> str:
        name = org_data.get("name", "Unknown")
        health = float(org_data.get("health_score", 0.0))
        proposals = int(org_data.get("proposal_count", 0))
        agents = int(org_data.get("agent_count", 0))
        stage = org_data.get("lifecycle_stage", "unknown")

        if self.use_rich:
            color = self._health_color(health)
            return (
                f"[bold]{name}[/bold] | health [{color}]{health:.1f}[/{color}] | "
                f"proposals {proposals} | agents {agents} | stage {stage}"
            )

        return (
            f"{name} | health {health:.1f} | proposals {proposals} | "
            f"agents {agents} | stage {stage}"
        )

    def render_proposals_table(self, proposals: list[dict]) -> str:
        rows = [
            {
                "id": str(proposal.get("id", ""))[:8],
                "priority": str(proposal.get("priority", "medium")),
                "category": str(proposal.get("category", "general")),
                "title": self._truncate(str(proposal.get("title", "")), 50),
            }
            for proposal in proposals
        ]

        if self.use_rich:
            table = Table(title="Latest Proposals")
            table.add_column("ID", no_wrap=True)
            table.add_column("Priority")
            table.add_column("Category")
            table.add_column("Title")
            for row in rows:
                table.add_row(row["id"], row["priority"], row["category"], row["title"])
            return self._render_rich(table)

        header = "ID       | Priority | Category | Title"
        divider = "-" * len(header)
        body = [
            f"{row['id']:<8} | {row['priority']:<8} | {row['category']:<8} | {row['title']}"
            for row in rows
        ] or ["(no proposals)"]
        return "\n".join([header, divider, *body])

    def render_org_tree(self, orgs: list[dict]) -> str:
        if self.use_rich:
            tree = Tree("Organizations")
            for org in orgs:
                name = org.get("name", "Unknown")
                health = float(org.get("health_score", 0.0))
                color = self._health_color(health)
                tree.add(f"{name} [[{color}]{health:.1f}[/{color}]]")
            return self._render_rich(tree)

        lines = ["Organizations"]
        for org in orgs:
            lines.append(
                f"├─ {org.get('name', 'Unknown')} (health: {float(org.get('health_score', 0.0)):.1f})"
            )
        return "\n".join(lines)

    def print_dashboard(self, orgs: list[dict], proposals: list[dict]) -> None:
        sections = ["=== Pantheon Dashboard ==="]
        sections.extend(self.render_org_summary(org) for org in orgs)
        sections.append("")
        sections.append(self.render_proposals_table(proposals))
        sections.append("")
        sections.append(self.render_org_tree(orgs))
        print("\n".join(sections))

    def _render_rich(self, renderable) -> str:
        console = Console(record=True, width=120)
        console.print(renderable)
        return console.export_text().rstrip()

    def _health_color(self, health: float) -> str:
        if health >= 70:
            return "green"
        if health >= 40:
            return "yellow"
        return "red"

    def _truncate(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."
