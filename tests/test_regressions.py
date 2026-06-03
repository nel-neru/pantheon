"""F12: 既知バグの回帰防止テスト。

- pre_task_orchestrator の `import asyncio` 欠落（並列実行パスの NameError）回帰防止。
- 主要 core/web モジュールが import 時に NameError(F821) を出さないスモーク。
"""

from __future__ import annotations

import importlib

import pytest

MODULES = [
    "core.orchestration.pre_task_orchestrator",
    "core.state.manager",
    "core.bootstrap",
    "core.quality.error_handling",
    "core.intelligence.codebase_snapshot",
    "core.llm.retry",
    "core.llm.client",
    "core.execution.safe_executor",
    "core.execution.cli_registry",
    "agents.core_improvement_agent",
    "web.terminal",
]


def test_pre_task_orchestrator_has_asyncio():
    module = importlib.import_module("core.orchestration.pre_task_orchestrator")
    # 並列実行パスが参照する asyncio がモジュールスコープに存在する（欠落バグの回帰防止）
    assert getattr(module, "asyncio", None) is not None
    assert module.asyncio.__name__ == "asyncio"


@pytest.mark.parametrize("module_name", MODULES)
def test_core_modules_import_cleanly(module_name):
    assert importlib.import_module(module_name) is not None


def test_safe_executor_apply_changes_exists():
    from core.execution.safe_executor import SafeChangeExecutor

    # 複数ファイル原子適用 API が存在する（Iter2 残課題②）
    assert hasattr(SafeChangeExecutor, "apply_changes")
