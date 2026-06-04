#!/usr/bin/env node
/**
 * Claude Code `Stop` hook — auto-commit (and push) working-tree changes each turn.
 *
 * Cross-platform Node port of the original PowerShell hook. Policy (unchanged):
 *   - On a DEFAULT branch (main/master): create a NEW work branch first
 *     (work/auto-<timestamp>) and commit there — never commit onto the default branch.
 *   - On any other branch: commit there AND push to origin.
 * Reads the Claude hook JSON on stdin (uses its `cwd`) and NEVER blocks the turn
 * (always exits 0); a failed push is non-fatal.
 */
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

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
const status = git(["status", "--porcelain"], cwd);
if (!status) process.exit(0);

// --- on a default branch, move to a fresh work branch first ---------------- //
let branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd);
const pad = (n) => String(n).padStart(2, "0");
const d = new Date();
const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
const human = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;

if (branch === "main" || branch === "master") {
  git(["checkout", "-b", `work/auto-${stamp}`], cwd);
  branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd);
}

// --- commit ---------------------------------------------------------------- //
const changed = status.split(/\r?\n/).filter(Boolean).length;
git(["add", "-A"], cwd);
const message = `checkpoint: auto-commit (${changed} files, ${human})\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`;
git(["commit", "-m", message], cwd);

// --- push the work branch to origin (non-fatal) --------------------------- //
if (git(["remote"], cwd) && branch) {
  git(["push", "-u", "origin", branch], cwd);
}

process.exit(0);
