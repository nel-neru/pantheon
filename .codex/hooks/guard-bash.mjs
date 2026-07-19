#!/usr/bin/env node
/**
 * Claude Code `PreToolUse` (Bash | PowerShell) hook — deny genuinely catastrophic commands.
 *
 * Intentionally narrow: it does NOT block ordinary dev commands like `rm -rf node_modules`
 * or `Remove-Item -Recurse -Force node_modules`. It only denies operations that are almost
 * never recoverable (root/home/drive/cwd wipes, disk format, raw-device writes, fork bombs,
 * force-push without lease, and shell overwrite/read of real secret files). Everything else
 * passes so the broad allow-list / `auto` mode keeps its velocity.
 *
 * Covers BOTH shells the project actually uses:
 *   - POSIX:      rm (any flag order/spelling), find -delete/-exec rm, dd of=/dev/…, mkfs, > /dev/…
 *   - PowerShell: Remove-Item -Recurse -Force, rd/rmdir /s /q, del /s /q, Clear-Content of secrets
 * (settings.json registers this hook on matcher "Bash|PowerShell").
 *
 * Returns a PreToolUse `permissionDecision: "deny"` (with reason) as JSON; otherwise exits 0.
 */
import { readFileSync } from "node:fs";
import { isSecretTarget } from "./sensitive-paths.mjs";

let cmd = "";
try {
  const { tool_input } = JSON.parse(readFileSync(0, "utf8"));
  cmd = (tool_input && tool_input.command) || "";
} catch {
  process.exit(0);
}

function deny(why) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason:
          `Blocked by Pantheon guardrail: ${why}. ` +
          `If this is truly intended, run it yourself in a terminal.`,
      },
    }),
  );
  process.exit(0);
}

const stripQuotes = (t) => t.replace(/^['"]+|['"]+$/g, "");

// Normalize a delete-target so the common catastrophic SPELLINGS collapse to a bare root:
//   `/*` and `/` -> `/` ; `~/` and `~/*` -> `~` ; `$HOME/` -> `$home` ; `${HOME}` -> `$home`.
function normTarget(t) {
  let s = stripQuotes(t).toLowerCase();
  s = s.replace(/\$\{([^}]+)\}/, "$$$1"); // ${HOME} -> $home, ${env:userprofile} -> $env:userprofile
  s = s.replace(/[\\/]+\*?$/, ""); // strip trailing slash(es) and an optional trailing /*
  return s === "" ? "/" : s; // "/", "/*", "\" collapsed to root
}

// "almost never recoverable" targets: filesystem root, home, drive root, cwd, bare glob.
// NOTE: only BARE roots match (after normTarget) — `/tmp/x`, `C:\Temp\x`, `./build` all pass through.
const DANGEROUS_TARGET =
  /^(?:\/|~|\$home|\$env:userprofile|%userprofile%|[a-z]:[\\/]?\*?|\.\/?|\*)$/i;

// Stricter set for `find` (excludes `.`/`*`): `find . -name '*.pyc' -delete` is common & safe,
// whereas `find / -delete` / `find /* -delete` / `find ~ -delete` are system-wide catastrophes.
const DANGEROUS_ROOT = /^(?:\/|~|\$home|\$env:userprofile|%userprofile%|[a-z]:[\\/]?\*?)$/i;

const tokensOf = (s) => s.split(/\s+/).map(stripQuotes).filter(Boolean);
const isDangerousTarget = (t) => DANGEROUS_TARGET.test(normTarget(t));
const isDangerousRoot = (t) => DANGEROUS_ROOT.test(normTarget(t));
const hasDangerousTarget = (s) => tokensOf(s).some((t) => isDangerousTarget(t));

// ---------- POSIX `rm` — flag-order-independent, short + long flags ---------- //
{
  const m = cmd.match(/\brm\b([^&|;]*)/i);
  if (m) {
    let recursive = false;
    let force = false;
    const targets = [];
    for (const tok of tokensOf(m[1])) {
      if (/^--recursive$/i.test(tok)) recursive = true;
      else if (/^--force$/i.test(tok)) force = true;
      else if (/^--no-preserve-root$/i.test(tok)) recursive = force = true;
      else if (/^-[a-z]+$/i.test(tok)) {
        if (/r/i.test(tok)) recursive = true; // -r / -R / -rf / -fr …
        if (/f/i.test(tok)) force = true;
      } else if (!/^--/.test(tok)) {
        targets.push(tok);
      }
    }
    if (recursive && force && targets.some((t) => isDangerousTarget(t))) {
      deny("recursive force-delete of a root/home/drive/cwd/glob path");
    }
  }
}

// ---------- PowerShell / cmd recursive force-delete of a dangerous target ---------- //
{
  const m = cmd.match(/\b(remove-item|ri|rd|rmdir|del|erase)\b([^&|;]*)/i);
  if (m) {
    const rest = m[2];
    const recursive = /(^|\s)(-recurse|-r)\b/i.test(rest) || /\s\/s\b/i.test(rest);
    const force = /(^|\s)(-force|-f)\b/i.test(rest) || /\s\/q\b/i.test(rest);
    // `rd`/`rmdir`/`del /s /q` are recursive+forceful by nature on a drive root
    const cmdName = m[1].toLowerCase();
    const inherentlyDestructive = /\s\/s\b/i.test(rest) && /\s\/q\b/i.test(rest);
    if (((recursive && force) || inherentlyDestructive) && hasDangerousTarget(rest)) {
      deny(`${cmdName} recursive force-delete of a root/home/drive path`);
    }
  }
}

// ---------- `find` mass-delete rooted at a dangerous target ---------- //
{
  const m = cmd.match(/\bfind\s+(\S+)([^&|;]*)/i);
  if (m && isDangerousRoot(m[1]) && /\s-delete\b|-exec\s+rm\b/i.test(m[2])) {
    deny("find -delete/-exec rm rooted at a root/home/drive path");
  }
}

// ---------- shell overwrite (clobber) / truncate of a real secret file ---------- //
{
  // `> secret`, `>> secret` (any redirect target), and `truncate -s 0 secret`.
  const redirect = cmd.match(/>>?\s*([^\s&|;]+)/);
  if (redirect && isSecretTarget(redirect[1])) deny("shell overwrite of a secret/credential file");

  const trunc = cmd.match(/\btruncate\b[^&|;]*\s([^\s&|;]+)/i);
  if (trunc && isSecretTarget(trunc[1])) deny("truncate of a secret/credential file");
}

// ---------- read / copy / exfil / PowerShell-write of a real secret file ---------- //
{
  // The Read-tool deny is bypassable via the allowed Bash(*) (`cat .env`), so guard those here too.
  // Scan EVERY token (not just the last) so `cat .env README.md`, `head .env > leak.txt`,
  // `cp .env /public/`, and `Set-Content .env -Value x` are all caught.
  // read / dump / copy / exfil / PS-write commands. (Editors like vi/nano are intentionally NOT
  // here — editing a secret manually in a terminal is the recommended path the guards point users to.)
  const SENSITIVE_CMD =
    /\b(cat|type|get-content|gc|more|less|head|tail|bat|nl|wc|od|xxd|strings|base64|awk|sed|grep|dd|cp|copy|copy-item|tee|set-content|add-content|out-file|clear-content|scp|rsync)\b/i;
  if (SENSITIVE_CMD.test(cmd) && tokensOf(cmd).some((t) => isSecretTarget(t))) {
    deny(
      "reading/copying/overwriting a secret/credential file via the shell " +
        "(the Read-tool deny does not cover Bash)",
    );
  }
}

// ---------- remaining unconditional catastrophes ---------- //
const RULES = [
  { re: /:\s*\(\s*\)\s*\{[^}]*\}\s*;/, why: "fork bomb" },
  { re: /\b(mkfs\b|diskpart\b|format\s+[a-z]:)/i, why: "disk format" },
  { re: />\s*\/dev\/(sd|nvme|disk|hd)/i, why: "raw block-device write" },
  { re: /\bdd\b[^&|;]*\bof=\/dev\/(sd|nvme|disk|hd)/i, why: "dd to a raw block device" },
  {
    re: /\bgit\s+push\b[^&|;]*\s(--force\b|-f\b)(?![-\w])/i,
    why: "git push --force (use --force-with-lease)",
  },
  { re: /\bgit\s+push\b[^&|;]*\s\+\S/i, why: "git push with a force refspec (leading '+')" },
  {
    re: /\bgit\s+clean\b[^&|;]*-[a-z]*x/i,
    why: "git clean -x (wipes gitignored files incl. .env/.venv)",
  },
];
const hit = RULES.find((r) => r.re.test(cmd));
if (hit) deny(hit.why);

process.exit(0);
