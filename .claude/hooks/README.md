# `.claude/hooks/` — Pantheon Claude Code hooks

Cross-platform **Node** hook scripts wired in `../settings.json`. Node is used (not `.ps1`/`.sh`)
because Claude Code already ships Node, so one command works on Windows/macOS/Linux. Each script
reads the hook JSON on **stdin**, follows the documented exit/JSON contract, and is defensive
(never crashes the turn).

> The hook launcher needs `node` on `PATH`. On this machine Node lives at a winget path that is not
> on PATH by default, so `../settings.local.json` prepends it via `env.PATH`. **Settings load at
> session start** — after editing hooks/settings, start a new session for changes to take effect.
>
> ⚠️ **Fragile PATH pin:** `settings.local.json`'s `env.PATH` hardcodes a *version-pinned* Node dir
> (e.g. `node-v24.16.0-win-x64`). When winget upgrades Node LTS the folder name changes and the pin
> breaks — `node` falls off PATH and **all** of these hooks silently stop running. After a Node
> upgrade, update that PATH segment (or switch to nvm-windows / a stable shim). Quick check:
> `node --version` should print from the winget Node dir.

| Script | Event (matcher) | Blocking? | What it does |
|---|---|---|---|
| `guard-bash.mjs` | `PreToolUse` (Bash\|PowerShell) | yes (`deny`) | Denies only catastrophic commands, flag-order-independent and for BOTH shells: root/home/drive/cwd `rm -rf` (incl. `rm -r -f` / `rm --recursive --force`), PowerShell `Remove-Item -Recurse -Force` / `rd /s /q` of a drive root, `find / -delete`, `dd of=/dev/…`, disk format, fork bomb, `git push --force`/force-refspec w/o lease, `git clean -x`, and shell overwrite/read of a real secret file (shared denylist). Ordinary `rm -rf node_modules` / `find . -name '*.pyc' -delete` pass. |
| `protect-secrets.mjs` | `PreToolUse` (Write\|Edit) | yes (`deny`) | Denies edits to real secret/credential/key files via the shared `sensitive-paths.mjs` denylist (`.env`/`.env.<x>`, `*.pem`/`*.key`/`*.pfx`, `id_rsa`, `.credentials.json`, `secrets.json`, `.npmrc`, …). Allows templates (`.example`/`.sample`/`.template`) AND ordinary source whose name merely contains a secret token (e.g. `secret_manager.py`). |
| `sensitive-paths.mjs` | (shared module) | n/a | `isSecretFile()` denylist imported by `protect-secrets`, `auto-commit`, and `guard-bash` — single source of truth so write/commit/push/read protection can't diverge. |
| `format.mjs` | `PostToolUse` (Write\|Edit) | no | Runs `ruff format` (idempotent; not `--fix`) on edited `.py` via the venv interpreter, **synchronously** (sub-second; avoids a deferred reformat racing a same-turn re-read/re-edit). Skips TS/CSS (no formatter configured). |
| `post-edit-checks.mjs` | `PostToolUse` (Write\|Edit) | yes (`exit 2`) | Single dispatcher: reads stdin once and runs only the checks whose file-path regex matches the edited file — config-validation (`config/`/`skills/` yaml), Atlas flows.json consistency (atlas/commands/main/server/pages), planning-doc hygiene (`docs/*.md`). Replaced 3 separate serial hooks → fewer node cold-starts. Each check runs its `scripts/*.py`; any failure → `exit 2` with combined stderr; unrelated files / unexpected errors → `exit 0`. |
| `session-context.mjs` | `SessionStart` (startup\|resume\|clear) | no | Injects a short dynamic git snapshot (branch, uncommitted count, last commit) as `additionalContext`. |
| `auto-commit.mjs` | `Stop` | no | Auto-commits the working tree each turn. On `main`/`master` it first branches to `work/auto-<timestamp>` (collision-safe; never commits onto the default branch), **un-stages any secret-shaped file (shared denylist) so it is never committed or pushed**, commits with a `Co-Authored-By: Claude Opus 4.8` trailer, and pushes if a remote exists. Always exits 0. |

## Self-test

```
node .claude/hooks/pantheon_hook_selftest.mjs   # 57 cases: catastrophic/secret payloads DENY, ordinary dev commands ALLOW
```
It pipes crafted payloads through the real `guard-bash.mjs` / `protect-secrets.mjs` and asserts the
deny/allow outcome — and is the regression fixture for every historical guard bypass (split/long rm
flags, PowerShell deletes, force-refspec push, secret reads). Run it after editing any guard hook.

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
