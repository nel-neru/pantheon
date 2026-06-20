from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from core.goals.goal_library import GoalLibrary
from core.goals.goal_scheduler import GoalScheduler
from core.intelligence.adaptive_cache import AdaptiveCacheManager
from core.intelligence.capability_history import CapabilityHistoryTracker
from core.intelligence.dependency_graph import DependencyGraphBuilder
from core.intelligence.pattern_library import PatternLibrary
from core.intelligence.repo_bibliography import RepoBibliography
from core.intelligence.self_extension_e2e import SelfExtensionE2ECycle
from core.intelligence.semantic_search import SemanticCodeSearch
from core.intelligence.understanding_score import UnderstandingScoreTracker
from core.models.organization import ImprovementProposal
from core.orchestration.task_router import LoadBalancer
from core.security.auditor import SecurityAuditor
from core.state.sqlite_manager import SQLiteStateManager
from core.ui.doc_generator import DocGenerator
from core.ui.error_messages import ErrorMessageHelper
from core.ui.health_report_generator import HealthReportGenerator
from core.ui.i18n import I18n
from core.ui.interactive_approver import InteractiveApprover
from core.ui.setup_wizard import SetupWizard


def test_interactive_approver_format_list():
    approver = InteractiveApprover()
    text = approver.list_pending_proposals(
        [{"title": "Fix", "priority": "high", "category": "security"}]
    )
    assert "1. Fix" in text


def test_interactive_approver_parse_approve():
    assert InteractiveApprover().parse_action("approve", "p1") == ("approve", "p1")


def test_interactive_approver_parse_reject():
    assert InteractiveApprover().parse_action("d", "p1") == ("reject", "p1")


def test_health_report_generator_weekly():
    report = HealthReportGenerator().generate_weekly_report(
        "Org",
        {
            "health_score": 60,
            "proposals_count": 12,
            "accepted_count": 3,
            "knowledge_count": 1,
        },
    )
    assert report.org_name == "Org"
    assert report.issues


def test_setup_wizard_get_steps():
    steps = SetupWizard().get_steps()
    assert len(steps) == 4
    assert steps[0].title == "Claude CLI 認証"


def test_error_message_helper_format():
    text = ErrorMessageHelper().format_error("MISSING_API_KEY")
    assert "claude" in text.lower()


def test_error_message_wrap_exception():
    text = ErrorMessageHelper().wrap_exception(KeyError("missing"))
    assert "組織が見つかりません" in text


def test_doc_generator_extract_docstrings(tmp_path):
    target = tmp_path / "sample.py"
    target.write_text(
        '"""module doc"""\n\nclass A:\n    """class doc"""\n    def run(self):\n        """method doc"""\n        return 1\n\ndef func():\n    """func doc"""\n    return 2\n',
        encoding="utf-8",
    )
    docs = DocGenerator().extract_docstrings(target)
    assert docs["module"] == "module doc"
    assert docs["classes"]["A"]["methods"]["run"] == "method doc"


def test_i18n_japanese_default(monkeypatch):
    monkeypatch.delenv("PANTHEON_LANG", raising=False)
    assert I18n().t("status_healthy") == "健康"


def test_i18n_english_via_env(monkeypatch):
    monkeypatch.setenv("PANTHEON_LANG", "en")
    assert I18n().t("status_healthy") == "Healthy"


def test_save_100_proposals_performance(tmp_path):
    manager = SQLiteStateManager(tmp_path / "state.db")
    for i in range(100):
        manager.save_improvement_proposal(
            ImprovementProposal(
                review_id=uuid4(), title=f"P{i}", description="d", file_path=f"core/{i}.py"
            )
        )
    assert len(manager.get_pending_improvement_proposals(limit=100)) == 100


def test_concurrent_writes_sqlite(tmp_path):
    manager = SQLiteStateManager(tmp_path / "state.db")

    async def run_writes():
        loop = asyncio.get_running_loop()
        await asyncio.gather(
            *[
                loop.run_in_executor(
                    None,
                    manager.save_improvement_proposal,
                    ImprovementProposal(
                        review_id=uuid4(), title=f"P{i}", description="d", file_path=f"core/{i}.py"
                    ),
                )
                for i in range(20)
            ]
        )

    asyncio.run(run_writes())
    assert len(manager.get_pending_improvement_proposals(limit=30)) == 20


def test_security_auditor_detects_eval(tmp_path):
    target = tmp_path / "bad.py"
    target.write_text("eval(user_input)\n", encoding="utf-8")
    assert SecurityAuditor().audit_file(target)


def test_security_auditor_clean_file(tmp_path):
    target = tmp_path / "good.py"
    target.write_text("value = 1\n", encoding="utf-8")
    assert SecurityAuditor().audit_file(target) == []


def test_semantic_search_returns_results():
    index = {
        "files": {
            "core/example.py": {
                "classes": ["ExampleService"],
                "functions": ["calculate_score"],
                "docstring_summary": "Calculate health score for repos",
            }
        }
    }
    results = SemanticCodeSearch(index=index).search("health score")
    assert results
    assert results[0].file_path == "core/example.py"


def test_dependency_graph_build(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text("from . import b\n", encoding="utf-8")
    (pkg / "b.py").write_text("import json\n", encoding="utf-8")
    graph = DependencyGraphBuilder().build(tmp_path)
    assert "pkg/a.py" in graph


def test_adaptive_cache_hit_rate():
    cache = AdaptiveCacheManager(max_size=2)
    cache.set("a", 1)
    assert cache.get("a") == 1
    assert cache.get("missing") is None
    assert cache.get_hit_rate() == 0.5


def test_understanding_score_record(tmp_path):
    tracker = UnderstandingScoreTracker(platform_home=tmp_path)
    tracker.record_exploration("repo", 20, 3, 4)
    assert tracker.get_score("repo") > 0


def test_repo_bibliography_generates(tmp_path):
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "mod.py").write_text('"""module docs"""\n', encoding="utf-8")
    content = RepoBibliography().generate(tmp_path)
    assert "module docs" in content


def test_capability_history_record(tmp_path):
    tracker = CapabilityHistoryTracker(platform_home=tmp_path)
    record = tracker.record_addition("Search", "tool", "needed", "gap")
    assert tracker.get_history()[0].capability_id == record.capability_id


def test_pattern_library_save_and_search(tmp_path):
    library = PatternLibrary(platform_home=tmp_path)
    saved = library.save_pattern("cache", "value = 1", ["cache", "python"], "lfu cache")
    results = library.search_patterns("cache")
    assert results[0].pattern_id == saved.pattern_id


def test_self_extension_e2e():
    gap = SimpleNamespace()
    gap_analyzer = SimpleNamespace(analyze=lambda: [gap])
    design_agent = SimpleNamespace(design=lambda g: SimpleNamespace(file_path="x.py"))
    code_writer = SimpleNamespace(write_code=lambda spec: SimpleNamespace(file_path="x.py"))
    result = SelfExtensionE2ECycle(gap_analyzer, design_agent, code_writer, tester=None).run_cycle()
    assert result.gap_detected is True
    assert result.tests_passed is False


def test_goal_library_save_and_find(tmp_path):
    library = GoalLibrary(platform_home=tmp_path)
    template = library.save_achieved_goal("security", "Improve auth", 5, 12.5)
    assert library.find_similar("security")[0].template_id == template.template_id


def test_goal_scheduler_submit_and_status():
    scheduler = GoalScheduler(max_parallel=2)
    execution = scheduler.submit_goal("security", "Improve auth")
    assert execution.status == "pending"
    assert "pending=1" in scheduler.get_status_summary()
    # started_at は submit 時点では未設定（実行開始時刻のセマンティクス）。
    assert execution.started_at == ""
    # start_execution で running 遷移＋実行開始時刻が刻まれる。
    assert scheduler.start_execution(execution.execution_id) is True
    assert execution.status == "running" and execution.started_at != ""
    # complete_execution で終了時刻が刻まれる。
    assert scheduler.complete_execution(execution.execution_id) is True
    assert execution.status == "completed" and execution.completed_at != ""
    assert scheduler.start_execution("exec:nope") is False


def test_load_balancer_tracks_load():
    balancer = LoadBalancer(max_tasks_per_agent=2)
    balancer.record_task_start("a1")
    assert balancer.get_load("a1") == 1
    assert balancer.is_overloaded("a1") is False


def test_load_balancer_least_loaded():
    balancer = LoadBalancer()
    balancer.record_task_start("a1")
    assert balancer.get_least_loaded(["a1", "a2"]) == "a2"


def test_health_report_cli_format():
    report = HealthReportGenerator().generate_weekly_report(
        "Org",
        {"health_score": 90, "proposals_count": 1, "accepted_count": 1, "knowledge_count": 10},
    )
    assert "週次健康診断レポート" in HealthReportGenerator().format_cli(report)


def test_setup_wizard_format_cli(monkeypatch, tmp_path):
    monkeypatch.setenv("PANTHEON_HOME", str(tmp_path))
    text = SetupWizard().format_wizard_cli()
    assert "セットアップウィザード" in text


def test_doc_generator_generate_markdown(tmp_path):
    target = tmp_path / "sample.py"
    target.write_text('"""module doc"""\n', encoding="utf-8")
    markdown = DocGenerator().generate_markdown(target)
    assert markdown.startswith("# sample.py")


def test_doc_generator_skips_syntax_error_files(tmp_path, caplog):
    (tmp_path / "good.py").write_text('"""good"""\n', encoding="utf-8")
    (tmp_path / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    output = tmp_path / "docs.md"

    caplog.set_level("WARNING")
    count = DocGenerator().generate_for_directory(tmp_path, output)
    content = output.read_text(encoding="utf-8")

    assert count == 1
    assert "# good.py" in content
    assert "# bad.py" not in content
    assert "Skipping documentation for" in caplog.text


def test_semantic_search_tokenize():
    tokens = SemanticCodeSearch()._tokenize("health_score compute")
    assert "health" in tokens and "score" in tokens


def test_dependency_graph_detect_cycle():
    cycles = DependencyGraphBuilder().detect_circular_imports({"a.py": ["b.py"], "b.py": ["a.py"]})
    assert cycles


def test_adaptive_cache_stats_most_accessed():
    cache = AdaptiveCacheManager(max_size=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("b")
    assert cache.get_stats()["most_accessed_key"] == "b"


def test_capability_history_timeline_empty(tmp_path):
    assert "ありません" in CapabilityHistoryTracker(platform_home=tmp_path).format_timeline()


def test_pattern_library_record_use(tmp_path):
    library = PatternLibrary(platform_home=tmp_path)
    pattern = library.save_pattern("cache", "x=1", ["cache"])
    library.record_use(pattern.pattern_id)
    assert library.get_pattern(pattern.pattern_id).use_count == 1


def test_goal_scheduler_can_start_new():
    scheduler = GoalScheduler(max_parallel=1)
    scheduler.submit_goal("a", "b")
    assert scheduler.can_start_new() is False


def test_load_balancer_overloaded():
    balancer = LoadBalancer(max_tasks_per_agent=1)
    balancer.record_task_start("a1")
    assert balancer.is_overloaded("a1") is True
