"""Phase 3 残ストアアダプタ（読み取り専用ミラー）と repo-scoped 配線。"""

from __future__ import annotations

from core.vault import build_default_adapters, build_default_sync, build_vault_graph, get_vault_dir
from core.vault.format import parse_note


def _fm(path):
    return parse_note(path.read_text(encoding="utf-8")).frontmatter


def test_pattern_adapter_mirrors_code(tmp_path):
    from core.intelligence.pattern_library import PatternLibrary

    PatternLibrary(tmp_path).save_pattern(
        "Retry", "def retry():\n    ...", ["resilience"], "リトライ"
    )
    vault = get_vault_dir(tmp_path)
    build_default_sync(tmp_path).export()

    note = next((vault / "patterns").glob("*.md"))
    fm = _fm(note)
    assert fm["pantheon_type"] == "pattern"
    assert fm["pantheon_canonical"] == "json"
    assert "```python" in parse_note(note.read_text(encoding="utf-8")).body


def test_agent_pattern_adapter(tmp_path):
    from core.intelligence.agent_knowledge import AgentKnowledgeAccumulator

    AgentKnowledgeAccumulator(platform_home=tmp_path).record_success(
        "AgentX", "code_review", "analyze", "差分を要約してから指摘する", 9.0
    )
    vault = get_vault_dir(tmp_path)
    build_default_sync(tmp_path).export()

    note = next((vault / "agent-patterns").glob("*.md"))
    assert _fm(note)["pantheon_type"] == "agent_pattern"
    assert "[[org:AgentX]]" in parse_note(note.read_text(encoding="utf-8")).body


def test_failure_pattern_adapter(tmp_path):
    from core.knowledge.failure_patterns import FailurePatternRegistry

    FailurePatternRegistry(tmp_path).record_failure("import_error", "core/foo.py", "循環 import")
    vault = get_vault_dir(tmp_path)
    build_default_sync(tmp_path).export()

    note = next((vault / "failure-patterns").glob("*.md"))
    assert _fm(note)["pantheon_type"] == "failure_pattern"


def test_capability_adapter(tmp_path):
    from core.intelligence.capability_registry import CapabilityEntry, CapabilityRegistry

    reg = CapabilityRegistry(platform_home=tmp_path)
    reg.register(CapabilityEntry(id="skill:test", name="Test Skill", capability_type="skill"))
    vault = get_vault_dir(tmp_path)
    build_default_sync(tmp_path).export()

    note = next((vault / "capabilities").glob("*.md"))
    fm = _fm(note)
    assert fm["pantheon_type"] == "capability"
    assert fm["capability_type"] == "skill"


def test_handoff_adapter_links_orgs(tmp_path):
    from core.hierarchy.org_handoff import OrgHandoffStore

    OrgHandoffStore(tmp_path).create("SNS", "Note", "audience_signal", "需要シグナル")
    vault = get_vault_dir(tmp_path)
    build_default_sync(tmp_path).export()

    note = next((vault / "handoffs").glob("*.md"))
    body = parse_note(note.read_text(encoding="utf-8")).body
    assert "[[org:SNS]]" in body
    assert "[[org:Note]]" in body


def test_org_and_repo_scoped_adapters(tmp_path):
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager

    repo = tmp_path / "myrepo"
    repo.mkdir()
    psm = PlatformStateManager(tmp_path)
    org = create_default_organization("MyOrg", "私の目的", repo_path=str(repo))
    psm.save_organization(org)
    rsm = psm.get_org_state_manager(org)
    rsm.record_decision("d1", "原子的書き込みにする", "torn write を防ぐ", "human", ["arch"])

    vault = get_vault_dir(tmp_path)
    build_default_sync(tmp_path).export()

    # org ノート（id=org 名なのでリンク解決のハブになる）
    org_notes = list((vault / "orgs").glob("*.md"))
    assert org_notes
    assert _fm(org_notes[0])["pantheon_id"] == "MyOrg"
    # repos/<slug>/decisions にミラー
    decisions = list(vault.glob("repos/*/decisions/*.md"))
    assert decisions
    assert _fm(decisions[0])["pantheon_type"] == "decision"


def test_handoff_org_link_resolves_when_org_note_exists(tmp_path):
    from core.hierarchy.org_handoff import OrgHandoffStore
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(tmp_path)
    for name in ("SNS", "Note"):
        psm.save_organization(create_default_organization(name, f"{name} の目的"))
    OrgHandoffStore(tmp_path).create("SNS", "Note", "audience_signal", "需要")

    build_default_sync(tmp_path).export()
    graph = build_vault_graph(get_vault_dir(tmp_path))

    # org ノードが存在し、handoff からのエッジが解決する
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "org:SNS" in node_ids
    assert "org:Note" in node_ids
    assert len(graph["backlinks"].get("org:SNS", [])) >= 1


def test_build_default_adapters_includes_all_platform_mirrors(tmp_path):
    keys = {a.key for a in build_default_adapters(tmp_path)}
    assert {
        "knowledge",
        "playbook",
        "outcome",
        "pattern",
        "agent_pattern",
        "failure_pattern",
        "capability",
        "org",
        "handoff",
    } <= keys


def test_export_on_empty_home_is_clean(tmp_path):
    # 空のプラットフォームでも全アダプタが安全に iterate できる（構築/走査でクラッシュしない）。
    stats = build_default_sync(tmp_path).export()
    assert stats.written == 0
