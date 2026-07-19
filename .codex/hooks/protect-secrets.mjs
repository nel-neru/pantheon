#!/usr/bin/env node
/**
 * Claude Code `PreToolUse` (Write|Edit) hook — protect secret/credential files.
 *
 * Denies edits to real secret/credential/key files using the shared denylist in
 * `./sensitive-paths.mjs`. Templates (`.env.example`/`.sample`/`.template`/`.dist`) AND ordinary
 * SOURCE files that merely contain "secret"/"credential" in their name (e.g. `secret_manager.py`,
 * and this hook's own siblings) are ALLOWED — only credential-SHAPED files are blocked.
 * Returns a PreToolUse `permissionDecision: "deny"` as JSON.
 */
import { readFileSync } from "node:fs";
import { isSecretFile, baseName } from "./sensitive-paths.mjs";

let file = "";
try {
  const { tool_input } = JSON.parse(readFileSync(0, "utf8"));
  file = (tool_input && tool_input.file_path) || "";
} catch {
  process.exit(0);
}

if (isSecretFile(file)) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason:
          `Blocked by Pantheon guardrail: '${baseName(file)}' looks like a secret/credential file. ` +
          `Edit it manually, or use the .example template.`,
      },
    }),
  );
  process.exit(0);
}

process.exit(0);
