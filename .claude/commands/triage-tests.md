---
description: Run and triage Pantheon's full test suites; on Windows there are now 0 known failures (any failure is a regression), so flag real regressions vs the 2 chmod tests that merely skip on Windows and pass on Linux CI.
argument-hint: "[optional: backend | frontend | all]   default all"
---

Delegate to the **test-triage** subagent to run and interpret the tests (scope: $ARGUMENTS, default all).

It should run the backend suite (`.venv/Scripts/python.exe -m pytest tests/ -q`) and, if frontend is
in scope, `cd web/frontend && npm test`, then return ONLY a concise verdict — not raw logs —
distinguishing NEW regressions from the baseline. On Windows the baseline is now 0 known failures,
so ANY failure is a regression; the 2 chmod tests (`test_get_settings_warns_on_open_permissions`,
`test_update_settings_sets_restrictive_permissions`) are SKIPPED on Windows (POSIX `chmod 0o600` is
a no-op there) and RUN and PASS on Linux CI — a SKIP is expected, not a failure.

If the subagent reports RED (real regressions), summarize each with file:line + one-line cause and
propose the next step (likely hand off to the `debugger` subagent). If GREEN, say so plainly.
