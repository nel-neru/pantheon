---
description: Python backend conventions for Pantheon (CLI, core/, agents/, web/server.py, tests/)
paths:
  - "**/*.py"
---

# Python conventions (Pantheon backend)

- Start every new module with `from __future__ import annotations`.
- **Never** `datetime.utcnow()` — use `datetime.now(timezone.utc)`; all datetimes are timezone-aware.
- Type-hint public functions; prefer explicit return types.
- Data models follow the existing **Pydantic v2 / dataclass** patterns (see `core/models/organization.py`).
- Async: no blocking I/O inside `async def` handlers; `pytest` runs with `asyncio_mode = "auto"`.
- Lint/format with ruff (`select = E,F,I`, line-length 100, `E501` ignored):
  `.venv/Scripts/python.exe -m ruff check . --fix` then `... -m ruff format .`.

## Tests

- Add tests under `tests/` using pytest; mirror the `tmp_path` + `monkeypatch.setattr("...get_platform_home", lambda: tmp_path)` fixture pattern (see `tests/conftest.py`).
- Run: `.venv/Scripts/python.exe -m pytest tests/ -q`. Do not break full-suite collection.
- 6 Windows failures are pre-existing (path-sep + chmod) — not regressions (see CLAUDE.md).

## Adding things (from AGENTS.md "new-feature recipe")

- **New CLI subcommand**: add `cmd_*` + `register(subparsers)` with `set_defaults(handler_name="cmd_*")` in `commands/<mod>.py`, then wire the wrapper into `main.HANDLERS`. (`/add-cli-command` scaffolds this.)
- **New Pantheon-agent**: subclass `BaseAgent` (`agents/base.py`); honor `async run(AgentTask)->AgentResult`.
- **New skill**: add the member to the `AgentSkill` enum (`core/models/organization.py`) AND create `skills/<value>.yaml` (loaded by `SkillLoader`; the YAML `id` must equal the enum value). `SpecialistAgent.skills` = min 2, max 3. (See the `pantheon-agent` skill.)
- Register new capabilities via `CapabilityRegistry`.
- State: global → `~/.pantheon`; repo-specific → `<repo>/.pantheon`.

## Backend = local `claude` CLI

Generation goes through `core/runtime/claude_code.ClaudeCodeProvider` (use `claude_available()` to gate). No API keys. Do not add hosted-LLM SDK calls.
