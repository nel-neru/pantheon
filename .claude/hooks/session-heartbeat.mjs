#!/usr/bin/env node
/**
 * Claude Code heartbeat hook — refresh a global "a pantheon-repo session is alive"
 * marker so scripts/evolve_resume.ps1 will NOT spawn a concurrent headless /evolve
 * while a live INTERACTIVE session is editing this same working tree. (The resume's
 * own headless children opt out via PANTHEON_EVOLVE_HEADLESS — see the guard below;
 * they are deduped by the pid lock, so the marker means "an interactive session lives".)
 *
 * The git-commit heartbeat that evolve_resume.ps1 already uses has two blind spots:
 *   - a long single turn (no commit fires until the Stop hook at turn end), and
 *   - a fresh session whose last commit is hours old.
 * Both let the hourly task wrongly conclude "no session" and double-launch (observed
 * for real: a rogue resume edited the same tree). This marker closes both windows.
 *
 * Registered on SessionStart (cold-start) + PostToolUse "*" (every tool, so it stays
 * fresh through a long turn). Best-effort, microsecond-cheap (no git/subprocess/net),
 * and NEVER blocks the turn — always exits 0.
 *
 * The PS reader looks ONLY at this file's mtime (LastWriteTime), never its contents,
 * so the JSON body below is advisory/debug parity with core/runtime/heartbeat.py. The
 * write is atomic (tmp in the same dir, then rename) so a concurrent reader never sees
 * a half-written file and the mtime flips atomically.
 */
import { readFileSync, mkdirSync, writeFileSync, renameSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// --- headless /evolve resume children must NOT write the marker --------------------- //
// evolve_resume.ps1 sets PANTHEON_EVOLVE_HEADLESS=1 on the claude it spawns. If such a
// resume crashed early it would otherwise mask its OWN restart for up to StaleMinutes
// (its fresh marker would make the next hourly tick skip). A healthy headless resume is
// already protected from double-launch by the pid lock + per-turn auto-commit, so the
// marker only needs to represent "an INTERACTIVE session is alive" — the collision the
// pid lock cannot see. Skipping here keeps that meaning precise.
if (process.env.PANTHEON_EVOLVE_HEADLESS === "1") process.exit(0);

// --- enrich the record from the hook payload (non-essential; PS ignores contents) -- //
let payload = {};
try {
  const raw = readFileSync(0, "utf8");
  if (raw) payload = JSON.parse(raw) || {};
} catch {
  /* no/invalid stdin — the marker write below does not depend on it */
}

// --- touch the marker atomically; swallow every error (must never break the turn) --- //
try {
  const dir = join(homedir(), ".pantheon");
  mkdirSync(dir, { recursive: true });
  const target = join(dir, "evolve_session.heartbeat");
  const tmp = `${target}.${process.pid}.tmp`;
  const record = {
    ts: new Date().toISOString(),
    pid: process.pid,
    cwd: typeof payload.cwd === "string" && payload.cwd ? payload.cwd : process.cwd(),
    event: typeof payload.hook_event_name === "string" ? payload.hook_event_name : "session",
  };
  writeFileSync(tmp, JSON.stringify(record));
  renameSync(tmp, target);
} catch {
  /* best-effort heartbeat — a failure here is never worth interrupting work */
}

process.exit(0);
