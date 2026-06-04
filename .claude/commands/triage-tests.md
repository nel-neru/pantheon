---
description: Run and triage Pantheon's full test suites, separating real regressions from the 6 known pre-existing Windows failures.
argument-hint: "[optional: backend | frontend | all]   default all"
---

Delegate to the **test-triage** subagent to run and interpret the tests (scope: $ARGUMENTS, default all).

It should run the backend suite (`.venv/Scripts/python.exe -m pytest tests/ -q`) and, if frontend is
in scope, `cd web/frontend && npm test`, then return ONLY a concise verdict — not raw logs —
distinguishing NEW regressions from the known baseline (the 6 Windows path-sep/chmod failures and the
2 order-flaky tests documented in CLAUDE.md / the agent).

If the subagent reports RED (real regressions), summarize each with file:line + one-line cause and
propose the next step (likely hand off to the `debugger` subagent). If GREEN, say so plainly.
