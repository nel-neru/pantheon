"""bootstrap_platform の堅牢性（discovery wave3）。

既定ポリシー生成が失敗（権限/ディスク/破損）してもプラットフォーム起動を止めない
（ポリシー欠如は致命でなく evaluate() で既定へフォールバックする）ことを検証する。
"""

from __future__ import annotations

import logging


def test_bootstrap_survives_policy_save_failure(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)

    from core.policy.engine import PolicyEngine

    def _boom(self, path):
        raise PermissionError("disk full / no perms")

    monkeypatch.setattr(PolicyEngine, "save_default_policy", _boom)

    from core.bootstrap import bootstrap_platform

    with caplog.at_level(logging.WARNING):
        psm = bootstrap_platform()

    # 起動は完了し（psm を返す）、警告で観測可能になっている。
    assert psm is not None
    assert any("policy" in r.message.lower() for r in caplog.records)
