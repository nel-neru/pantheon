---
description: Scaffold a new Pantheon CLI subcommand end-to-end (parser + handler + dispatch + test), wired exactly the way main.py expects.
argument-hint: "[group] [verb]   e.g. org archive   |   doctor   |   platform prune"
---

Add a new Pantheon CLI subcommand for: **$ARGUMENTS**

Wire it the way `main.py` dispatches (it looks up `args.handler_name` in the `HANDLERS` dict and
`asyncio.run`s the result if it's awaitable). Touch all four points — missing one is the usual bug:

1. **Command module** (`commands/<group>.py`, or a new module — modules are auto-discovered by
   `commands/__init__.py:discover_command_modules`): add `register(subparsers)` that does
   `p = subparsers.add_parser("<verb>", help="…日本語…")`, adds any args, and
   `p.set_defaults(handler_name="cmd_<group>_<verb>")`. For a subcommand group, mirror
   `commands/goal.py` (a parent parser + `add_subparsers` + per-verb `set_defaults`).
   Put the real implementation in this module as an `async def` (take injected deps as params:
   `get_psm`, `get_orchestrator`, `require_api_key`, `confirm_action` — see how `org.py`/`goal.py` do it).

2. **Handler wrapper in `main.py`**: add `async def cmd_<group>_<verb>(args): await _cmd_..._impl(args, get_psm=_get_psm, ...)`
   injecting the concrete deps (`_get_psm`, `_get_orchestrator`, `_require_api_key`, `_confirm_action`).
   If the command needs the `claude` backend, gate with `_require_api_key` (which now checks
   `claude_available()`), not an API key.

3. **Register in `HANDLERS`** (`main.py`): add `"cmd_<group>_<verb>": cmd_<group>_<verb>,`.

4. **Test** (`tests/test_*.py`): assert wiring with
   `build_parser().parse_args([...]).handler_name == "cmd_<group>_<verb>"` (see
   `tests/test_pdca_rounds_71_80.py::test_new_cli_handlers_are_registered`), plus a behavior test
   that calls the handler with a fake `get_psm`/`tmp_path`.

Conventions: new files start with `from __future__ import annotations`; tz-aware datetimes; ruff clean.

Verify:
```
.venv/Scripts/python.exe -m pytest tests/ -q -k "parser or handler or <group>"
pantheon <group> <verb> --help        # or .venv/Scripts/pantheon.exe ...
.venv/Scripts/python.exe -m ruff check commands/ main.py --fix
```
