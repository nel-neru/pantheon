# 外部 CLI ツール導入手順（I8）

実行モードを **CLI** にすると、RepoCorp は内蔵エージェントの代わりに外部コーディング CLI を
埋め込みターミナル上で起動します。対応ツールと検出は `core/execution/cli_registry.py` が管理します。

## 対応ツールと既定コマンド

| ツール | 既定コマンド | 用途 | 導入の目安 |
|---|---|---|---|
| Claude Code | `claude` | Anthropic 公式 CLI | `npm i -g @anthropic-ai/claude-code` |
| Codex | `codex` | OpenAI 系コーディング CLI | 各配布元の手順 |
| Gemini CLI | `gemini` | Google Gemini CLI | 各配布元の手順 |
| Aider | `aider` | OSS ペアプロ CLI | `pipx install aider-chat` |
| OpenCode | `opencode` | OSS コーディング CLI | 各配布元の手順 |

> 実際の配布元/コマンド名は各プロジェクトの最新ドキュメントに従ってください。上表は目安です。

## 可用性の確認

- `GET /api/execution/modes` が各ツールの `available`（PATH 検出）を返します。
- Web GUI の Settings「実行モード」カードでも確認できます。

## コマンド名の上書き

PATH 上の実体名が既定と異なる場合、`~/.repocorp/gui_settings.json` の `cli_commands` で上書きします。

```json
{
  "execution_mode": "cli",
  "cli_tool": "claude",
  "cli_commands": { "claude": "claude-x", "aider": "/opt/bin/aider" }
}
```

## 使い方

1. Settings で実行モード=CLI、使用する `cli_tool` を選択。
2. ターミナルページでワークスペースを作成すると、選択した CLI が起動します（`POST /api/terminal/sessions` の `cli_tool`）。
3. 未検出の場合は [`docs/troubleshooting.md`](troubleshooting.md) を参照。
