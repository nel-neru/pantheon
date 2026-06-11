"""
TemplatePromoter — 高パフォーマンスOrg構造のテンプレート昇格 (H-07)
"""

from __future__ import annotations

from pathlib import Path

import yaml

from core.platform.state import get_platform_home


class TemplatePromoter:
    def __init__(self, platform_home=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.templates_dir = self.platform_home / "org_templates"
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def should_promote(self, org_name: str, autonomy_score: float, threshold: float = 70.0) -> bool:
        return autonomy_score >= threshold

    def promote_org_template(self, org_name: str, org_spec: dict, score: float) -> Path:
        payload = dict(org_spec)
        payload.setdefault("org_name", org_name)
        payload["promoted_score"] = score
        path = self.templates_dir / f"{org_name}_promoted.yaml"
        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        return path

    def list_promoted_templates(self) -> list[str]:
        return sorted(path.stem for path in self.templates_dir.glob("*_promoted.yaml"))
