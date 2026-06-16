@AGENTS.md

<!-- ▲ The line above imports AGENTS.md (project overview, directory map, component
     responsibilities, dev conventions). Claude Code does NOT read AGENTS.md natively,
     so this import is the bridge. Keep architecture facts in AGENTS.md; keep
     Claude-Code-specific operational guidance below. Both load every session. -->

# Claude Code — Pantheon operating guide

Pantheon is a **Python 3.12 CLI + FastAPI backend + React 19 / Vite / TypeScript / Tailwind v4 frontend**.
All "thinking"/generation runs through the **local `claude` CLI** (`core/runtime/claude_code.py`) —
there are **NO hosted-LLM API keys** (legacy provider key fields in `main.py` / `web/server.py` are
vestigial GUI compatibility, not a generation path). Authenticate once with `claude` itself.

## Commands (Windows dev env — `python` & `node` are NOT on PATH by default)

Backend (project venv at `.venv/`):

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -q              # full backend suite
.\.venv\Scripts\python.exe -m pytest tests\ --collect-only -q   # collection health only
.\.venv\Scripts\python.exe -m pytest tests\test_web_server.py -q   # single file
.\.venv\Scripts\python.exe -m ruff check .                  # lint (rules E,F,I; line-length 100; E501 ignored)
.\.venv\Scripts\python.exe -m ruff check . --fix            # autofix imports/lint
.\.venv\Scripts\python.exe -m ruff format .                 # format
pantheon serve --port 7860                                  # run the app (FastAPI, serves web/dist)
pantheon serve --ui atelier                                 # serve the new Atelier GUI instead (web/atelier/dist; PANTHEON_UI env also works)
```

Frontend (`web/frontend/`; Node v24 installed via winget — see `.claude/settings.local.json` `env.PATH`):

```powershell
npm test            # vitest run (jsdom + Testing Library)
npm run build       # tsc -b && vite build  -> web/dist
npm run dev         # vite dev server (proxies /api + /ws -> http://localhost:8000)
```

Bash-tool equivalents use forward slashes: `.venv/Scripts/python -m pytest tests/ -q`.

## Test baseline — DO NOT treat these as regressions

On Windows the full backend suite has **2 long-standing failures** unrelated to any change
(verified against a clean tree). Only NEW failures beyond these count:

- POSIX `chmod 0o600` not honored on Windows: `test_get_settings_warns_on_open_permissions`,
  `test_update_settings_sets_restrictive_permissions`

(4 former path-separator failures were fixed 2026-06-12 by normalizing relative paths to
POSIX with `as_posix()` in `repo_reader` / `dependency_graph` / `improvement_executor_agent`.)

(The 2 former order-flaky tests — `test_backup_manager_cleanup_old`,
`test_get_improvement_history` — were root-fixed 2026-06-12: wall-clock timestamps used as
uniqueness keys collided within one Windows clock tick; now disambiguated. If they fail, it IS a regression.)

## Git & commits

- A **`Stop` hook auto-commits** the working tree each turn (`.claude/hooks/auto-commit.mjs`):
  on `main`/`master` it first creates a `work/auto-<timestamp>` branch (never commits onto the
  default branch), then commits with a `Co-Authored-By: Claude Opus 4.8` trailer and pushes if a
  remote exists. Pushing/merging to `main` is a deliberate, user-triggered step.
- **Branch naming convention** (always under the `work/` prefix; never commit directly to `main`):
  - `work/<slug>-<YYYYMMDD>` — Claude/human-initiated focused work (`slug` = kebab-case topic,
    e.g. `work/phase6-8-monetization`). Create with `node scripts/new_work_branch.mjs <slug>`
    (or `/new-work-branch`), which branches from an up-to-date `main`.
  - `work/auto-<timestamp>` — the auto-commit hook's fallback (when a turn starts on `main`).
- **Finished-branch detection**: "done" ≡ **merged into `origin/main`**. Run
  `node scripts/branch_status.mjs` (or `/branch-status`) to classify every branch as
  ✅ done (merged → deletable) / 🟡 active (ahead of main) / 💤 stale (active but old).
  `--prune` deletes done local `work/*` branches.
- When you create a commit yourself, end the message with:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Merging a completed work branch into `main`** is systematized via
  `node scripts/merge_to_main.mjs` (or the `/merge-to-main` command). Run it **from the work
  branch when its work is done**: it gates on the backend tests (only the known baseline
  failures allowed — no new regressions), fast-forwards `main` to `origin/main`, merges the
  work branch `--no-ff`, and pushes (never `--force`; aborts cleanly on conflict). Flags:
  `--no-test`, `--stay`, `--delete-branch`, `--dry-run`. The per-turn auto-commit still only
  ever touches work branches; promotion to `main` stays this one deliberate step.

## Non-negotiables (enforced by hooks, not just prose — see `.claude/settings.json`)

- New Python files start with `from __future__ import annotations`.
- Never `datetime.utcnow()` → use `datetime.now(timezone.utc)` (timezone-aware always).
- Do not break full-suite collection/execution, and do not break the explicit 404 handling in `web/server.py`.
- `SpecialistAgent.skills`: min 2, max 3.
- State location: global → `~/.pantheon`; repo-specific → `<repo>/.pantheon`.
- A `PreToolUse` guard (`guard-bash.mjs`, on Bash **and** PowerShell) blocks catastrophic deletes
  (POSIX `rm -rf` in any flag spelling, PowerShell `Remove-Item -Recurse -Force`/`rd /s /q`,
  `find / -delete`, `dd of=/dev/…`, disk format), `git push --force`/force-refspec, and shell
  overwrite/read of secret files; `protect-secrets.mjs` blocks editing them. The shared denylist is
  `.claude/hooks/sensitive-paths.mjs`. Validate hook edits with `node .claude/hooks/pantheon_hook_selftest.mjs`.
- NOTE: the `settings.json` `Read(...)` deny list is NOT a hard boundary while `settings.local.json`
  allows `Bash(*)` — a shell `cat`/`Get-Content` could otherwise read a secret, so `guard-bash.mjs`
  also blocks shell reads of denylisted files. Treat the hooks (not the permission lists) as the real guard.

## `.claude/` tooling map (this repo's Claude Code customizations)

> "Pantheon-agent/skill" = the app's *own* in-product framework (`agents/`, `core/intelligence`).
> "CC-agent/skill/command" = the Claude Code helpers below. They are different things.

- **Subagents** (`.claude/agents/`), model-tiered by cognitive load: Opus —
  `code-reviewer` (read-only diff), `debugger`; Sonnet — `frontend-dev`, `flow-auditor`;
  Haiku (mechanical/monitoring) — `test-triage` (separates the 2 known failures from real
  regressions), `trend-watcher` (Claude Code trends → `.claude/` config suggestions),
  `doc-writer` (keep docs in sync).
- **Skills** (`.claude/skills/`): `run-pantheon` (launch recipe), `pantheon-agent`
  (how to add a Pantheon-agent + skill correctly), `improvement-proposal-flow`,
  `fastapi-endpoint` (add/modify a FastAPI route + test), `atlas` (understand/extend the Repository Atlas).
- **Commands** (`.claude/commands/`): `/add-cli-command`, `/add-web-page`, `/triage-tests`,
  `/atlas` (show/audit the Repository Atlas), `/evolve` (long-running autonomous PDCA loop),
  `/daemon-status` (24h 自律基盤の状態), `/trend-report` (トレンド収集状況), `/spawn-org`
  (ジャンル別 Organization を1コマンド量産), plus the git-lifecycle commands
  `/new-work-branch` · `/branch-status` · `/merge-to-main`.
- **Rules** (`.claude/rules/`): path-scoped guidance for `*.py`, frontend, and `web/server.py`.
- **Output-styles** (`.claude/output-styles/`): `rigor`, `diagram-first`.
- **MCP** (`.mcp.json`): Context7 (version-pinned docs) + Playwright (drive the frontend) — both are
  committed but **disabled by default** in the (git-ignored, personal) `settings.local.json`
  `disabledMcpjsonServers`; remove them from that list to enable.
- Full description: `docs/claude-code-setup.md`.
