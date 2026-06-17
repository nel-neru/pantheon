<!-- Pantheon PR template. Keep it short; delete sections that don't apply. -->

## What & why
<!-- One or two sentences: what this changes and the motivation. Link issues with #id. -->

## Changes
-

## Type
- [ ] Backend (CLI / `core` / `agents`)
- [ ] Web API (`web/server.py`)
- [ ] Frontend (`web/frontend/`)
- [ ] Docs / config / tooling

## Checklist
- [ ] New Python files start with `from __future__ import annotations`; no `datetime.utcnow()` (use `datetime.now(timezone.utc)`).
- [ ] `SpecialistAgent.skills` is 2–3; new state goes to `~/.pantheon` (global) or `<repo>/.pantheon` (per-repo).
- [ ] New `AgentSkill` updates the enum **and** `skills/<value>.yaml`. New CLI verb wires parser → handler → `main.HANDLERS` + test.
- [ ] `web/server.py` explicit 404 handling preserved (if touched).
- [ ] Backend tests pass at baseline: `\.venv\Scripts\python.exe -m pytest tests\ -q` → only the **2 known Windows failures** (chmod 0o600), no new ones.
- [ ] Frontend (if touched): `npm test` and `npm run build` green in `web/frontend/`.
- [ ] `\.venv\Scripts\python.exe -m ruff check . --fix` clean.

## Notes for reviewers
<!-- Anything risky, follow-ups, or out-of-scope items. -->
