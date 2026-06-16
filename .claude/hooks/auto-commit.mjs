#!/usr/bin/env node
/**
 * Claude Code `Stop` hook — auto-commit (and push) working-tree changes each turn.
 *
 * Policy:
 *   - On a DEFAULT branch (main/master): create a NEW work branch first
 *     (work/auto-<timestamp>) and commit there — never commit onto the default branch.
 *   - On any other branch: commit there AND push to origin.
 * Reads the Claude hook JSON on stdin (uses its `cwd`) and NEVER blocks the turn
 * (always exits 0); a failed push is non-fatal.
 *
 * SECURITY: before staging, any file matching the shared secret denylist (./sensitive-paths.mjs)
 * is UN-staged so it is never committed or pushed. protect-secrets.mjs only sees files written
 * through Claude's Write/Edit tool; a secret can also arrive via the `claude` CLI subprocess, a
 * build step, a download, or a user-dropped key. The remote (`origin`) may be public, and push is
 * the irreversible outward step — so this is the last line of defense against leaking a secret.
 */
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { isSecretFile } from "./sensitive-paths.mjs";

function git(args, cwd) {
  try {
    return execFileSync("git", args, {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "";
  }
}

// --- resolve the working directory from the hook payload ------------------- //
let cwd = process.cwd();
try {
  const raw = readFileSync(0, "utf8");
  if (raw) {
    const payload = JSON.parse(raw);
    if (payload && typeof payload.cwd === "string" && payload.cwd) cwd = payload.cwd;
  }
} catch {
  /* fall back to process.cwd() */
}

// --- only act inside a git work tree --------------------------------------- //
if (git(["rev-parse", "--is-inside-work-tree"], cwd) !== "true") process.exit(0);

// --- skip when there is nothing to commit ---------------------------------- //
if (!git(["status", "--porcelain"], cwd)) process.exit(0);

// --- timestamp ------------------------------------------------------------- //
let branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd);
const pad = (n) => String(n).padStart(2, "0");
const d = new Date();
const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
const human = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;

// --- on a default branch, move to a fresh work branch first ---------------- //
if (branch === "main" || branch === "master") {
  git(["checkout", "-b", `work/auto-${stamp}`], cwd);
  branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd);
  // same-second double-fire: the first `checkout -b` collided and failed → uniquify with pid.
  if (branch === "main" || branch === "master") {
    git(["checkout", "-b", `work/auto-${stamp}-${process.pid}`], cwd);
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd);
  }
  // last-resort guard: NEVER commit onto a default branch (the whole point of this hook).
  if (branch === "main" || branch === "master") {
    process.stderr.write(
      "auto-commit: could not create a work branch; refusing to commit onto the default branch.\n",
    );
    process.exit(0);
  }
}

// --- stage, then UN-stage any secret/credential file (never commit/push it) - //
// Detection is by FILENAME (sensitive-paths.mjs); it cannot catch secret CONTENT moved into an
// innocent name (e.g. `git mv .env config.yaml`). That residual risk is accepted — the common
// vectors (a dropped .pem/.npmrc, generated credentials.json) are name-detectable and covered.
git(["add", "-A"], cwd);
const staged = git(["diff", "--cached", "--name-only"], cwd).split(/\r?\n/).filter(Boolean);
const secrets = staged.filter((p) => isSecretFile(p));
for (const s of secrets) git(["reset", "-q", "--", s], cwd);
if (secrets.length) {
  process.stderr.write(
    `auto-commit: refused to stage ${secrets.length} secret-looking file(s) — NOT committed or pushed:\n  ` +
      secrets.join("\n  ") +
      "\nMove them out of the working tree or add them to .gitignore.\n",
  );
}

// --- commit only if something safe remains staged -------------------------- //
const remaining = git(["diff", "--cached", "--name-only"], cwd).split(/\r?\n/).filter(Boolean);
if (remaining.length === 0) process.exit(0);

const message = `checkpoint: auto-commit (${remaining.length} files, ${human})\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`;
git(["commit", "-m", message], cwd);

// --- push the work branch to origin (non-fatal) --------------------------- //
if (git(["remote"], cwd) && branch) {
  git(["push", "-u", "origin", branch], cwd);
}

process.exit(0);
