---
name: fastapi-endpoint
description: Add or modify a FastAPI endpoint in Pantheon's web/server.py the right way. Use when adding/changing a REST route, WebSocket, or API response shape in the web backend.
---

# Add / modify a FastAPI endpoint (`web/server.py`)

Pantheon's web API is a single FastAPI app in `web/server.py`, backed by `PlatformStateManager`,
serving the built SPA from `web/dist`. REST lives under `/api`, WebSocket under `/ws`.

## Rules (do not break)

- **Preserve the explicit 404 handling** — there are tests for it (`tests/test_web_server.py`).
  Do not let a refactor swallow unknown paths into a catch-all.
- Handlers are `async`; keep them non-blocking (no sync file/network/CPU-bound work inline).
- Validate request bodies with **Pydantic v2** models; return JSON-serializable dicts/models.
- **Do not** add hosted-LLM SDK calls. Generation goes through `core/runtime/Codex` only.
  The `_PROVIDER_KEY_MAPPING` / settings-key endpoints are legacy GUI compat — don't extend them.

## Steps

1. Locate an existing route near your feature in `web/server.py` and mirror its shape (decorator,
   path under `/api/...`, return type, error handling).
2. Read/write platform state through the existing `PlatformStateManager` accessor used by neighbors
   (don't open state files directly).
3. If the frontend will call it, add the client function in `web/frontend/src/lib/api.ts`.
4. Add a test in `tests/test_web_server.py`. The suite monkeypatches `get_platform_home` to a
   `tmp_path`; follow the existing fixtures. Assert both the happy path and the relevant error/404.

## Verify

```
.venv/Scripts/python.exe -m pytest tests/test_web_server.py -q
.venv/Scripts/python.exe -m ruff check web/server.py --fix
```
