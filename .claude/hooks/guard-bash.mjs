#!/usr/bin/env node
/**
 * Claude Code `PreToolUse` (Bash) hook — deny genuinely catastrophic commands.
 *
 * Intentionally narrow: it does NOT block ordinary dev commands like
 * `rm -rf node_modules`. It only denies operations that are almost never
 * recoverable (root/home wipes, force-push without lease, disk format, fork
 * bombs, shell-redirect overwrites of secret files). Everything else passes
 * through so the broad allow-list / `auto` mode keeps its velocity.
 *
 * Returns a PreToolUse `permissionDecision: "deny"` (with reason) as JSON.
 */
import { readFileSync } from "node:fs";

let cmd = "";
try {
  const { tool_input } = JSON.parse(readFileSync(0, "utf8"));
  cmd = (tool_input && tool_input.command) || "";
} catch {
  process.exit(0);
}

const RULES = [
  // rm -rf targeting a root / home / drive-root / .git / the repo root itself
  {
    re: /\brm\s+(-[a-z]*\s+)*-?[a-z]*r[a-z]*f[a-z]*\b[^&|;]*\s(\/|~|\$HOME|%USERPROFILE%|[a-zA-Z]:\\?|\.\s*$|\.git\b|\*\s*$)/i,
    why: "recursive force-delete of a root/home/drive/.git path",
  },
  { re: /\brm\s+-[a-z]*\s+\/(\s|$)/i, why: "rm of the filesystem root" },
  { re: /:\s*\(\s*\)\s*\{[^}]*\}\s*;/, why: "fork bomb" },
  { re: /\bgit\s+push\b[^&|;]*\s(--force\b|-f\b)(?![-\w])/i, why: "git push --force (use --force-with-lease)" },
  { re: /\b(mkfs\b|diskpart\b|format\s+[a-zA-Z]:)/i, why: "disk format" },
  { re: />\s*\/dev\/(sd|nvme|disk)/i, why: "raw block-device write" },
  // shell redirect that would clobber a real secret file (not .env.example)
  { re: />>?\s*(\.\/)?(\.env)(\s|$)/i, why: "shell overwrite of .env" },
  { re: /\bgit\s+clean\b[^&|;]*-[a-z]*x/i, why: "git clean -x (wipes gitignored files incl. .env/.venv)" },
];

const hit = RULES.find((r) => r.re.test(cmd));
if (hit) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason:
          `Blocked by Pantheon guardrail: ${hit.why}. ` +
          `If this is truly intended, run it yourself in a terminal.`,
      },
    }),
  );
  process.exit(0);
}

process.exit(0);
