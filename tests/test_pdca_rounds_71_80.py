from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from commands import build_parser
from commands.doctor import cmd_doctor
from commands.orchestration import cmd_agent_list
from commands.org import cmd_org_show, cmd_proposal_apply, cmd_proposal_reject, cmd_proposal_show
from commands.platform import (
    cmd_platform_backup,
    cmd_platform_config,
    cmd_platform_config_set,
    cmd_platform_logs,
    cmd_platform_restore,
)
from commands.version import get_version_string
from core.ui.doc_generator import DocGenerator
from core.ui.error_messages import ErrorMessageHelper
from core.ui.health_report_generator import HealthReportGenerator
from core.ui.i18n import I18n
from core.ui.interactive_approver import InteractiveApprover
from core.ui.rich_dashboard import RichDashboard
from core.ui.setup_wizard import SetupWizard
from github_integration.pr_creator import create_improvement_pr
from github_integration.repo_reader import get_file_tree, get_important_files


class FakeProposalStateManager:
    def __init__(self, proposals: list[dict[str, object]]):
        self.proposals = proposals
        self.status_updates: list[tuple[str, str]] = []

    def get_pending_improvement_proposals(self, limit: int = 100):
        return self.proposals[:limit]

    def update_proposal_status(self, proposal_id: str, status: str) -> None:
        self.status_updates.append((proposal_id, status))
        for proposal in self.proposals:
            if str(proposal["id"]).startswith(proposal_id):
                proposal["status"] = status

    def update_proposal_fields(self, proposal_id: str, **updates) -> bool:
        for proposal in self.proposals:
            if str(proposal["id"]).startswith(proposal_id):
                proposal.update(updates)
        return True


class FakePSM:
    def __init__(self, platform_home: Path, org, state_manager: FakeProposalStateManager):
        self.platform_home = platform_home
        self._org = org
        self._state_manager = state_manager
        self._config: dict[str, object] = {}

    def load_organization_by_name(self, name: str):
        return self._org if name == self._org.name else None

    def load_organizations(self):
        return [self._org]

    def get_org_state_manager(self, _org):
        return self._state_manager

    def load_platform_config(self):
        return dict(self._config)

    def save_platform_config(self, config):
        self._config = dict(config)
        self.platform_home.mkdir(parents=True, exist_ok=True)
        (self.platform_home / "platform.json").write_text(
            json.dumps(self._config), encoding="utf-8"
        )


@pytest.mark.parametrize(
    "argv, handler",
    [
        (["version"], "cmd_version"),
        (["doctor"], "cmd_doctor"),
        (["org", "show", "--name", "Demo"], "cmd_org_show"),
        (["proposal", "show", "abc", "--org-name", "Demo"], "cmd_proposal_show"),
        (["platform", "config"], "cmd_platform_config"),
        (["platform", "config", "set", "foo", "bar"], "cmd_platform_config_set"),
        (["platform", "logs"], "cmd_platform_logs"),
        (["platform", "backup"], "cmd_platform_backup"),
        (["platform", "restore"], "cmd_platform_restore"),
        (["agent", "list"], "cmd_agent_list"),
    ],
)
def test_new_cli_handlers_are_registered(argv, handler):
    parser = build_parser()
    args = parser.parse_args(argv)
    assert args.handler_name == handler


def test_version_flag_prints_version(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--version"])
    assert get_version_string() in capsys.readouterr().out


def test_org_show_proposal_show_and_reject(capsys, tmp_path):
    proposal = {
        "id": "12345678-1234-1234-1234-123456789abc",
        "title": "Improve cache",
        "description": "Cache more aggressively",
        "priority": "high",
        "category": "performance",
        "file_path": "src/app.py",
        "expected_impact": "Faster loads",
        "implementation_difficulty": "medium",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    agent = SimpleNamespace(
        name="Planner",
        skills=[SimpleNamespace(value="strategic_planning"), SimpleNamespace(value="org_design")],
    )
    team = SimpleNamespace(
        name="Core", division_type=SimpleNamespace(value="org_evolution"), agents=[agent]
    )
    division = SimpleNamespace(
        name="Evolution", type=SimpleNamespace(value="org_evolution"), teams=[team]
    )
    org = SimpleNamespace(
        name="Demo",
        id="org-1",
        purpose="Improve repo",
        target_repo_path=str(tmp_path / "repo"),
        created_at=datetime.now(timezone.utc),
        last_active=datetime.now(timezone.utc),
        autonomy_score=88.0,
        improvement_velocity=77.0,
        status=SimpleNamespace(value="active"),
        divisions=[division],
        get_all_agents=lambda: [agent],
    )
    state_manager = FakeProposalStateManager([proposal])
    psm = FakePSM(tmp_path, org, state_manager)

    asyncio.run(cmd_org_show(SimpleNamespace(name="Demo"), get_psm=lambda: psm))
    assert "Organization 詳細" in capsys.readouterr().out

    asyncio.run(
        cmd_proposal_show(
            SimpleNamespace(org_name="Demo", proposal_id="12345678"), get_psm=lambda: psm
        )
    )
    assert "提案詳細" in capsys.readouterr().out

    asyncio.run(
        cmd_proposal_reject(
            SimpleNamespace(org_name="Demo", proposal_id="12345678", yes=True),
            confirm_action=lambda *a, **k: True,
            get_psm=lambda: psm,
        )
    )
    assert state_manager.status_updates[-1][1] == "rejected"
    assert "却下しました" in capsys.readouterr().out


def test_proposal_apply_updates_status_and_reports_branch(capsys, tmp_path):
    proposal = {
        "id": "12345678-1234-1234-1234-123456789abc",
        "title": "Improve cache",
        "description": "Cache more aggressively",
        "priority": "high",
        "category": "performance",
        "file_path": "src/app.py",
        "expected_impact": "Faster loads",
        "implementation_difficulty": "medium",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    org = SimpleNamespace(
        name="Demo",
        target_repo_path=str(tmp_path / "repo"),
    )
    state_manager = FakeProposalStateManager([proposal])
    psm = FakePSM(tmp_path, org, state_manager)

    class FakeExecutor:
        async def run(self, task):
            assert task.task_type == "improvement_execution"
            return SimpleNamespace(
                success=True, output={"branch": "pantheon/demo", "change_summary": "updated"}
            )

    asyncio.run(
        cmd_proposal_apply(
            SimpleNamespace(
                org_name="Demo",
                proposal_id="12345678",
                github_repo=None,
                github_token="token",
                yes=True,
            ),
            confirm_action=lambda *a, **k: True,
            get_orchestrator=lambda: FakeExecutor(),
            get_psm=lambda: psm,
            require_api_key=lambda _command: None,
        )
    )
    assert state_manager.status_updates[-1][1] == "done"
    assert "ローカルブランチ" in capsys.readouterr().out


def test_platform_config_logs_backup_restore(capsys, tmp_path):
    platform_home = tmp_path / ".pantheon"
    platform_home.mkdir()
    (platform_home / "daemon.log").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (platform_home / "scheduler_log.jsonl").write_text(
        '{"cycle": 1}\n{"cycle": 2}\n', encoding="utf-8"
    )
    state_file = platform_home / "platform.json"
    state_file.write_text("{}", encoding="utf-8")
    org = SimpleNamespace(name="Demo", target_repo_path=str(tmp_path / "repo"))
    psm = FakePSM(platform_home, org, FakeProposalStateManager([]))

    asyncio.run(
        cmd_platform_config_set(SimpleNamespace(key="theme", value="dark"), get_psm=lambda: psm)
    )
    asyncio.run(cmd_platform_config(SimpleNamespace(), get_psm=lambda: psm))
    assert "theme" in capsys.readouterr().out

    asyncio.run(cmd_platform_logs(SimpleNamespace(tail=1), get_psm=lambda: psm))
    logs_output = capsys.readouterr().out
    assert "three" in logs_output
    assert '{"cycle": 2}' in logs_output

    asyncio.run(cmd_platform_backup(SimpleNamespace(), get_psm=lambda: psm))
    state_file.write_text('{"theme": "light"}', encoding="utf-8")
    asyncio.run(cmd_platform_restore(SimpleNamespace(), get_psm=lambda: psm))
    assert json.loads(state_file.read_text(encoding="utf-8")) == {"theme": "dark"}


def test_agent_list_and_doctor(capsys, monkeypatch, tmp_path):
    agent = SimpleNamespace(
        name="Planner",
        skills=[SimpleNamespace(value="strategic_planning"), SimpleNamespace(value="org_design")],
    )
    org = SimpleNamespace(name="Demo", get_all_agents=lambda: [agent])
    psm = FakePSM(tmp_path, org, FakeProposalStateManager([]))

    asyncio.run(cmd_agent_list(SimpleNamespace(), get_psm=lambda: psm))
    assert "Planner" in capsys.readouterr().out

    class FakeDoctor:
        def diagnose(self):
            return [
                SimpleNamespace(
                    issue_id="missing_backups_dir",
                    severity="warning",
                    description="missing",
                    auto_fixable=True,
                )
            ]

        def fix_issues(self, issues):
            return len(issues)

    monkeypatch.setattr("core.state.system_doctor.SystemDoctor", FakeDoctor)
    asyncio.run(cmd_doctor(SimpleNamespace(fix=True)))
    assert "自動修復" in capsys.readouterr().out


def test_repo_reader_finds_code_files(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "src" / "app.js").write_text("console.log('hi')", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "ignored.py").write_text("", encoding="utf-8")
    (tmp_path / "README.md").write_text("# readme", encoding="utf-8")

    files = get_file_tree(tmp_path)
    important = get_important_files(tmp_path, max_files=2)

    assert "src/main.py" in files
    assert "src/app.js" in files
    assert ".git/ignored.py" not in files
    assert "src/main.py" in important


def test_doc_generator_health_report_and_ui_helpers(tmp_path, monkeypatch):
    source = tmp_path / "sample.py"
    source.write_text(
        '"""module docs"""\n\n'
        "class Demo:\n"
        '    """class docs"""\n'
        "    def run(self):\n"
        '        """method docs"""\n'
        "        return 1\n\n"
        "def helper():\n"
        '    """function docs"""\n'
        "    return 2\n",
        encoding="utf-8",
    )
    generator = DocGenerator()
    markdown = generator.generate_markdown(source)
    assert "# sample.py" in markdown and "function docs" in markdown

    report = HealthReportGenerator().generate_weekly_report(
        "Demo",
        {"health_score": 80, "proposals_count": 2, "accepted_count": 2, "knowledge_count": 5},
    )
    assert "Demo" in HealthReportGenerator().format_cli(report)

    approver = InteractiveApprover()
    assert "未承認の提案" in approver.list_pending_proposals([{"title": "Fix"}])
    assert approver.parse_action("approve", "abc") == ("approve", "abc")

    helper = ErrorMessageHelper()
    assert "ORG_NOT_FOUND" not in helper.format_error("ORG_NOT_FOUND")
    assert "nope" in helper.wrap_exception(KeyError("nope"))

    monkeypatch.setenv("PANTHEON_LANG", "en")
    assert I18n().t("status_healthy") == "Healthy"

    dashboard = RichDashboard(use_rich=False)
    assert "health" in dashboard.render_org_summary(
        {
            "name": "Demo",
            "health_score": 91,
            "proposal_count": 1,
            "agent_count": 2,
            "lifecycle_stage": "active",
        }
    )

    wizard = SetupWizard()
    monkeypatch.setattr("core.ui.setup_wizard.get_platform_home", lambda: tmp_path)
    (tmp_path / "organizations").mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".pantheon").mkdir()
    (tmp_path / "organizations" / "demo.json").write_text(
        json.dumps({"target_repo_path": str(repo)}), encoding="utf-8"
    )
    wizard_text = wizard.format_wizard_cli()
    assert "Claude CLI 認証" in wizard_text


def test_pr_creator_updates_existing_file(monkeypatch, tmp_path):
    class FakeGithubException(Exception):
        pass

    class FakeContent:
        sha = "abc123"

    class FakeBranch:
        commit = SimpleNamespace(sha="deadbeef")

    class FakePull:
        html_url = "https://example.com/pr/1"

    class FakeRepo:
        default_branch = "main"

        def __init__(self):
            self.updated = []
            self.created = []
            self.pull_kwargs = None

        def get_branch(self, branch):
            return FakeBranch()

        def get_contents(self, path, ref=None):
            return FakeContent()

        def update_file(self, **kwargs):
            self.updated.append(kwargs)

        def create_file(self, **kwargs):
            self.created.append(kwargs)

        def create_pull(self, **kwargs):
            self.pull_kwargs = kwargs
            return FakePull()

    repo = FakeRepo()
    fake_module = ModuleType("github")
    fake_module.GithubException = FakeGithubException

    class FakeGithub:
        def __init__(self, token):
            self.token = token

        def get_repo(self, slug):
            return repo

    fake_module.Github = FakeGithub
    monkeypatch.setitem(sys.modules, "github", fake_module)

    pr_url = asyncio.run(
        create_improvement_pr(
            repo_path=tmp_path,
            github_token="token",
            github_repo="owner/repo",
            file_path="src/app.py",
            modified_content="print('ok')",
            suggestion={
                "title": "Improve cache",
                "description": "desc",
                "expected_impact": "faster",
            },
        )
    )
    assert pr_url == "https://example.com/pr/1"
    assert repo.updated and not repo.created
    assert repo.pull_kwargs["title"].startswith("[Pantheon]")


def test_pr_creator_creates_file_when_missing(monkeypatch, tmp_path):
    class FakeGithubException(Exception):
        pass

    class FakeBranch:
        commit = SimpleNamespace(sha="deadbeef")

    class FakePull:
        html_url = "https://example.com/pr/2"

    class FakeRepo:
        default_branch = "main"

        def __init__(self):
            self.created = []

        def get_branch(self, branch):
            return FakeBranch()

        def get_contents(self, path, ref=None):
            raise FakeGithubException("missing")

        def update_file(self, **kwargs):
            raise AssertionError("update_file should not be called")

        def create_file(self, **kwargs):
            self.created.append(kwargs)

        def create_pull(self, **kwargs):
            return FakePull()

    repo = FakeRepo()
    fake_module = ModuleType("github")
    fake_module.GithubException = FakeGithubException

    class FakeGithub:
        def __init__(self, token):
            self.token = token

        def get_repo(self, slug):
            return repo

    fake_module.Github = FakeGithub
    monkeypatch.setitem(sys.modules, "github", fake_module)

    pr_url = asyncio.run(
        create_improvement_pr(
            repo_path=tmp_path,
            github_token="token",
            github_repo="owner/repo",
            file_path="src/new.py",
            modified_content="print('new')",
            suggestion={"title": "Add file", "description": "desc", "expected_impact": "better"},
        )
    )
    assert pr_url == "https://example.com/pr/2"
    assert repo.created
