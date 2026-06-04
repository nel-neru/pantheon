#!/usr/bin/env node
/**
 * Claude Code `PreToolUse` (Write|Edit) hook — protect secret/credential files.
 *
 * Denies edits to `.env` (and `.env.<env>`) and common credential/key files,
 * while explicitly ALLOWING templates (`.env.example` / `.sample` / `.template`).
 * Returns a PreToolUse `permissionDecision: "deny"` as JSON.
 */
import { readFileSync } from "node:fs";

let file = "";
try {
  const { tool_input } = JSON.parse(readFileSync(0, "utf8"));
  file = (tool_input && tool_input.file_path) || "";
} catch {
  process.exit(0);
}

const norm = file.replace(/\\/g, "/").toLowerCase();
const base = norm.split("/").pop() || "";

const isTemplate = /\.(example|sample|template|dist)$/.test(base);
const isEnv = !isTemplate && (base === ".env" || /^\.env\./.test(base));
const isCredential =
  /(^|\/)\.credentials\.json$/.test(norm) ||
  /(^|[._-])(secret|secrets|credentials?)([._-]|\.)/.test(base) ||
  /\.(pem|key|pfx|p12|keystore)$/.test(base) ||
  /(^|\/)id_(rsa|ed25519|ecdsa)(\.|$)/.test(base);

if (isEnv || isCredential) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason:
          `Blocked by Pantheon guardrail: '${base}' looks like a secret/credential file. ` +
          `Edit it manually, or use the .example template.`,
      },
    }),
  );
  process.exit(0);
}

process.exit(0);
