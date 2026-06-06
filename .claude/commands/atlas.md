---
description: Show the Pantheon Repository Atlas (usage-flow health, dependency graph, CLI/API map) or audit flows.
argument-hint: "[optional: a flow id/name to audit | 'open' to launch the web UI]   default = summary"
---

Show the Repository Atlas overview, scope: $ARGUMENTS (default: full summary).

Steps:
1. Run `.venv/Scripts/python.exe main.py atlas` and relay the human summary (flow health + inventory
   + high-severity known issues). For machine output use `... main.py atlas --json`.
2. If `$ARGUMENTS` names a flow (e.g. `analyze-propose-approve-apply`) or says "audit", delegate to
   the **flow-auditor** subagent to verify that flow end-to-end and report honest health.
3. If `$ARGUMENTS` is "open", remind the user to `pantheon serve` and open
   http://localhost:7860/atlas (the live React Atlas page).

The Atlas is read-only and offline (no generation backend). The only hand-maintained input is
`core/atlas/data/flows.json`; everything else (CLI tree, API routes, dependency graph, inventory)
is derived live from the repo. See the `atlas` skill for how to add/update a flow.
