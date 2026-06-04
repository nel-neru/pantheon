#!/usr/bin/env node
/**
 * Claude Code `PostToolUse` (Write|Edit) hook — auto-format the edited file.
 *
 * Python files are formatted with the project's venv ruff. TypeScript/CSS are
 * left alone (the frontend has no formatter configured; type-checking is `tsc -b`).
 * Runs `ruff format` only (idempotent, non-destructive) — NOT `--fix`, to avoid
 * import/lint rewrites mid-edit. Never blocks: any failure exits 0 silently.
 * Configured with `"async": true` so it never stalls the turn.
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
