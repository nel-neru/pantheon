from __future__ import annotations

from core.security.auditor import SecurityAuditor


def test_auditor_detects_api_key_exposure(tmp_path):
    target = tmp_path / "bad.py"
    target.write_text("TOKEN = 'sk-secret-value'\n", encoding="utf-8")
    issues = SecurityAuditor().audit_file(target)
    assert any(issue.issue_id.startswith("api_key_exposure") for issue in issues)


def test_auditor_detects_eval_usage(tmp_path):
    target = tmp_path / "bad.py"
    target.write_text("eval(user_input)\n", encoding="utf-8")
    issues = SecurityAuditor().audit_file(target)
    assert any(issue.issue_id.startswith("eval_usage") for issue in issues)


def test_auditor_clean_file_no_issues(tmp_path):
    target = tmp_path / "good.py"
    target.write_text("def safe():\n    return 1\n", encoding="utf-8")
    assert SecurityAuditor().audit_file(target) == []


def test_auditor_directory_scan(tmp_path):
    (tmp_path / "a.py").write_text("TOKEN = 'ghp_secret'\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("exec(code)\n", encoding="utf-8")
    issues = SecurityAuditor().audit_directory(tmp_path)
    assert len(issues) >= 2
