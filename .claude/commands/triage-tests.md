---
description: Run and triage Pantheon's full test suites; on Windows there are now 0 known failures (any failure is a regression), so flag real regressions vs the 2 chmod tests that merely skip on Windows and pass on Linux CI.
argument-hint: "[optional: backend | frontend | all]   default all"
---

Delegate to the **test-triage** subagent to run and interpret the tests (scope: $ARGUMENTS, default all).

It should run the backend suite (`.venv/Scripts/python.exe -m pytest tests/ -q`) and, if frontend is
in scope, `cd web/frontend && npm test`, then return ONLY a concise verdict — not raw logs —
distinguishing NEW regressions from the known baseline (the 2 Windows chmod failures
documented in CLAUDE.md / the agent).

If the subagent reports RED (real regressions), summarize each with file:line + one-line cause and
propose the next step (likely hand off to the `debugger` subagent). If GREEN, say so plainly.
