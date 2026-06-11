"""C-1: Organization のジャンル/ペルソナ/デザイン属性と persona⇔content 統合のテスト。"""

from __future__ import annotations

import asyncio

from core.models.organization import Organization
from core.org_factory import create_default_organization


def _run(coro):
    return asyncio.run(coro)


# ---- モデル後方互換 ----
def test_new_fields_have_defaults():
    org = Organization(name="X", purpose="p")
    assert org.industry_genre == "general"
    assert org.persona_id == ""
    assert org.design_style == "minimal"


def test_old_json_loads_without_new_fields():
    # 旧フォーマット（新フィールド無し）の JSON を後方互換でロードできる
    old = {"name": "Legacy", "purpose": "p"}
    org = Organization.model_validate(old)
    assert org.industry_genre == "general"
    assert org.design_style == "minimal"


def test_new_fields_roundtrip():
    org = Organization(
        name="Game Studio",
        purpose="p",
        industry_genre="game_dev",
        persona_id="sns_growth_hacker",
        design_style="pixel",
    )
    loaded = Organization.model_validate_json(org.model_dump_json())
    assert loaded.industry_genre == "game_dev"
    assert loaded.persona_id == "sns_growth_hacker"
    assert loaded.design_style == "pixel"


# ---- persona ローダー（同梱パス解決）----
def test_persona_loader_resolves_bundled():
    from core.intelligence.persona_loader import PersonaLoader

    loader = PersonaLoader()
    personas = loader.list_personas()
    assert "sns_growth_hacker" in personas
    assert "luxury_brand_voice" in personas
    addon = loader.get_system_prompt_addon("sns_growth_hacker")
    assert "フック" in addon or "SNS" in addon


# ---- persona/design → content_runner プロンプト注入 ----
def test_persona_design_addon_injection():
    from core.content.content_runner import _persona_design_addon

    org = Organization(
        name="X", purpose="p", persona_id="luxury_brand_voice", design_style="minimal"
    )
    addon = _persona_design_addon(org)
    assert "ペルソナ" in addon
    assert "luxury_brand_voice" in addon


def test_persona_design_addon_empty_for_neutral():
    from core.content.content_runner import _persona_design_addon

    org = Organization(name="X", purpose="p")  # persona 無し・minimal
    assert _persona_design_addon(org) == ""


def test_generate_body_injects_persona_into_system(monkeypatch):
    from core.content import content_runner
    from core.content.content_jobs import ContentJob

    monkeypatch.setattr("core.runtime.claude_code.claude_available", lambda: True)
    captured = {}

    class _Resp:
        content = "本文"

    class _Provider:
        async def generate(self, **kwargs):
            captured["system"] = kwargs["messages"][0].content
            return _Resp()

    monkeypatch.setattr("core.llm.get_llm_provider", lambda *a, **k: _Provider())

    org = Organization(name="X", purpose="p", persona_id="sns_growth_hacker")
    job = ContentJob(org_name="X", kind="content_brief", theme="AI 副業")
    body, used, rate = _run(content_runner._generate_body(job, "L", "S", org=org))
    assert body == "本文"
    assert "ペルソナ" in captured["system"]


# ---- org_factory がテンプレ meta から属性を読む ----
def test_create_default_org_has_defaults():
    org = create_default_organization("Org", "p")
    assert org.industry_genre == "general"
    assert org.design_style == "minimal"


def test_template_meta_supplies_attributes(tmp_path):
    from core.org_factory import create_organization_from_template

    tpl = tmp_path / "tpl.yaml"
    tpl.write_text(
        "meta:\n"
        "  industry_genre: video_edit\n"
        "  persona_id: luxury_brand_voice\n"
        "  design_style: luxury\n"
        "departments: []\n",
        encoding="utf-8",
    )
    org = create_organization_from_template("Vid", "p", template_path=tpl)
    assert org.industry_genre == "video_edit"
    assert org.persona_id == "luxury_brand_voice"
    assert org.design_style == "luxury"


def test_explicit_args_override_template_meta(tmp_path):
    from core.org_factory import create_organization_from_template

    tpl = tmp_path / "tpl.yaml"
    tpl.write_text("meta:\n  industry_genre: video_edit\ndepartments: []\n", encoding="utf-8")
    org = create_organization_from_template(
        "Vid", "p", template_path=tpl, industry_genre="game_dev"
    )
    assert org.industry_genre == "game_dev"  # 引数が meta を上書き
