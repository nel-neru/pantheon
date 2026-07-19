---
name: "source-command-trend-report"
description: "収集済みトレンドをスコア順に表示し、必要なら今すぐ収集・変換する"
---

# source-command-trend-report

Use this skill when the user asks to run the migrated source command `trend-report`.

## Command Template

# /trend-report — トレンド収集の状態を見る

web/RSS・YouTube から収集・採点済みのトレンドをスコア順に確認する。

```powershell
.\.venv\Scripts\python.exe main.py trends list --limit 30
```

絞り込み: `--source web|youtube|x`、`--genre ai|side_business|Codex|...`、`--min-score 7`

いま収集したい場合:

```powershell
.\.venv\Scripts\python.exe main.py trends collect
```

- 収集 = `config/trend_sources.yaml` の RSS/Atom＋YouTube チャンネルを横断取得→light ティアで
  採点→重複排除して `~/.pantheon/trends/trends.jsonl` に保存。
- 高スコアトレンドは trend daemon が ContentJob ドラフト（`enabled=False`＝承認待ち）と新規事業
  提案（`status=proposed`）へ変換する。承認は `/inbox`（Web GUI）または `pantheon proposals`。
- `genre=Codex` のトレンドは `.Codex/` 設定更新提案になる（`trend-watcher` agent と連動）。
- Web API: `GET /api/trends`、`POST /api/trends/collect`、`POST /api/trends/convert`。
