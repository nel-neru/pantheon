# `.claude/hooks/` — Pantheon Claude Code hooks

Cross-platform **Node** hook scripts wired in `../settings.json`. Node is used (not `.ps1`/`.sh`)
because Claude Code already ships Node, so one command works on Windows/macOS/Linux. Each script
reads the hook JSON on **stdin**, follows the documented exit/JSON contract, and is defensive
(never crashes the turn).

> The hook launcher needs `node` on `PATH`. On this machine Node lives at a winget path that is not
> on PATH by default, so `../settings.local.json` prepends it via `env.PATH`. **Settings load at
> session start** — after editing hooks/settings, start a new session for changes to take effect.

| Script | Event (matcher) | Blocking? | What it does |
|---|---|---|---|
| `guard-bash.mjs` | `PreToolUse` (Bash) | yes (`deny`) | Denies only catastrophic commands (root/home `rm -rf`, drive format, fork bomb, `git push --force` w/o lease, `git clean -x`, shell overwrite of `.env`). Ordinary `rm -rf node_modules` passes. |
| `protect-secrets.mjs` | `PreToolUse` (Write\|Edit) | yes (`deny`) | Denies edits to `.env`/`.env.<x>` and credential/key files (`*.pem`, `*.key`, `id_rsa`, `.credentials.json`, `secret*`). Allows `.env.example`/`.sample`/`.template`. |
| `format.mjs` | `PostToolUse` (Write\|Edit), `async` | no | Runs `ruff format` (idempotent; not `--fix`) on edited `.py` via the venv interpreter. Skips TS/CSS (no formatter configured). |
| `session-context.mjs` | `SessionStart` (startup\|resume\|clear) | no | Injects a short dynamic git snapshot (branch, uncommitted count, last commit) as `additionalContext`. |
| `auto-commit.mjs` | `Stop` | no | Auto-commits the working tree each turn. On `main`/`master` it first branches to `work/auto-<timestamp>` (never commits onto the default branch), commits with a `Co-Authored-By: Claude Opus 4.8` trailer, and pushes if a remote exists. Always exits 0. |

## Self-test

```
node <path-to>/pantheon_hook_selftest.mjs   # see commit history / docs for the harness
```
Or pipe a payload manually, e.g.:
```
echo '{"tool_input":{"command":"git push --force"}}' | node .claude/hooks/guard-bash.mjs
# -> {"hookSpecificOutput":{"permissionDecision":"deny",...}}
```

## Editing guidance

- Keep every script non-blocking on its own failure (wrap in try/catch, `process.exit(0)`), except the
  two guards which intentionally emit a `permissionDecision: "deny"` JSON.
- `PreToolUse` decisions go in `hookSpecificOutput.permissionDecision`; `PostToolUse`/`Stop` use a
  top-level `{"decision":"block"}` instead — don't mix them up.
- Resolve tool paths explicitly (e.g. the venv `python.exe`) so scripts don't depend on `PATH`.
