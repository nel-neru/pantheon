#!/usr/bin/env node
/**
 * Claude Code `SessionStart` hook — inject a short DYNAMIC status snapshot.
 *
 * Static facts (commands, conventions, test baseline) live in CLAUDE.md and load
 * every session; this hook only adds timely git state so it doesn't duplicate them.
 */
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

let cwd = process.cwd();
try {
  const raw = readFileSync(0, "utf8");
  if (raw) {
    const p = JSON.parse(raw);
    if (p && typeof p.cwd === "string" && p.cwd) cwd = p.cwd;
  }
} catch {
  /* ignore */
}

const git = (args) => {
  try {
    return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
};

if (git(["rev-parse", "--is-inside-work-tree"]) !== "true") process.exit(0);

const branch = git(["rev-parse", "--abbrev-ref", "HEAD"]);
const dirty = git(["status", "--porcelain"]).split(/\r?\n/).filter(Boolean).length;
const last = git(["log", "-1", "--pretty=%h %s"]);

const lines = [
  "Pantheon git snapshot (via .claude/hooks/session-context.mjs):",
  branch ? `- branch: ${branch}${(branch === "main" || branch === "master") ? " (Stop hook will branch to work/auto-* before committing)" : ""}` : "",
  `- uncommitted files: ${dirty}`,
  last ? `- last commit: ${last}` : "",
].filter(Boolean);

process.stdout.write(
  JSON.stringify({
    hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: lines.join("\n") },
  }),
);
process.exit(0);
