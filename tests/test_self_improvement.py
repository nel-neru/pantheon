"""Tests for Sprint 5 self-improvement components."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from core.models.organization import ImprovementProposal
from core.quality.meta_improvement_analyzer import (
    ArchitectureAnalysis,
    MetaImprovementAnalyzer,
)
from core.quality.prompt_evolution_engine import PromptEvolutionEngine
from core.quality.self_improvement_cycle import SelfImprovementCycle
from core.state.migrator import StateMigrator
from core.state.sqlite_manager import SQLiteStateManager


def make_proposal(**overrides) -> ImprovementProposal:
    payload = {
        "review_id": uuid4(),
        "title": "Improve module",
        "description": "Refine responsibilities",
        "file_path": "core/example.py",
    }
    payload.update(overrides)
    return ImprovementProposal(**payload)


class TestSQLiteStateManager:
    def test_create_tables_on_init(self, tmp_path: Path):
        manager = SQLiteStateManager(tmp_path / "state.db")

        table_rows = manager._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row[0] for row in table_rows}

        assert {"proposals", "decisions", "insights"}.issubset(table_names)

    def test_save_and_get_proposals(self, tmp_path: Path):
        manager = SQLiteStateManager(tmp_path / "state.db")
        proposal = make_proposal(title="Split file")

        saved = manager.save_improvement_proposal(proposal)
        proposals = manager.get_pending_improvement_proposals()

        assert saved is True
        assert len(proposals) == 1
        assert proposals[0].title == "Split file"
        assert proposals[0].id == proposal.id

    def test_update_proposal_status(self, tmp_path: Path):
        manager = SQLiteStateManager(tmp_path / "state.db")
        proposal = make_proposal()
        manager.save_improvement_proposal(proposal)

        updated = manager.update_proposal_status(str(proposal.id)[:8], "done")
        stored_status = manager._conn.execute(
            "SELECT status FROM proposals WHERE id = ?",
            (str(proposal.id),),
        ).fetchone()[0]

        assert updated is True
        assert stored_status == "done"
        assert manager.get_pending_improvement_proposals() == []

    def test_record_and_get_decisions(self, tmp_path: Path):
        manager = SQLiteStateManager(tmp_path / "state.db")

        manager.record_decision("approve", "proposal-1", "Looks good")
        decisions = manager.get_recent_decisions()

        assert len(decisions) == 1
        assert decisions[0]["action"] == "approve"
        assert decisions[0]["proposal_id"] == "proposal-1"
        assert decisions[0]["reason"] == "Looks good"

    def test_pending_proposals_filter_by_status(self, tmp_path: Path):
        manager = SQLiteStateManager(tmp_path / "state.db")
        proposed = make_proposal(title="Keep proposed")
        pending = make_proposal(title="Keep pending", status="pending")
        running = make_proposal(title="Keep running", status="in_progress")
        done = make_proposal(title="Already done", status="done")
        manager.save_improvement_proposal(proposed)
        manager.save_improvement_proposal(pending)
        manager.save_improvement_proposal(running)
        manager.save_improvement_proposal(done)

        active = manager.get_pending_improvement_proposals()

        assert {proposal.title for proposal in active} == {"Keep proposed", "Keep pending", "Keep running"}


class TestStateMigrator:
    def test_migrate_empty_dir(self, tmp_path: Path):
        migrator = StateMigrator()

        result = migrator.migrate(tmp_path, tmp_path / "state.db")

        assert result.migrated_proposals == 0
        assert result.migrated_decisions == 0
        assert result.errors == []

    def test_migrate_with_proposals_json(self, tmp_path: Path):
        migrator = StateMigrator()
        proposal = make_proposal(title="Migrated proposal")
        decision = {
            "id": "decision-1",
            "action": "approve",
            "proposal_id": str(proposal.id),
            "reason": "ready",
            "timestamp": "2025-01-01T00:00:00",
        }
        (tmp_path / "proposals.json").write_text(
            json.dumps([proposal.model_dump(mode="json")], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (tmp_path / "decisions.json").write_text(
            json.dumps([decision], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = migrator.migrate(tmp_path, tmp_path / "state.db")
        manager = SQLiteStateManager(tmp_path / "state.db")

        assert result.migrated_proposals == 1
        assert result.migrated_decisions == 1
        assert result.errors == []
        assert manager.get_pending_improvement_proposals()[0].title == "Migrated proposal"
        assert manager.get_recent_decisions()[0]["id"] == "decision-1"


class TestMetaImprovementAnalyzer:
    def test_analyze_architecture_counts_files(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / "a.py").write_text(
            "class Example:\n    pass\n\n\ndef helper():\n    return 1\n",
            encoding="utf-8",
        )
        (repo_root / "b.py").write_text("def other():\n    return 2\n", encoding="utf-8")

        analysis = MetaImprovementAnalyzer().analyze_architecture(repo_root)

        assert analysis.total_files == 2
        assert analysis.total_classes == 1
        assert analysis.total_functions == 2
        assert analysis.total_lines >= 5

    def test_analyze_detects_large_files(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        large_file = repo_root / "large_module.py"
        large_file.write_text("\n".join(["value = 1"] * 501), encoding="utf-8")

        analysis = MetaImprovementAnalyzer().analyze_architecture(repo_root)

        assert "large_module.py" in analysis.large_files

    def test_generate_proposals_for_large_files(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        large_file = repo_root / "large_module.py"
        large_file.write_text("\n".join(["value = 1"] * 700), encoding="utf-8")
        analyzer = MetaImprovementAnalyzer()

        analysis = analyzer.analyze_architecture(repo_root)
        proposals = analyzer.generate_meta_proposals(analysis)

        assert proposals
        assert proposals[0].file_path == "large_module.py"
        assert proposals[0].priority == "medium"


class TestPromptEvolutionEngine:
    def test_create_experiment(self, tmp_path: Path):
        engine = PromptEvolutionEngine(platform_home=tmp_path)

        experiment = engine.create_experiment("agent", "prompt a", "prompt b")

        assert experiment.agent_name == "agent"
        assert [variant.variant_id for variant in experiment.variants] == ["A", "B"]
        assert (tmp_path / "prompt_experiments.json").exists()

    def test_record_result_updates_variant(self, tmp_path: Path):
        engine = PromptEvolutionEngine(platform_home=tmp_path)
        experiment = engine.create_experiment("agent", "prompt a", "prompt b")

        engine.record_result(experiment.experiment_id, "A", success=True, quality=8.0)
        reloaded = PromptEvolutionEngine(platform_home=tmp_path)
        variant = reloaded._experiments[experiment.experiment_id].variants[0]

        assert variant.use_count == 1
        assert variant.success_count == 1
        assert variant.avg_quality == 8.0

    def test_get_best_variant_requires_min_uses(self, tmp_path: Path):
        engine = PromptEvolutionEngine(platform_home=tmp_path)
        experiment = engine.create_experiment("agent", "prompt a", "prompt b")

        for _ in range(2):
            engine.record_result(experiment.experiment_id, "A", success=True, quality=9.0)
            engine.record_result(experiment.experiment_id, "B", success=False, quality=4.0)

        assert engine.get_best_variant(experiment.experiment_id) is None

    def test_evolve_prompt_adds_hint_for_low_quality(self, tmp_path: Path):
        engine = PromptEvolutionEngine(platform_home=tmp_path)

        evolved = engine.evolve_prompt("base prompt", [{"quality": 5.0}, {"quality": 4.0}])

        assert "より具体的で実装可能な提案を心がけてください。" in evolved

    def test_evolve_prompt_unchanged_for_high_quality(self, tmp_path: Path):
        engine = PromptEvolutionEngine(platform_home=tmp_path)

        evolved = engine.evolve_prompt("base prompt", [{"quality": 8.0}, {"quality": 9.0}])

        assert "現在の高品質を維持してください。" in evolved
        assert "より具体的で実装可能な提案を心がけてください。" not in evolved


class FakeMetaAnalyzer:
    def analyze_architecture(self, repo_root: Path) -> ArchitectureAnalysis:
        return ArchitectureAnalysis(
            repo_root=str(repo_root),
            total_files=1,
            total_lines=10,
            total_classes=0,
            total_functions=1,
            large_files=["core/big.py"],
            complex_modules=[],
            circular_import_hints=[],
            analyzed_at="2025-01-01T00:00:00",
        )

    def generate_meta_proposals(self, analysis: ArchitectureAnalysis) -> list[ImprovementProposal]:
        return [
            make_proposal(
                title="Split core/big.py",
                description="Separate responsibilities",
                file_path="core/big.py",
            )
        ]


class TestSelfImprovementCycle:
    def test_get_default_version(self, tmp_path: Path):
        cycle = SelfImprovementCycle(platform_home=tmp_path, meta_analyzer=FakeMetaAnalyzer())

        version = cycle.get_current_version()

        assert version.version == "1.0.0"
        assert version.improved_at == ""
        assert version.changes == []

    def test_run_cycle_increments_version(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        cycle = SelfImprovementCycle(platform_home=tmp_path, meta_analyzer=FakeMetaAnalyzer())

        record = cycle.run_meta_analysis_cycle(repo_root)
        version = cycle.get_current_version()

        assert record.version_before == "1.0.0"
        assert record.version_after == "1.0.1"
        assert version.version == "1.0.1"

    def test_run_cycle_saves_to_history(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        cycle = SelfImprovementCycle(platform_home=tmp_path, meta_analyzer=FakeMetaAnalyzer())

        record = cycle.run_meta_analysis_cycle(repo_root)
        lines = (tmp_path / "core_improvement_history.jsonl").read_text(encoding="utf-8").splitlines()

        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["cycle_id"] == record.cycle_id
        assert payload["meta_proposals_count"] == 1

    def test_get_improvement_history(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        cycle = SelfImprovementCycle(platform_home=tmp_path, meta_analyzer=FakeMetaAnalyzer())

        first = cycle.run_meta_analysis_cycle(repo_root)
        second = cycle.run_meta_analysis_cycle(repo_root)
        history = cycle.get_improvement_history(limit=1)

        assert first.cycle_id != second.cycle_id
        assert len(history) == 1
        assert history[0].cycle_id == second.cycle_id

    def test_increment_version_returns_original_for_non_numeric_patch(self, tmp_path: Path):
        cycle = SelfImprovementCycle(platform_home=tmp_path, meta_analyzer=FakeMetaAnalyzer())

        assert cycle._increment_version("1.0.beta") == "1.0.beta"
