---
description: FastAPI server rules for Pantheon (web/server.py) — preserve 404 behavior and the no-API-key backend
paths:
  - "web/server.py"
  - "web/**/*.py"
---

# FastAPI server rules (`web/server.py`)

- **Preserve the explicit 404 handling.** There are tests asserting 404 behavior; do not let
  refactors collapse it into generic handlers. (AGENTS.md lists this as a hard rule.)
- The server is **PlatformStateManager-backed**; REST lives under `/api`, WebSocket under `/ws`.
  It serves the built frontend from `web/dist`.
- **Legacy provider-key surface is vestigial.** `_PROVIDER_KEY_MAPPING` and the
  GET/POST settings endpoints that read/mask `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/… are GUI
  compatibility only. Generation does NOT flow through them — it goes through
  `core/runtime/claude_code.ClaudeCodeProvider` (the local `claude` CLI, no keys). Do not wire any
  new generation path to those env vars.
- New endpoints: keep async handlers non-blocking, validate input with Pydantic models, and add a
  test in `tests/test_web_server.py` (which monkeypatches `get_platform_home` to `tmp_path`).
