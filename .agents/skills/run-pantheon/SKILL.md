---
name: run-pantheon
description: Launch and smoke-check the Pantheon app (FastAPI backend + React 19 frontend) on Windows. Use when asked to run, serve, start, preview, or manually verify the app or a UI change. (Screenshots need the Playwright MCP enabled — see AGENTS.md MCP note; this skill only serves + curl-smoke-checks.)
allowed-tools: Bash(pantheon*) Bash(npm*) Bash(.venv/Scripts/*) Bash(curl*)
---

# Run Pantheon

Prereqs: backend deps in `.venv` (`pip install -e ".[dev,web]"`); frontend deps installed
(`npm install` in `web/frontend/`). `python`/`node`/`pantheon` resolve via the venv + winget Node
on PATH (see `.Codex/settings.local.json`). Generation uses the local `Codex` CLI — no API keys.

## A) Serve the built app (quick look / production-like) — port 7860

```
cd web/frontend && npm run build && cd ../..      # build the SPA into web/dist (first time / after FE changes)
pantheon serve --port 7860                          # FastAPI serves web/dist + /api + /ws
```
Open http://localhost:7860 ; OpenAPI docs at http://localhost:7860/docs .
(`pantheon` not found? use `.venv/Scripts/pantheon.exe serve --port 7860`.)

## B) Live frontend development (hot reload)

The Vite dev server proxies `/api` and `/ws` to `http://localhost:8000`, so run the backend there:

```
pantheon serve --port 8000        # terminal 1 (backend/API)
cd web/frontend && npm run dev    # terminal 2 (Vite dev server, hot reload)
```
Open the Vite URL it prints (default http://localhost:5173).

## Smoke check (no browser)

```
curl.exe -s http://localhost:7860/api/platform/status     # expect JSON
curl.exe -s -o NUL -w "%{http_code}" http://localhost:7860/nonexistent   # expect 404 (Windows: NUL, not /dev/null)
```

## Stop

Ctrl-C the server terminal(s). For long runs, prefer launching the server with the Bash tool's
`run_in_background` so you can keep working, then curl to verify.
