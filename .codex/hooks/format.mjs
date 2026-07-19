#!/usr/bin/env node
/**
 * Claude Code `PostToolUse` (Write|Edit) hook — auto-format the edited file.
 *
 * Python files are formatted with the project's venv ruff. TypeScript/CSS are
 * left alone (the frontend has no formatter configured; type-checking is `tsc -b`).
 * Runs `ruff format` only (idempotent, non-destructive) — NOT `--fix`, to avoid
 * import/lint rewrites mid-edit. Never blocks: any failure exits 0 silently.
 * Runs SYNCHRONOUSLY (not `async`): `ruff format` of one file is sub-second, and a
 * deferred reformat could rewrite a file the model re-reads/re-edits later in the same
 * turn (stale read, or an Edit whose `old_string` ruff already reflowed). The 60s hook
 * timeout in settings.json bounds the rare slow case.
 */
import { readFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, extname } from "node:path";

try {
  const { tool_input } = JSON.parse(readFileSync(0, "utf8"));
  const file = tool_input?.file_path;
  if (!file) process.exit(0);

  if (extname(file).toLowerCase() === ".py") {
    const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
    const py =
      process.platform === "win32"
        ? join(projectDir, ".venv", "Scripts", "python.exe")
        : join(projectDir, ".venv", "bin", "python");
    if (existsSync(py)) {
      execFileSync(py, ["-m", "ruff", "format", file], { stdio: "ignore" });
    }
  }
} catch {
  /* never block on formatter failure */
}
process.exit(0);
