---
name: atlas
description: Understand or extend Pantheon's Repository Atlas — the human-facing overview of usage flows, the module dependency graph, the CLI command tree, and the FastAPI route map. Use when asked to visualize/explain the repo at a high level, regenerate the atlas, or add/update a usage flow.
---

# Pantheon Repository Atlas

The **Atlas** turns the large Pantheon repo into a navigable overview: the canonical
**usage-flow catalog** (with honest per-flow health), the **module dependency graph**
(collapsed to subsystems), the **CLI command tree**, the **FastAPI route map**, and a
**subsystem inventory**. It is read-only and never touches the generation backend.

## Where it lives

- **Introspection** — `core/atlas/introspect.py` (`build_atlas()`): runtime-introspects the
  argparse parser (`commands.build_parser`) and the FastAPI `app`, AST-parses project Python for
  the dependency graph, scans `web/frontend/src` for pages/routes, and merges the curated flows.
- **Curated flow catalog** — `core/atlas/data/flows.json` (the only hand-maintained part; everything
  else is derived live). `core/atlas/data/subsystem_maps.json` is the raw subsystem analysis it came from.
- **API** — `GET /api/atlas` in `web/server.py` (runs `build_atlas` off the event loop via `asyncio.to_thread`).
- **Web UI** — `web/frontend/src/pages/AtlasPage.tsx`, route `/atlas`, nav item "Atlas".
- **CLI** — `pantheon atlas` (summary), `pantheon atlas --json`, `pantheon atlas -o <path>` (export).

## How to view it

```powershell
.\.venv\Scripts\python.exe main.py atlas            # human summary (flow health + inventory)
.\.venv\Scripts\python.exe main.py atlas --json     # full model as JSON
pantheon serve  # then open http://localhost:7860/atlas
```

## How to add or update a usage flow

1. Edit `core/atlas/data/flows.json` — add a flow object with `id` (kebab-case), `name`, `summary`,
   `trigger` (`kind` + `name`), `steps` (`component`/`action`), `surfaces`, optional `state` /
   `verification`, `status` (`solid|partial|fragile|unknown`), and `known_issues`.
2. Keep `verification` pointing at real `tests/test_*.py` files so the health claim is checkable.
3. Re-run `pantheon atlas` to confirm it loads, and `pytest tests/test_atlas.py -q`.

## When something is "fragile/partial"

`status` and `known_issues` are deliberately honest — they reflect the subsystem analysis. Treat a
`fragile` flow's `known_issues` as the backlog: fix the cited file, add a regression test (see
`tests/test_flow_hardening.py` for the pattern), then upgrade the flow's `status`.

## Don't

- Don't wire any generation/LLM call into the Atlas — it must stay offline and read-only.
- Don't hardcode counts; everything except `flows.json` is derived from the live repo.
