"""C-3: LLM ジャンル別テンプレ設計＋pantheon org create のテスト。"""

from __future__ import annotations

import asyncio

import yaml

from core.orchestration import org_template_designer as otd


def _run(coro):
    return asyncio.run(coro)


# ---- スキーマ検証 ----
def test_validate_normalizes_invalid_type_and_skills():
    raw = {
        "departments": [
            {
                "name": "Game Engine Div",
                "type": "totally_invalid_type",
                "mission": "m",
                "teams": [
                    {
                        "name": "Engine Team",
                        "mission": "m",
                        "required_skills": ["strategic_planning", "bogus_skill"],
                    }
                ],
            }
        ]
    }
    out = otd.validate_departments(raw)
    assert len(out) == 1
    assert out[0]["type"] == "org_evolution"  # 不正 type は寄せる
    skills = out[0]["teams"][0]["required_skills"]
    assert "bogus_skill" not in skills
    assert 2 <= len(skills) <= 3  # SpecialistAgent.skills 制約に合わせ補填


def test_validate_drops_empty_departments_and_teams():
    assert otd.validate_departments({"departments": []}) == []
    assert otd.validate_departments({"departments": [{"name": "X", "teams": []}]}) == []
    assert otd.validate_departments("not a dict") == []


def test_validate_caps_divisions_and_teams():
    raw = {
        "departments": [
            {
                "name": f"D{i}",
                "type": "org_evolution",
                "teams": [
                    {"name": f"T{j}", "required_skills": ["deep_research"]} for j in range(6)
                ],
            }
            for i in range(8)
        ]
    }
    out = otd.validate_departments(raw)
    assert len(out) <= otd.MAX_DIVISIONS
    assert all(len(d["teams"]) <= otd.MAX_TEAMS_PER_DIVISION for d in out)


def test_extract_json_from_fenced():
    text = 'ここに説明\n```json\n{"departments": []}\n```\n後書き'
    assert otd._extract_json(text) == {"departments": []}
    assert otd._extract_json("no json here") is None


def test_extract_json_tolerates_trailing_prose_with_braces():
    text = '```json\n{"departments": [{"name": "X"}]}\n```\n注: } を含む説明文'
    parsed = otd._extract_json(text)
    assert parsed == {"departments": [{"name": "X"}]}


def test_extract_json_no_redos_on_unclosed_fence():
    # 閉じフェンスが無く大量の空白が続く（max_tokens で切れたケース）でも即座に返る
    import time

    text = "```json\n" + " \n" * 20000  # 閉じない
    start = time.monotonic()
    result = otd._extract_json(text)
    assert (time.monotonic() - start) < 1.0  # ReDoS なら数十秒かかる
    assert result is None


# ---- 設計（オフライン＝決定論フォールバック）----
def test_design_departments_offline_fallback():
    # conftest が PANTHEON_NO_CLAUDE=1 → claude_available()=False → 決定論テンプレ
    departments = _run(otd.design_departments("game_dev"))
    assert len(departments) >= 1
    assert all(d["teams"] for d in departments)
    # 全スキルが有効
    valid = {
        s.value for s in __import__("core.models.organization", fromlist=["AgentSkill"]).AgentSkill
    }
    for d in departments:
        for t in d["teams"]:
            assert all(s in valid for s in t["required_skills"])


def test_design_uses_claude_when_available(monkeypatch):
    monkeypatch.setattr("core.runtime.claude_code.claude_available", lambda: True)

    class _Resp:
        content = (
            '{"departments": [{"name": "AI研究部", "type": "agent_architecture", '
            '"mission": "m", "teams": [{"name": "Research", "mission": "m", '
            '"required_skills": ["deep_research", "corporate_research"]}]}]}'
        )

    class _Provider:
        async def generate(self, **kwargs):
            assert kwargs.get("task_type") == "meta_improvement"
            return _Resp()

    monkeypatch.setattr("core.llm.get_llm_provider", lambda *a, **k: _Provider())
    departments = _run(otd.design_departments("ai"))
    assert departments[0]["name"] == "AI研究部"
    assert departments[0]["type"] == "agent_architecture"


def test_design_falls_back_when_claude_output_invalid(monkeypatch):
    monkeypatch.setattr("core.runtime.claude_code.claude_available", lambda: True)

    class _Resp:
        content = "garbage, no json"

    class _Provider:
        async def generate(self, **kwargs):
            return _Resp()

    monkeypatch.setattr("core.llm.get_llm_provider", lambda *a, **k: _Provider())
    departments = _run(otd.design_departments("video_edit"))
    assert len(departments) >= 1  # フォールバックが効く


# ---- 保存 ----
def test_save_generated_template(tmp_path, monkeypatch):
    monkeypatch.setattr(otd, "generated_dir", lambda: tmp_path)
    departments = otd._deterministic_template("ai")
    path = otd.save_generated_template("AI Consulting", departments)
    assert path.exists()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["meta"]["industry_genre"] == "AI Consulting"
    assert len(data["departments"]) == len(departments)
    # ファイル名は安全化される
    assert path.name == "ai_consulting.yaml"


def test_generated_dir_under_platform_home(tmp_path, monkeypatch):
    # 生成物はユーザー state として platform home 配下に書く（同梱領域でない）
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    d = otd.generated_dir()
    assert str(d).startswith(str(tmp_path))
    assert d.parts[-3:] == ("config", "departments", "generated")


def test_design_and_save_falls_back_to_temp_on_oserror(tmp_path, monkeypatch):
    monkeypatch.setattr(
        otd,
        "save_generated_template",
        lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")),
    )
    path, departments = _run(otd.design_and_save("ai"))
    assert path.exists()  # 一時ファイルに退避して必ず読めるパスを返す
    assert departments


# ---- org_factory がテンプレを読んで実 Organization を作れる ----
def test_generated_template_builds_organization(tmp_path, monkeypatch):
    from core.org_factory import create_organization_from_template

    monkeypatch.setattr(otd, "generated_dir", lambda: tmp_path)
    path, departments = _run(otd.design_and_save("game_dev"))
    org = create_organization_from_template("GameStudio", "p", path, industry_genre="game_dev")
    assert org.industry_genre == "game_dev"
    assert len(org.divisions) >= 1
    agents = org.get_all_agents()
    assert agents
    for a in agents:
        assert 2 <= len(a.skills) <= 3  # SpecialistAgent 制約
