#!/usr/bin/env node
/**
 * Claude Code `PostToolUse` (Write|Edit) hook — Pantheon の YAML 設定を検証する。
 *
 * `config/**.yaml` または `skills/**.yaml`（Pantheon-native の skill / persona /
 * department / agent 定義）が編集されたら、既存の `scripts/validate_config.py` を実行し、
 * schema_version / capability_id 接頭辞 / skills 2〜3 個 / persona キー等の規約を検査する。
 *
 * 検証に失敗したら stderr に内容を出して exit 2（Claude にフィードバックされ修正を促す）。
 * 無関係なファイルや想定外エラーでは常に exit 0（編集をブロックしない）。
 */
import { readFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, extname } from "node:path";

try {
  const { tool_input } = JSON.parse(readFileSync(0, "utf8"));
  const file = tool_input?.file_path;
  if (!file) process.exit(0);

  const ext = extname(file).toLowerCase();
  if (ext !== ".yaml" && ext !== ".yml") process.exit(0);

  const norm = file.replace(/\\/g, "/");
  const isConfig = /(^|\/)config\//.test(norm) || /(^|\/)skills\//.test(norm);
  if (!isConfig) process.exit(0);

  const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const py =
    process.platform === "win32"
      ? join(projectDir, ".venv", "Scripts", "python.exe")
      : join(projectDir, ".venv", "bin", "python");
  if (!existsSync(py)) process.exit(0);

  try {
    execFileSync(py, [join(projectDir, "scripts", "validate_config.py")], {
      cwd: projectDir,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (err) {
    const out = `${err.stdout?.toString() ?? ""}${err.stderr?.toString() ?? ""}`.trim();
    process.stderr.write(
      `Pantheon config validation failed after editing ${norm}:\n${out}\n`,
    );
    process.exit(2);
  }
} catch {
  /* never block on unexpected hook failure */
}
process.exit(0);
